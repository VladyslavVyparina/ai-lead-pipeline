from app.models import Business
from app.services import artifact_storage
from app.services.artifact_storage import LocalArtifactStore
from app.services.proposal import build_proposal
from app.services.proposal_pdf import ensure_proposal_pdf, render_proposal_pdf


def test_proposal_pdf_is_valid_private_and_idempotent(db, tmp_path, monkeypatch):
    store = LocalArtifactStore(str(tmp_path / "private"))
    monkeypatch.setattr(artifact_storage, "get_artifact_store", lambda: store)
    business = Business(
        name="Porto Wellness Studio",
        category="massage_wellness",
        city="porto",
        dedupe_key="proposal-pdf-studio",
    )
    db.add(business)
    db.flush()
    proposal = build_proposal(db, business, offer_package="local_pro", actor="human:test")

    rendered = render_proposal_pdf(proposal)
    first = ensure_proposal_pdf(db, business=business, proposal=proposal)
    second = ensure_proposal_pdf(db, business=business, proposal=proposal)

    assert rendered.startswith(b"%PDF-")
    assert first.id == second.id
    assert first.kind == "proposal_pdf"
    assert first.proposal_id == proposal.id
    assert first.content_type == "application/pdf"
    with store.open(first.object_key) as handle:
        assert handle.read().startswith(b"%PDF-")
