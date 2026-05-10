"""Async upload endpoints using Celery.

POST /upload-slip/async → enqueues process_slip task → 202 + {task_id, status}
GET  /status/{task_id}  → polls Celery result backend for task state

Decision: same size limits as the sync endpoint (10 MB). The async path does NOT
skip validation — it just defers the heavy OCR+detection work to a Celery worker.
If the file is invalid (empty, too large), we reject immediately (before enqueuing)
to avoid filling the queue with unprocessable tasks.

Decision: /status/{task_id} returns 200 for all states including FAILURE — the HTTP
status reflects "we found status info about this task_id", not the task result.
PENDING is returned for unknown task_ids (Celery's default). Callers check `status`
field to distinguish outcomes.
"""

from __future__ import annotations

import base64
from typing import Any

from celery.result import AsyncResult
from fastapi import APIRouter, File, HTTPException, UploadFile, status

from celery_app import celery_app

router = APIRouter(tags=["upload-async"])

MAX_SIZE = 10 * 1024 * 1024  # 10 MB


@router.post(
    "/upload-slip/async",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Enqueue a comprobante upload for async processing",
    response_description="Task enqueued. Poll /status/{task_id} for result.",
)
async def upload_slip_async(file: UploadFile = File(...)) -> dict[str, str]:
    """Enqueue a comprobante upload for async processing via Celery.

    Returns task_id immediately. Use GET /status/{task_id} to poll for result.

    Raises:
        400: Empty file.
        413: File exceeds 10 MB limit.
    """
    file_bytes = await file.read()

    if len(file_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty file",
        )
    if len(file_bytes) > MAX_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large (limit: {MAX_SIZE} bytes)",
        )

    # base64-encode for JSON-serializable Celery args
    file_b64 = base64.b64encode(file_bytes).decode()
    task = celery_app.send_task(
        "tasks.process_slip",
        args=[
            file_b64,
            file.filename or "upload.bin",
            file.content_type or "application/octet-stream",
        ],
    )
    return {"task_id": task.id, "status": "queued"}


@router.get(
    "/status/{task_id}",
    summary="Poll the status of an async upload task",
)
async def get_task_status(task_id: str) -> dict[str, Any]:
    """Poll the status of an async upload task.

    Possible states: PENDING, STARTED, SUCCESS, FAILURE, RETRY

    On SUCCESS: response contains `result` with ComprobanteResponse fields.
    On FAILURE: response contains `error` with the exception message.
    PENDING is returned for unknown task_ids (Celery default behavior).
    """
    result = AsyncResult(task_id, app=celery_app)
    state = result.state

    response: dict[str, Any] = {"task_id": task_id, "status": state}

    if state == "SUCCESS":
        response["result"] = result.get()
    elif state == "FAILURE":
        response["error"] = str(result.result)

    return response
