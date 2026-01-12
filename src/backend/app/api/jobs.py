"""
Jobs API - Handles repository submission and status polling.
Communicates with Celery to enqueue tasks and fetch results.
"""
import os
import uuid
from fastapi import APIRouter, HTTPException
from celery import Celery

from app.schemas import RepoSubmitRequest, JobSubmitResponse, JobStatusResponse

router = APIRouter(prefix="/api", tags=["jobs"])

# Celery client (not a worker, just for sending tasks)
celery_client = Celery(
    "autoreadme_client",
    broker=os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0"),
    backend=os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/0"),
)

celery_client.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)


@router.post("/submit", response_model=JobSubmitResponse)
async def submit_repo(request: RepoSubmitRequest):
    """
    Submit a GitHub repository for documentation generation.
    Returns job_id for status polling.
    """
    job_id = str(uuid.uuid4())
    
    # Send task to worker queue (task_id = job_id for easy lookup)
    celery_client.send_task(
        "process_repo_task",
        args=[job_id, request.github_url],
        task_id=job_id,
    )
    
    return JobSubmitResponse(
        job_id=job_id,
        status="queued",
        message="Job has been queued for processing",
    )


@router.get("/status/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str):
    """
    Poll job status. Returns current stage, progress, or final result URL.
    """
    try:
        result = celery_client.AsyncResult(job_id)
        state = result.state
        
        if state == 'PENDING':
            # Task queued but not picked up yet
            return JobStatusResponse(job_id=job_id, status="queued")
        
        elif state == 'PROGRESS':
            # Task in progress - extract stage info
            progress_info = result.info or {}
            return JobStatusResponse(
                job_id=job_id,
                status="processing",
                stage=progress_info.get("stage"),
                files_processed=progress_info.get("files_found"),
                documents_generated=progress_info.get("documents_generated"),
            )
        
        elif state == 'SUCCESS':
            # Task completed - return result URL
            task_result = result.result
            if isinstance(task_result, dict):
                return JobStatusResponse(
                    job_id=job_id,
                    status=task_result.get("status", "completed"),
                    files_processed=task_result.get("files_processed"),
                    documents_generated=task_result.get("documents_generated"),
                    result=task_result.get("result"),
                    result_url=task_result.get("result_url"),
                    error=task_result.get("error"),
                )
            return JobStatusResponse(job_id=job_id, status="completed")
        
        elif state == 'FAILURE':
            error_msg = str(result.info) if result.info else "Job failed"
            return JobStatusResponse(job_id=job_id, status="failed", error=error_msg)
        
        else:
            # Unknown state - treat as queued
            return JobStatusResponse(job_id=job_id, status="queued")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error checking job status: {str(e)}")
