from datetime import datetime, timedelta

import pytest

from app.models import Business
from app.services import artifact_storage
from app.services.artifact_storage import ArtifactStorageError, LocalArtifactStore, delete_expired_artifacts, persist_artifact


def _business(db):
    business = Business(
        name="Artifact Spa",
        category="massage_wellness",
        city="porto",
        dedupe_key="artifact-spa",
    )
    db.add(business)
    db.flush()
    return business


def test_local_store_rejects_path_escape(tmp_path):
    store = LocalArtifactStore(str(tmp_path / "private"))
    with pytest.raises(ArtifactStorageError):
        store.put_bytes("../outside.txt", b"no", "text/plain")


def test_persisted_artifact_is_private_and_integrity_tracked(db, tmp_path, monkeypatch):
    store = LocalArtifactStore(str(tmp_path / "private"))
    monkeypatch.setattr(artifact_storage, "get_artifact_store", lambda: store)

    artifact = persist_artifact(
        db,
        business=_business(db),
        kind="proposal_json",
        payload=b'{"proposal":true}',
        filename="proposal.json",
        content_type="application/json",
    )

    assert artifact.is_private is True
    assert artifact.storage_backend == "local"
    assert artifact.object_key.startswith("leads/")
    with store.open(artifact.object_key) as handle:
        assert handle.read() == b'{"proposal":true}'


def test_expired_artifacts_are_deleted_from_store(db, tmp_path, monkeypatch):
    store = LocalArtifactStore(str(tmp_path / "private"))
    monkeypatch.setattr(artifact_storage, "get_artifact_store", lambda: store)
    artifact = persist_artifact(
        db,
        business=_business(db),
        kind="qa_screenshot",
        payload=b"png-bytes",
        filename="desktop.png",
        expires_at=datetime.utcnow() - timedelta(seconds=1),
    )

    assert delete_expired_artifacts(db) == 1
    assert artifact.deleted_at is not None
    with pytest.raises(FileNotFoundError):
        store.open(artifact.object_key)
