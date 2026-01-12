# AutoReadME

**AI-Powered Documentation Generator for GitHub Repositories**

AutoReadME automatically analyzes your GitHub repository and generates beautiful, comprehensive documentation using GPT-4o-mini. Simply paste a repo URL and get a hosted documentation page in minutes.

---

## Features

- **One-Click Generation** — Paste a GitHub URL and get documentation instantly
- **AI-Powered Analysis** — Uses GPT-4o-mini to understand code context and generate meaningful summaries
- **Real-Time Progress** — Live status updates as your repository is processed
- **Hosted Output** — Documentation is uploaded to S3 with a shareable link (valid for 7 days)
- **Full Repository Support** — Processes all code files with smart prioritization

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              AutoReadME                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌──────────────┐      ┌──────────────┐      ┌──────────────┐              │
│   │   Frontend   │─────▶│   Backend    │─────▶│    Redis     │              │
│   │  (React/TS)  │      │  (FastAPI)   │      │   (Broker)   │              │
│   │  Port 5173   │◀─────│  Port 8000   │      │  Port 6379   │              │
│   └──────────────┘      └──────────────┘      └──────┬───────┘              │
│                                                       │                      │
│                                                       ▼                      │
│                                               ┌──────────────┐              │
│                                               │    Worker    │              │
│                                               │   (Celery)   │              │
│                                               │  LangGraph   │              │
│                                               └──────┬───────┘              │
│                                                       │                      │
│                         ┌─────────────────────────────┼─────────────────┐   │
│                         ▼                             ▼                 ▼   │
│                  ┌────────────┐             ┌──────────────┐    ┌─────────┐ │
│                  │   GitHub   │             │   OpenAI     │    │   S3    │ │
│                  │   (Clone)  │             │  GPT-4o-mini │    │ (Host)  │ │
│                  └────────────┘             └──────────────┘    └─────────┘ │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Processing Pipeline (LangGraph Agent)

1. **Clone** — Clones the GitHub repository to a temp directory
2. **Index** — Walks the directory tree and identifies code files
3. **Generate** — Processes each file with GPT-4o-mini (parallel execution)
4. **Compile** — Assembles documentation into a styled HTML page
5. **Upload** — Uploads to S3 and returns a presigned URL

---

## Quick Start

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose
- [OpenAI API Key](https://platform.openai.com/api-keys)
- AWS Account with S3 bucket (for hosting output)

### 1. Clone the Repository

```bash
git clone https://github.com/palakdesai4501/AutoReadMe.git
cd AutoReadMe
```

### 2. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` and add your credentials:

| Variable | Description | Required |
|----------|-------------|----------|
| `OPENAI_API_KEY` | Your OpenAI API key | ✅ |
| `AWS_ACCESS_KEY_ID` | AWS access key for S3 | ✅ |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key | ✅ |
| `S3_BUCKET` | S3 bucket name for hosting docs | ✅ |
| `AWS_REGION` | AWS region (default: `us-east-1`) | ❌ |

### 3. Start the Application

```bash
docker-compose up --build
```

### 4. Open the App

Navigate to **http://localhost:5173** and paste a GitHub repository URL.

---

## API Reference

### Submit Repository

```http
POST /api/submit
Content-Type: application/json

{
  "github_url": "https://github.com/username/repo"
}
```

**Response:**
```json
{
  "job_id": "uuid-string",
  "status": "queued",
  "message": "Job has been queued for processing"
}
```

### Check Status

```http
GET /api/status/{job_id}
```

**Response (Processing):**
```json
{
  "job_id": "uuid-string",
  "status": "processing",
  "stage": "analyzing"
}
```

**Response (Completed):**
```json
{
  "job_id": "uuid-string",
  "status": "completed",
  "files_processed": 42,
  "documents_generated": 38,
  "result_url": "https://your-bucket.s3.amazonaws.com/..."
}
```

### Health Check

```http
GET /health
```

---

## Project Structure

```
AutoReadMe/
├── src/
│   ├── frontend/          # React + TypeScript + Tailwind CSS
│   │   ├── src/
│   │   │   ├── components/    # Hero, StatusTracker, ResultCard
│   │   │   ├── hooks/         # useJobStatus (polling hook)
│   │   │   └── lib/           # API client (axios)
│   │   └── Dockerfile
│   │
│   ├── backend/           # FastAPI REST API
│   │   ├── app/
│   │   │   ├── api/           # Route handlers
│   │   │   └── schemas/       # Pydantic models
│   │   └── Dockerfile
│   │
│   └── worker/            # Celery + LangGraph Agent
│       ├── agent.py           # LangGraph pipeline (5 nodes)
│       ├── tasks.py           # Celery task definition
│       ├── storage.py         # S3 upload utility
│       └── Dockerfile
│
├── docker-compose.yml     # Multi-service orchestration
├── .env.example           # Environment template
└── README.md
```

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| **Frontend** | React 18, TypeScript, Tailwind CSS, Framer Motion, Vite |
| **Backend** | FastAPI, Pydantic, Uvicorn |
| **Worker** | Celery, LangGraph, LangChain, OpenAI GPT-4o-mini |
| **Broker** | Redis |
| **Storage** | AWS S3 |
| **Containerization** | Docker, Docker Compose |

---

## Local Development (Without Docker)

### Frontend

```bash
cd src/frontend
npm install
npm run dev
```

### Backend

```bash
cd src/backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Worker

```bash
cd src/worker
pip install -r requirements.txt
celery -A celery_app worker --loglevel=info
```

> **Note:** You'll need Redis running locally (`redis-server`) for the worker to connect.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | `redis://redis:6379/0` | Redis connection URL |
| `CELERY_BROKER_URL` | `redis://redis:6379/0` | Celery message broker |
| `CELERY_RESULT_BACKEND` | `redis://redis:6379/0` | Celery result storage |
| `OPENAI_API_KEY` | — | OpenAI API key (required) |
| `AWS_ACCESS_KEY_ID` | — | AWS access key (required) |
| `AWS_SECRET_ACCESS_KEY` | — | AWS secret key (required) |
| `AWS_REGION` | `us-east-1` | AWS region for S3 |
| `S3_BUCKET` | — | S3 bucket name (required) |
| `VITE_API_URL` | `http://localhost:8000` | Backend URL for frontend |

---

## Troubleshooting

### Docker daemon not running
```
Cannot connect to the Docker daemon. Is the docker daemon running?
```
→ Start Docker Desktop or run `sudo systemctl start docker`

### Worker not picking up tasks
→ Check Redis connection and ensure `CELERY_BROKER_URL` matches in both backend and worker

### S3 upload fails
→ Verify AWS credentials and ensure the S3 bucket exists with appropriate permissions

---

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

**Built with ❤️ using LangGraph and OpenAI**
