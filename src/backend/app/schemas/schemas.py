from pydantic import BaseModel, HttpUrl, Field


class RepoSubmitRequest(BaseModel):
    github_url: str = Field(..., description="GitHub repository URL to process")


class JobSubmitResponse(BaseModel):
    job_id: str
    status: str
    message: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    stage: str | None = None
    files_processed: int | None = None
    documents_generated: int | None = None
    result: list | None = None
    result_url: str | None = None
    error: str | None = None

