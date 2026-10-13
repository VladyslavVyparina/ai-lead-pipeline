"""Private artifact persistence with a local development and R2 production backend.

The database stores only an immutable object reference and integrity metadata.
Artifact bytes never live in Postgres and R2 credentials never reach the browser.
"""

from __future__ import annotations

import hashlib
import mimetypes
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Artifact, Business, Proposal, WebsiteBuild


class ArtifactStorageError(RuntimeError):
    pass


@dataclass(frozen=True)
class StoredArtifact:
    backend: str
    bucket: str
    object_key: str
    byte_size: int
    sha256: str


def _safe_key(key: str) -> str:
    path = PurePosixPath(key)
    if not key or path.is_absolute() or ".." in path.parts:
        raise ArtifactStorageError("artifact key must be a safe relative path")
    return path.as_posix()


class LocalArtifactStore:
    backend = "local"
    bucket = "local-private"

    def __init__(self, root: str):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        candidate = (self.root / _safe_key(key)).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:  # defensive on Windows path semantics
            raise ArtifactStorageError("artifact path escapes local storage root") from exc
        return candidate

    def put_bytes(self, key: str, payload: bytes, content_type: str) -> StoredArtifact:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return StoredArtifact(
            backend=self.backend,
            bucket=self.bucket,
            object_key=_safe_key(key),
            byte_size=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(),
        )

    def open(self, key: str) -> BinaryIO:
        return self._path(key).open("rb")

    def path_for(self, key: str) -> Path:
        return self._path(key)

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


class R2ArtifactStore:
    backend = "r2"

    def __init__(self):
        if not all(
            (
                settings.r2_account_id,
                settings.r2_access_key_id,
                settings.r2_secret_access_key,
                settings.r2_bucket_private,
            )
        ):
            raise ArtifactStorageError("R2 requires account ID, scoped credentials, and a private bucket")
        try:
            import boto3
        except ImportError as exc:  # clear failure when optional dependency was omitted
            raise ArtifactStorageError("R2 storage requires boto3") from exc
        self.bucket = settings.r2_bucket_private
        endpoint = settings.r2_endpoint_url or (
            f"https://{settings.r2_account_id}.r2.cloudflarestorage.com"
        )
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            region_name="auto",
            aws_access_key_id=settings.r2_access_key_id,
            aws_secret_access_key=settings.r2_secret_access_key,
        )

    def put_bytes(self, key: str, payload: bytes, content_type: str) -> StoredArtifact:
        key = _safe_key(key)
        digest = hashlib.sha256(payload).hexdigest()
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=payload,
            ContentType=content_type,
            Metadata={"sha256": digest},
        )
        return StoredArtifact(self.backend, self.bucket, key, len(payload), digest)

    def signed_download_url(self, key: str, expires_seconds: int = 300) -> str:
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": _safe_key(key)},
            ExpiresIn=max(1, min(expires_seconds, 3600)),
        )

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=_safe_key(key))


def get_artifact_store():
    if settings.artifact_storage_backend == "r2":
        return R2ArtifactStore()
    if settings.artifact_storage_backend == "local":
        return LocalArtifactStore(settings.artifact_local_dir)
    raise ArtifactStorageError("ARTIFACT_STORAGE_BACKEND must be local or r2")


def persist_artifact(
    db: Session,
    *,
    business: Business,
    kind: str,
    payload: bytes,
    filename: str,
    content_type: str | None = None,
    website_build: WebsiteBuild | None = None,
    proposal: Proposal | None = None,
    expires_at: datetime | None = None,
) -> Artifact:
    """Upload private bytes and register their immutable reference in one place."""
    suffix = Path(filename).suffix.lower()
    content_type = content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    captured_at = datetime.utcnow().strftime("%Y%m%dT%H%M%S%fZ")
    key = f"leads/{business.id}/{kind}/{captured_at}-{hashlib.sha256(payload).hexdigest()[:12]}{suffix}"
    stored = get_artifact_store().put_bytes(key, payload, content_type)
    artifact = Artifact(
        business_id=business.id,
        website_build_id=website_build.id if website_build else None,
        proposal_id=proposal.id if proposal else None,
        kind=kind,
        storage_backend=stored.backend,
        bucket=stored.bucket,
        object_key=stored.object_key,
        content_type=content_type,
        byte_size=stored.byte_size,
        sha256=stored.sha256,
        is_private=True,
        expires_at=expires_at or datetime.utcnow() + timedelta(days=settings.artifact_retention_days),
    )
    db.add(artifact)
    db.flush()
    return artifact


def delete_expired_artifacts(db: Session, *, now: datetime | None = None) -> int:
    now = now or datetime.utcnow()
    expired = db.query(Artifact).filter(
        Artifact.deleted_at.is_(None), Artifact.expires_at.is_not(None), Artifact.expires_at <= now
    ).all()
    for artifact in expired:
        get_artifact_store().delete(artifact.object_key)
        artifact.deleted_at = now
        db.add(artifact)
    db.flush()
    return len(expired)


def persist_qa_screenshots(db: Session, *, business: Business, website_build: WebsiteBuild, qa_report: dict) -> dict:
    """Move rendered screenshots into private artifact storage and return safe links."""
    report = dict(qa_report or {})
    screenshot_dir = Path(settings.qa_artifact_dir) / f"build-{website_build.id}"
    for viewport in ("desktop", "mobile"):
        screenshot = screenshot_dir / f"{viewport}.png"
        if not screenshot.is_file():
            continue
        artifact = persist_artifact(
            db,
            business=business,
            website_build=website_build,
            kind="qa_screenshot",
            payload=screenshot.read_bytes(),
            filename=screenshot.name,
            content_type="image/png",
        )
        report[f"{viewport}_artifact_id"] = artifact.id
        report[f"{viewport}_download_path"] = f"/private-artifacts/{artifact.id}/download"
    return report
