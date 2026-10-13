"""Optional background-task boundary for the lead pipeline.

Celery is deliberately optional: a fresh local checkout (and the test suite)
executes the same handlers inline.  A deployment enables Celery simply by
setting ``TASK_QUEUE_MODE=celery`` and installing/configuring Celery; no
request handler needs to know which mode is in use.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import asdict, dataclass
from typing import Any, Callable


DISCOVERY_QUEUE = "discovery"
CRAWL_RESEARCH_QUEUE = "crawl_research"
PREVIEW_QUEUE = "preview"
QA_QUEUE = "qa"

TASKS: dict[str, tuple[str, Callable[..., dict[str, Any]]]] = {}


@dataclass(frozen=True)
class EnqueueResult:
    """Stable response returned by both inline and Celery enqueue paths."""

    job_id: str | int
    task_name: str
    queue: str
    status: str
    inline: bool
    retry: dict[str, int]
    result: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def register_task(name: str, queue: str) -> Callable[[Callable[..., dict[str, Any]]], Callable[..., dict[str, Any]]]:
    def decorator(handler: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
        TASKS[name] = (queue, handler)
        return handler

    return decorator


def queue_mode() -> str:
    """Return the explicitly selected mode, safely falling back to inline."""
    return os.getenv("TASK_QUEUE_MODE", "inline").strip().lower()


def retry_metadata() -> dict[str, int]:
    return {
        "max_attempts": int(os.getenv("TASK_MAX_ATTEMPTS", "3")),
        "backoff_seconds": int(os.getenv("TASK_RETRY_BACKOFF_SECONDS", "30")),
    }


def enqueue(task_name: str, /, **payload: int) -> EnqueueResult:
    """Enqueue an ID-only payload or execute it inline.

    Keeping payload values to scalar IDs prevents a queue from becoming a
    shadow database of raw lead data or mutable business facts.
    """
    if task_name not in TASKS:
        # Task registration is import-driven, but API callers should not need
        # to import the worker module themselves.
        import app.worker  # noqa: F401
    if task_name not in TASKS:
        raise ValueError(f"unknown pipeline task: {task_name}")
    if any(not isinstance(value, int) or value < 1 for value in payload.values()):
        raise ValueError("background task payloads must contain positive integer IDs only")

    queue, handler = TASKS[task_name]
    retry = retry_metadata()
    if queue_mode() != "celery":
        result = handler(**payload)
        return EnqueueResult(
            job_id=result.get("job_id", f"inline-{uuid.uuid4()}"),
            task_name=task_name,
            queue=queue,
            status=result.get("status", "succeeded"),
            inline=True,
            retry=retry,
            result=result,
        )

    celery = get_celery_app()
    async_result = celery.send_task(task_name, kwargs=payload, queue=queue)
    return EnqueueResult(
        job_id=async_result.id,
        task_name=task_name,
        queue=queue,
        status="queued",
        inline=False,
        retry=retry,
    )


def get_celery_app():
    """Construct Celery lazily so it remains an optional production extra."""
    try:
        from celery import Celery
    except ImportError as exc:  # pragma: no cover - exercised in deployments
        raise RuntimeError(
            "TASK_QUEUE_MODE=celery requires the optional 'celery' package"
        ) from exc

    broker_url = os.getenv("CELERY_BROKER_URL", "").strip()
    if not broker_url:
        raise RuntimeError("TASK_QUEUE_MODE=celery requires CELERY_BROKER_URL")
    return Celery(
        "ai_lead",
        broker=broker_url,
        backend=os.getenv("CELERY_RESULT_BACKEND", broker_url),
        include=["app.worker"],
    )
