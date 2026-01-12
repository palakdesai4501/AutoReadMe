"""
API Schema Definitions.
Pydantic models for request validation and response serialization.
"""
from pydantic import BaseModel, Field


class RepoSubmitRequest(BaseModel):
    """Request body for /api/submit endpoint."""
    github_url: str = Field(..., description="GitHub repository URL to process")


class JobSubmitResponse(BaseModel):
    """Response after job submission."""
    job_id: str
    status: str
    message: str


class JobStatusResponse(BaseModel):
    """Response for job status polling."""
    job_id: str
    status: str  # queued | processing | completed | failed
    stage: str | None = None  # cloning | analyzing | uploading
    files_processed: int | None = None
    documents_generated: int | None = None
    result: list | None = None
    result_url: str | None = None  # S3 presigned URL
    error: str | None = None
