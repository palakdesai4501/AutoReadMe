"""
FastAPI application entry point.
Configures CORS, mounts routers, and exposes health endpoints.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import jobs

app = FastAPI(title="AutoReadME API", version="0.1.0")

# CORS: Allow all origins for development (restrict in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(jobs.router)


@app.get("/")
async def root():
    """API root - basic info endpoint."""
    return {"message": "AutoReadME API"}


@app.get("/health")
async def health():
    """Health check for container orchestration."""
    return {"status": "healthy"}
