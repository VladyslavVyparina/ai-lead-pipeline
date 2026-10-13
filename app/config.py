import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

# Local developers can select a Git-ignored environment file without copying
# secrets into the default `.env`, for example: `$env:ENV_FILE='.env.dev'`.
load_dotenv(os.getenv("ENV_FILE", ".env"))

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"


def _default_preview_origin_regex() -> str:
    """Allow local preview hosts + the PUBLIC_BASE_URL host (pilot)."""
    public = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
    host = urlparse(public).hostname or "localhost"
    host_re = re.escape(host)
    return (
        r"^(https://[a-z0-9-]+\.vercel\.app|"
        r"http://(localhost|127\.0\.0\.1)(:[0-9]+)?|"
        rf"https?://{host_re}(:[0-9]+)?)$"
    )


def _allowed_hosts() -> tuple[str, ...]:
    configured = os.getenv("ALLOWED_HOSTS", "").strip()
    if configured:
        return tuple(host.strip() for host in configured.split(",") if host.strip())
    if os.getenv("APP_ENV", "development").lower() == "production":
        host = urlparse(os.getenv("PUBLIC_BASE_URL", "")).hostname
        return (host,) if host else ()
    return ("*",)


@dataclass(frozen=True)
class Settings:
    app_env: str = os.getenv("APP_ENV", "development").lower()
    app_host: str = os.getenv("APP_HOST", "0.0.0.0")
    app_port: int = int(os.getenv("APP_PORT", "8000"))
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./pipeline.db")
    public_base_url: str = field(
        default_factory=lambda: os.getenv("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
    )
    preview_origin_regex: str = field(
        default_factory=lambda: os.getenv("PREVIEW_ORIGIN_REGEX") or _default_preview_origin_regex()
    )
    allowed_hosts: tuple[str, ...] = field(default_factory=_allowed_hosts)

    inbound_webhook_secret: str = os.getenv("INBOUND_WEBHOOK_SECRET", "change_this_secret")
    admin_token: str = os.getenv("ADMIN_TOKEN", "change_this_token")

    # `auto` selects OpenRouter when its key is configured, otherwise OpenAI.
    # Pin a model in OPENROUTER_MODEL/CHAT_MODEL for repeatable environments;
    # `openrouter/free` is suitable only for small local experiments.
    ai_provider: str = os.getenv("AI_PROVIDER", "auto").lower()
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openrouter_api_key: str = os.getenv("OPENROUTER_API_KEY", "")
    openrouter_model: str = os.getenv("OPENROUTER_MODEL", "openrouter/free")
    chat_model: str = field(
        default_factory=lambda: os.getenv(
            "CHAT_MODEL",
            os.getenv("OPENROUTER_MODEL", "openrouter/free")
            if os.getenv("OPENROUTER_API_KEY")
            else "gpt-4o-mini",
        )
    )
    openrouter_site_url: str = os.getenv("OPENROUTER_SITE_URL", "")
    openrouter_app_name: str = os.getenv("OPENROUTER_APP_NAME", "AI Lead Pipeline")
    # Preview websites are deterministic by default: data + approved blocks,
    # not a paid generative-copy call. Set to ``ai`` only for an explicitly
    # approved polish pass after the operator has reviewed the evidence.
    preview_content_mode: str = os.getenv("PREVIEW_CONTENT_MODE", "deterministic").lower()

    vercel_token: str = os.getenv("VERCEL_TOKEN", "")
    vercel_team_id: str = os.getenv("VERCEL_TEAM_ID", "")
    vercel_project_id: str = os.getenv("VERCEL_PROJECT_ID", "")
    vercel_github_repo_id: str = os.getenv("VERCEL_GITHUB_REPO_ID", "")
    vercel_git_ref: str = os.getenv("VERCEL_GIT_REF", "main")
    # JSON map of template deploy_key -> {project_id, github_repo_id, git_ref?}
    # for routing multi-niche templates to their own Vercel projects. Empty =
    # all templates deploy to the single default VERCEL_PROJECT_ID.
    vercel_template_projects: str = os.getenv("VERCEL_TEMPLATE_PROJECTS", "")

    per_lead_token_budget: float = float(os.getenv("PER_LEAD_TOKEN_BUDGET", "0.25"))
    ai_max_output_tokens: int = int(os.getenv("AI_MAX_OUTPUT_TOKENS", "600"))
    ai_request_timeout_seconds: float = float(os.getenv("AI_REQUEST_TIMEOUT_SECONDS", "30"))
    google_places_api_key: str = os.getenv("GOOGLE_PLACES_API_KEY", "")
    crawl_max_pages: int = int(os.getenv("CRAWL_MAX_PAGES", "6"))
    crawl_timeout_seconds: float = float(os.getenv("CRAWL_TIMEOUT_SECONDS", "12"))
    crawl_max_response_bytes: int = int(os.getenv("CRAWL_MAX_RESPONSE_BYTES", "2000000"))
    qa_artifact_dir: str = os.getenv(
        "QA_ARTIFACT_DIR", str(PROJECT_ROOT / "artifacts" / "preview_qa")
    )
    artifact_storage_backend: str = os.getenv("ARTIFACT_STORAGE_BACKEND", "local").lower()
    artifact_local_dir: str = os.getenv(
        "ARTIFACT_LOCAL_DIR", str(PROJECT_ROOT / "private_artifacts")
    )
    artifact_retention_days: int = int(os.getenv("ARTIFACT_RETENTION_DAYS", "90"))
    r2_account_id: str = os.getenv("R2_ACCOUNT_ID", "")
    r2_access_key_id: str = os.getenv("R2_ACCESS_KEY_ID", "")
    r2_secret_access_key: str = os.getenv("R2_SECRET_ACCESS_KEY", "")
    r2_bucket_private: str = os.getenv("R2_BUCKET_PRIVATE", "")
    r2_endpoint_url: str = os.getenv("R2_ENDPOINT_URL", "")

    def validate_runtime(self) -> None:
        """Fail closed when a production deployment is incomplete or unsafe."""
        if self.app_env not in {"development", "test", "production"}:
            raise RuntimeError("APP_ENV must be development, test, or production")
        if self.app_env != "production":
            return

        errors: list[str] = []
        if self.database_url.startswith("sqlite"):
            errors.append("DATABASE_URL must use PostgreSQL in production")
        if not self.public_base_url.startswith("https://"):
            errors.append("PUBLIC_BASE_URL must use HTTPS in production")
        if not self.allowed_hosts or "*" in self.allowed_hosts:
            errors.append("ALLOWED_HOSTS must contain explicit production hostnames")
        if self.admin_token in {"", "change_this_token"}:
            errors.append("ADMIN_TOKEN must be a strong secret")
        if self.inbound_webhook_secret in {"", "change_this_secret"}:
            errors.append("INBOUND_WEBHOOK_SECRET must be a strong secret")
        if not all(
            (self.vercel_token, self.vercel_project_id, self.vercel_github_repo_id)
        ):
            errors.append(
                "VERCEL_TOKEN, VERCEL_PROJECT_ID, and VERCEL_GITHUB_REPO_ID "
                "are required for production previews"
            )
        if self.artifact_storage_backend not in {"local", "r2"}:
            errors.append("ARTIFACT_STORAGE_BACKEND must be local or r2")
        if self.artifact_storage_backend == "local":
            errors.append("ARTIFACT_STORAGE_BACKEND=r2 is required in production")
        if self.artifact_storage_backend == "r2" and not all(
            (
                self.r2_account_id,
                self.r2_access_key_id,
                self.r2_secret_access_key,
                self.r2_bucket_private,
            )
        ):
            errors.append("R2 account, scoped credentials, and private bucket are required")
        if errors:
            raise RuntimeError("Production startup refused: " + "; ".join(errors))


settings = Settings()
