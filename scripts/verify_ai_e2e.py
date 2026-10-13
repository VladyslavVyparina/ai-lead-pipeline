"""Run one local, non-contacting Release 1 package with the configured AI provider.

The script forces an in-memory SQLite database, local temporary artifacts and
the offline hosting adapter itself. It does not use R2, deploy to Vercel, or
send outreach. Run it with a configured AI provider:

    py -3.10 scripts/verify_ai_e2e.py

The script uses the synthetic directory fixture, never sends outreach, and
fails unless at least one OpenAI- or OpenRouter-backed ledger record is created.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

# Allow direct `python scripts/verify_ai_e2e.py` execution from a checkout.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Force a disposable, non-contacting runtime before importing application
# settings. ``load_dotenv`` does not override these explicit process values.
E2E_ARTIFACT_DIR = tempfile.mkdtemp(prefix="ai-lead-e2e-")
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["ARTIFACT_STORAGE_BACKEND"] = "local"
os.environ["ARTIFACT_LOCAL_DIR"] = E2E_ARTIFACT_DIR
os.environ["QA_ARTIFACT_DIR"] = str(Path(E2E_ARTIFACT_DIR) / "qa")
os.environ["VERCEL_TOKEN"] = ""
os.environ["VERCEL_TEAM_ID"] = ""
os.environ["VERCEL_PROJECT_ID"] = ""
os.environ["VERCEL_GITHUB_REPO_ID"] = ""

from app.database import Base, SessionLocal, engine
from app.models import AIUsageLedger, Business, PipelineJob
from app.services.pipeline import approve_and_generate_preview, run_porto_wellness_vertical_slice


def main() -> int:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # One lead covers research, preview copy and outreach while keeping the
        # provider-backed smoke test bounded to three model calls.
        discovery = run_porto_wellness_vertical_slice(db, limit=1, top_review=1)
        business_id = next(iter(discovery["review_queue"]), None)
        if business_id is None:
            # A rerun against the same disposable database may have already
            # advanced the only shortlisted lead to preview_ready. Reuse that
            # package rather than creating another lead or reporting a false
            # failure.
            completed = (
                db.query(PipelineJob)
                .filter(
                    PipelineJob.job_type == "asset_package",
                    PipelineJob.status == "succeeded",
                    PipelineJob.business_id.isnot(None),
                )
                .order_by(PipelineJob.id.desc())
                .first()
            )
            business_id = completed.business_id if completed else None
        if business_id is None:
            raise RuntimeError("no eligible lead was shortlisted or previously packaged")
        business = db.get(Business, business_id)
        if business is None:
            raise RuntimeError("shortlisted business disappeared")
        package = approve_and_generate_preview(db, business, actor="human:local-ai-e2e")
        db.commit()

        provider_rows = (
            db.query(AIUsageLedger)
            .filter(
                AIUsageLedger.provider.in_(("openai", "openrouter")),
                AIUsageLedger.status == "succeeded",
            )
            .all()
        )
        if not provider_rows:
            raise RuntimeError("AI provider did not return a successful ledger entry")
        if package.get("pipeline_stage") != "preview_ready":
            raise RuntimeError(f"preview did not pass QA: {package.get('pipeline_stage')}")

        print(
            json.dumps(
                {
                    "business_id": business.id,
                    "business": business.name,
                    "preview_url": package.get("preview_url"),
                    "qa_status": package.get("qa", {}).get("status"),
                    "proposal_id": package.get("proposal", {}).get("id"),
                    "message_id": package.get("message_id"),
                    "recommended_channel": package.get("recommended_channel"),
                    "ai_calls": len(provider_rows),
                    "ai_cost_usd": round(sum(float(row.estimated_cost_usd or 0) for row in provider_rows), 8),
                },
                ensure_ascii=False,
            )
        )
        return 0
    finally:
        db.close()
        shutil.rmtree(E2E_ARTIFACT_DIR, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
