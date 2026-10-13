"""Hosting adapter contract (§5.2): template version + config → deploy status,
URL, logs, expiry and teardown. Vercel first, provider-replaceable."""

import hashlib
import json
import time
from typing import Protocol

import httpx
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.config import PROJECT_ROOT, settings


class HostingAdapter(Protocol):
    def deploy(self, *, template_id: str, template_version: str, site_config: dict) -> dict: ...

    def teardown(self, url: str) -> bool: ...


class HostingConfigurationError(RuntimeError):
    pass


DEFAULT_LOCAL_RENDERER = "preview_static.html"


def _local_renderer_for(template_id: str) -> str:
    """Map a template_id to its offline Jinja renderer via the template registry.

    Unknown/unmapped templates fall back to the generic renderer so QA never
    fails closed on a registry gap.
    """
    try:
        from app.services.config_loader import load

        manifests = load("templates").get("templates") or {}
        renderer = (manifests.get(template_id) or {}).get("local_renderer")
        if renderer:
            candidate = PROJECT_ROOT / "templates" / renderer
            if candidate.exists():
                return renderer
    except Exception:
        pass
    return DEFAULT_LOCAL_RENDERER


class LocalStubAdapter:
    """Render a real local HTML artifact so browser QA can run offline."""

    def deploy(self, *, template_id: str, template_version: str, site_config: dict) -> dict:
        digest = hashlib.sha256(
            json.dumps(site_config, sort_keys=True, default=str).encode()
        ).hexdigest()[:12]
        output_dir = PROJECT_ROOT / "artifacts" / "local_previews" / digest
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "index.html"
        environment = Environment(
            loader=FileSystemLoader(str(PROJECT_ROOT / "templates")),
            autoescape=select_autoescape(["html"]),
        )
        template = environment.get_template(_local_renderer_for(template_id))
        def fact_value(key: str) -> str:
            value = site_config.get(key) or {}
            return value.get("value", "") if isinstance(value, dict) else str(value)

        business_name = fact_value("business_name") or site_config.get("business", "Preview")
        content = site_config.get("content") or {
            "hero": {
                "headline": business_name,
                "subheadline": "Pré-visualização conceptual.",
            },
            "services": [],
            "cta": {"label": "Pedir marcação", "supporting": "Sem compromisso"},
            "contact": {
                "phone": fact_value("phone"),
                "email": fact_value("email"),
                "whatsapp": fact_value("whatsapp"),
            },
            "theme": {},
            "disclaimer": (
                site_config.get("disclaimer")
                or "Pré-visualização conceptual não oficial — não representa o negócio."
            ),
            "seo_title": business_name,
        }
        output_path.write_text(
            template.render(
                business_name=business_name,
                category=site_config.get("category", ""),
                city=site_config.get("city", ""),
                content=content,
                form_endpoint=site_config.get("form_endpoint", ""),
                build_id=site_config.get("build_id", ""),
                form_token=site_config.get("form_token", ""),
            ),
            encoding="utf-8",
        )
        return {
            "status": "deployed",
            "url": f"https://preview-{digest}.local.test",
            "qa_url": output_path.resolve().as_uri(),
            "local_path": str(output_path.resolve()),
            "logs": [f"stub deploy {template_id}@{template_version}"],
        }

    def teardown(self, url: str) -> bool:
        return True


class VercelAdapter:
    """Thin Vercel REST wrapper. Requires VERCEL_TOKEN; deployment expects the
    template project to already exist (templates are audited/published separately)."""

    BASE = "https://api.vercel.com"

    def __init__(
        self,
        token: str,
        project_id: str,
        github_repo_id: str,
        git_ref: str = "main",
        team_id: str = "",
        template_projects: dict | None = None,
    ):
        self.token = token
        self.project_id = project_id
        self.github_repo_id = github_repo_id
        self.git_ref = git_ref
        self.team_id = team_id
        # Maps a template deploy_key -> {project_id, github_repo_id, git_ref?}.
        # Keyed by the ``deploy_key`` in config/templates, falling back to
        # ``template_id`` for convenience. Unmapped templates use the default
        # single project so existing single-template setups keep working.
        self.template_projects = template_projects or {}

    def _params(self) -> dict:
        params = {"forceNew": "1"}
        if self.team_id:
            params["teamId"] = self.team_id
        return params

    def _target_project(self, template_id: str) -> tuple[str, str, str]:
        """Resolve (project_id, github_repo_id, git_ref) for a template_id."""
        deploy_key = self._deploy_key_for(template_id)
        mapping = self.template_projects.get(deploy_key) or self.template_projects.get(template_id)
        if mapping:
            return (
                mapping.get("project_id") or self.project_id,
                mapping.get("github_repo_id") or self.github_repo_id,
                mapping.get("git_ref") or self.git_ref,
            )
        return self.project_id, self.github_repo_id, self.git_ref

    @staticmethod
    def _deploy_key_for(template_id: str) -> str:
        try:
            from app.services.config_loader import load

            manifests = load("templates").get("templates") or {}
            return (manifests.get(template_id) or {}).get("deploy_key") or template_id
        except Exception:
            return template_id

    def deploy(self, *, template_id: str, template_version: str, site_config: dict) -> dict:
        project_id, github_repo_id, git_ref = self._target_project(template_id)
        response = httpx.post(
            f"{self.BASE}/v13/deployments",
            headers={"Authorization": f"Bearer {self.token}"},
            params=self._params(),
            json={
                "name": template_id,
                "project": project_id,
                "target": "preview",
                "gitSource": {
                    "type": "github",
                    "repoId": github_repo_id,
                    "ref": git_ref,
                },
                "env": {"SITE_CONFIG": json.dumps(site_config, default=str)},
                "meta": {
                    "template_id": template_id,
                    "template_version": template_version,
                },
            },
            timeout=60.0,
        )
        if response.status_code >= 400:
            return {"status": "failed", "url": "", "logs": [response.text]}
        data = response.json()
        deployment_id = data.get("id", "")
        ready_state = data.get("readyState")
        if ready_state and ready_state != "READY" and deployment_id:
            deadline = time.monotonic() + 55
            while time.monotonic() < deadline:
                status_response = httpx.get(
                    f"{self.BASE}/v13/deployments/{deployment_id}",
                    headers={"Authorization": f"Bearer {self.token}"},
                    params=self._params(),
                    timeout=15.0,
                )
                if status_response.status_code >= 400:
                    return {
                        "status": "failed",
                        "url": "",
                        "deployment_id": deployment_id,
                        "logs": [status_response.text],
                    }
                status_data = status_response.json()
                ready_state = status_data.get("readyState")
                if ready_state == "READY":
                    data = status_data
                    break
                if ready_state in {"ERROR", "CANCELED"}:
                    return {
                        "status": "failed",
                        "url": "",
                        "deployment_id": deployment_id,
                        "logs": [f"Vercel deployment ended in {ready_state}"],
                    }
                time.sleep(1)
            else:
                return {
                    "status": "failed",
                    "url": "",
                    "deployment_id": deployment_id,
                    "logs": ["Vercel deployment readiness timed out"],
                }
        return {
            "status": "deployed",
            "url": f"https://{data.get('url', '')}",
            "deployment_id": deployment_id,
            "logs": [],
        }

    def teardown(self, url: str) -> bool:
        deployment_id = url.removeprefix("https://")
        response = httpx.delete(
            f"{self.BASE}/v13/deployments/{deployment_id}",
            headers={"Authorization": f"Bearer {self.token}"},
            params=self._params(),
            timeout=30.0,
        )
        return response.status_code < 400


def _parse_template_projects(raw: str) -> dict:
    """Parse VERCEL_TEMPLATE_PROJECTS JSON: {deploy_key: {project_id, ...}}."""
    if not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HostingConfigurationError(
            f"VERCEL_TEMPLATE_PROJECTS must be valid JSON: {exc}"
        ) from exc
    if not isinstance(parsed, dict):
        raise HostingConfigurationError(
            "VERCEL_TEMPLATE_PROJECTS must be a JSON object keyed by deploy_key"
        )
    return parsed


def get_hosting_adapter() -> HostingAdapter:
    vercel_values = (
        settings.vercel_token,
        settings.vercel_project_id,
        settings.vercel_github_repo_id,
    )
    if any(vercel_values):
        if not all(vercel_values):
            raise HostingConfigurationError(
                "Vercel requires VERCEL_TOKEN, VERCEL_PROJECT_ID, and "
                "VERCEL_GITHUB_REPO_ID"
            )
        return VercelAdapter(
            token=settings.vercel_token,
            project_id=settings.vercel_project_id,
            github_repo_id=settings.vercel_github_repo_id,
            git_ref=settings.vercel_git_ref,
            team_id=settings.vercel_team_id,
            template_projects=_parse_template_projects(settings.vercel_template_projects),
        )
    return LocalStubAdapter()
