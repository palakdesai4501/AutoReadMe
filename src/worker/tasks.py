"""
Celery Task Definitions.
Contains the main process_repo_task that orchestrates documentation generation.
"""
import os
import shutil
from celery.utils.log import get_task_logger
from celery_app import app
from agent import agent_app, set_progress_callback

logger = get_task_logger(__name__)


def update_task_progress(task_id: str, stage: str, message: str, **extra):
    """Store progress update directly in Redis backend."""
    try:
        meta = {'stage': stage, 'message': message, **extra}
        app.backend.store_result(task_id, meta, 'PROGRESS')
        logger.info(f"[{task_id}] Stage: {stage} - {message}")
    except Exception as e:
        logger.warning(f"Failed to update progress for {task_id}: {str(e)}")


@app.task(name="process_repo_task", bind=True)
def process_repo_task(self, job_id: str, github_url: str):
    """
    Main documentation generation task.
    
    Pipeline:
    1. Clone repository
    2. Index code files
    3. Generate docs with GPT-4o-mini
    4. Compile HTML
    5. Upload to S3
    
    Args:
        job_id: Unique job identifier
        github_url: GitHub repository URL
    
    Returns:
        Dict with status, files_processed, documents_generated, result_url
    """
    logger.info(f"Starting job {job_id} for repo: {github_url}")
    
    # Setup progress callback for agent nodes
    def progress_callback(stage: str, message: str, **extra):
        update_task_progress(job_id, stage, message, **extra)
    
    set_progress_callback(progress_callback)
    update_task_progress(job_id, 'starting', 'Initializing...')
    
    result = None
    local_path = None
    
    try:
        # Initialize agent state
        initial_state = {
            "repo_url": github_url,
            "job_id": job_id,
            "local_path": "",
            "files": [],
            "documents": [],
            "compiled_html": "",
            "final_url": "",
        }
        
        # Run LangGraph agent pipeline
        result = agent_app.invoke(initial_state)
        local_path = result.get("local_path")
        
        # Cleanup temp directory
        if local_path and os.path.exists(local_path):
            try:
                shutil.rmtree(local_path)
                logger.info(f"Cleaned up temp directory for job {job_id}")
            except Exception as e:
                logger.warning(f"Failed to cleanup: {str(e)}")
        
        logger.info(f"Job {job_id} completed successfully")
        
        return {
            "status": "completed",
            "job_id": job_id,
            "files_processed": len(result.get("files", [])),
            "documents_generated": len(result.get("documents", [])),
            "result": result.get("documents", []),
            "result_url": result.get("final_url", ""),
        }
        
    except Exception as e:
        logger.error(f"Job {job_id} failed: {str(e)}")
        
        # Store failure state
        try:
            app.backend.store_result(job_id, {'error': str(e), 'stage': 'failed'}, 'FAILURE')
        except Exception:
            pass
        
        # Cleanup on error
        if local_path and os.path.exists(local_path):
            try:
                shutil.rmtree(local_path)
            except Exception:
                pass
        
        return {
            "status": "failed",
            "job_id": job_id,
            "error": str(e),
        }
    finally:
        set_progress_callback(None)
