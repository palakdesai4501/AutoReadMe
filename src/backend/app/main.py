from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import jobs

app = FastAPI(title="AutoReadME API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(jobs.router)


@app.get("/")
async def root():
    return {"message": "AutoReadME API"}


@app.get("/health")
async def health():
    return {"status": "healthy"}

