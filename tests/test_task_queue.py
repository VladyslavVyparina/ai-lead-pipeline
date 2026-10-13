import pytest

from app.services import task_queue


def test_inline_enqueue_returns_handler_job_and_metadata(monkeypatch):
    monkeypatch.setenv("TASK_QUEUE_MODE", "inline")
    task_queue.TASKS["test.inline"] = ("qa", lambda *, build_id: {"job_id": build_id, "status": "succeeded"})

    queued = task_queue.enqueue("test.inline", build_id=7)

    assert queued.job_id == 7
    assert queued.inline is True
    assert queued.queue == "qa"
    assert queued.retry["max_attempts"] == 3


def test_enqueue_rejects_non_id_payload(monkeypatch):
    monkeypatch.setenv("TASK_QUEUE_MODE", "inline")
    task_queue.TASKS["test.ids"] = ("discovery", lambda **_: {})
    with pytest.raises(ValueError, match="positive integer IDs"):
        task_queue.enqueue("test.ids", connector_id=0)


def test_celery_mode_requires_optional_dependency_or_broker(monkeypatch):
    monkeypatch.setenv("TASK_QUEUE_MODE", "celery")
    monkeypatch.delenv("CELERY_BROKER_URL", raising=False)
    task_queue.TASKS["test.celery"] = ("preview", lambda **_: {})
    with pytest.raises(RuntimeError):
        task_queue.enqueue("test.celery", business_id=1)
