# AutoReadME

Autonomous Codebase Documenter - An AI-powered service that automatically generates comprehensive documentation from GitHub repositories.

## Project Structure

```
AutoReadMe/
├── src/
│   ├── frontend/     # React + Vite + Tailwind CSS
│   ├── backend/      # FastAPI application
│   └── worker/       # Celery worker with LangGraph agent
├── infra/            # Infrastructure as Code
├── data/             # Local data storage
└── docs/             # Project documentation
```

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Git

### Setup

1. Copy the environment file:
   ```bash
   cp .env.example .env
   ```

2. Update `.env` with your configuration:
   - `OPENAI_API_KEY`: Your OpenAI API key
   - `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`: AWS credentials for S3
   - `S3_BUCKET`: Your S3 bucket name

3. Start all services:
   ```bash
   docker-compose up
   ```

### Services

- **Frontend**: http://localhost:5173
- **Backend API**: http://localhost:8000
- **Redis**: localhost:6379
- **Worker**: Runs in background processing jobs

### Health Check

Check if the backend is running:
```bash
curl http://localhost:8000/health
```

## Development

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

## License

MIT

