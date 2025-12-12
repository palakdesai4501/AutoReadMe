import os
import uuid
from fastapi import APIRouter
from celery import Celery

from app.schemas import RepoSubmitRequest, JobSubmitResponse, JobStatusResponse
from fastapi import HTTPException

router = APIRouter(prefix="/api", tags=["jobs"])

# Celery client for enqueueing tasks
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
    Submit a GitHub repository URL for documentation generation.
    
    Returns a job_id that can be used to track the processing status.
    """
    job_id = str(uuid.uuid4())
    
    # Enqueue the Celery task
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
    Get the status of a documentation generation job.
    
    Returns the current status, result URL if completed, or error if failed.
    """
    try:
        # Get task result from Celery
        result = celery_client.AsyncResult(job_id)
        
        # Get the task state (this will trigger a backend check)
        state = result.state
        
        # Check if task exists
        if state == 'PENDING':
            # When a task is first queued, Celery may not have registered it in the
            # result backend yet, so result.info might be None even though the task exists.
            # Since tasks are created synchronously with specific IDs, PENDING state
            # with None info typically means the task is queued but not yet picked up.
            # Return "queued" status instead of 404 to avoid false negatives during polling.
            return JobStatusResponse(
                job_id=job_id,
                status="queued",
            )
        elif state == 'PROGRESS':
            # Job is in progress - extract progress metadata
            progress_info = result.info if result.info else {}
            if isinstance(progress_info, dict):
                return JobStatusResponse(
                    job_id=job_id,
                    status="processing",
                    stage=progress_info.get("stage"),
                    files_processed=progress_info.get("files_found"),
                    documents_generated=progress_info.get("documents_generated"),
                )
            return JobStatusResponse(
                job_id=job_id,
                status="processing",
            )
        elif state == 'SUCCESS':
            # Job completed successfully
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
            else:
                return JobStatusResponse(
                    job_id=job_id,
                    status="completed",
                )
        elif state == 'FAILURE':
            # Job failed
            error_msg = str(result.info) if result.info else "Job failed"
            return JobStatusResponse(
                job_id=job_id,
                status="failed",
                error=error_msg,
            )
        else:
            # Unknown state - return as queued to be safe
            return JobStatusResponse(
                job_id=job_id,
                status="queued",
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error checking job status: {str(e)}")

