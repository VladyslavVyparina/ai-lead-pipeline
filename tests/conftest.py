import pytest
from dataclasses import replace
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.adapters.hosting import LocalStubAdapter
from app.config import settings
from app.database import Base
from app.models import SourceConnector


@pytest.fixture(autouse=True)
def offline_external_adapters(monkeypatch, tmp_path):
    """Tests never call configured Vercel/R2/AI credentials from a local .env."""
    from app.services import ai_agent, artifact_storage, site_factory

    local_store = artifact_storage.LocalArtifactStore(str(tmp_path / "private-artifacts"))
    monkeypatch.setattr(site_factory, "get_hosting_adapter", lambda: LocalStubAdapter())
    monkeypatch.setattr(artifact_storage, "get_artifact_store", lambda: local_store)
    offline_settings = replace(settings, openai_api_key="", openrouter_api_key="", ai_provider="auto")
    monkeypatch.setattr(ai_agent, "settings", offline_settings)


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine)
    session = TestSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def connector(db):
    c = SourceConnector(
        name="test-csv",
        adapter="csv_import",
        owner="owner",
        permitted_use="pilot research",
        quota_per_run=5000,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c
