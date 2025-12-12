import os
import shutil
from celery.utils.log import get_task_logger
from celery_app import app
from agent import agent_app, set_progress_callback

logger = get_task_logger(__name__)


def update_task_progress(task_id: str, stage: str, message: str, **extra):
    """
    Update task progress using the app backend directly.
    This avoids task context issues in forked worker processes.
    """
    try:
        meta = {'stage': stage, 'message': message, **extra}
        # Use app.backend.store_result directly to avoid task context issues
        app.backend.store_result(task_id, meta, 'PROGRESS')
        logger.info(f"[{task_id}] Stage: {stage} - {message}")
    except Exception as e:
        logger.warning(f"Failed to update progress for {task_id}: {str(e)}")


@app.task(name="process_repo_task", bind=True)
def process_repo_task(self, job_id: str, github_url: str):
    """
    Main Celery task to process a documentation job.
    
    Args:
        self: Task instance (for progress updates)
        job_id: Unique identifier for the job
        github_url: GitHub repository URL to process
    
    Returns:
        Dictionary with status and result
    """
    logger.info(f"Starting documentation generation for repo: {github_url} (Job ID: {job_id})")
    
    # Create progress callback that updates Celery task state
    # Uses job_id directly since it equals task_id (set when enqueueing)
    def progress_callback(stage: str, message: str, **extra):
        update_task_progress(job_id, stage, message, **extra)
    
    # Set the global progress callback for agent nodes to use
    set_progress_callback(progress_callback)
    
    # Update task state to PROGRESS
    update_task_progress(job_id, 'starting', 'Initializing...')
    
    result = None
    local_path = None
    
    try:
        # Initialize state
        initial_state = {
            "repo_url": github_url,
            "job_id": job_id,
            "local_path": "",
            "files": [],
            "documents": [],
            "compiled_html": "",
            "final_url": "",
        }
        
        # Run the LangGraph agent (nodes will update progress via callback)
        result = agent_app.invoke(initial_state)
        local_path = result.get("local_path")
        
        # Clean up temporary directory
        if local_path and os.path.exists(local_path):
            try:
                shutil.rmtree(local_path)
                logger.info(f"Cleaned up temporary directory for job {job_id}")
            except Exception as e:
                logger.warning(f"Failed to clean up temp directory: {str(e)}")
        
        logger.info(f"Documentation generation completed for job {job_id}")
        
        final_url = result.get("final_url", "")
        logger.info(f"Final URL from result: {final_url}")
        
        response = {
            "status": "completed",
            "job_id": job_id,
            "files_processed": len(result.get("files", [])),
            "documents_generated": len(result.get("documents", [])),
            "result": result.get("documents", []),
            "result_url": final_url,
        }
        
        logger.info(f"Returning response with result_url: {response.get('result_url', 'NOT SET')}")
        
        return response
        
    except Exception as e:
        logger.error(f"Error processing job {job_id}: {str(e)}")
        
        # Update state to show error - use direct backend call
        try:
            app.backend.store_result(job_id, {'error': str(e), 'stage': 'failed'}, 'FAILURE')
        except Exception as update_err:
            logger.warning(f"Failed to update failure state: {str(update_err)}")
        
        # Clean up on error
        if local_path and os.path.exists(local_path):
            try:
                shutil.rmtree(local_path)
            except Exception as cleanup_error:
                logger.warning(f"Failed to clean up temp directory on error: {str(cleanup_error)}")
        
        return {
            "status": "failed",
            "job_id": job_id,
            "error": str(e),
        }
    finally:
        # Clear the progress callback
        set_progress_callback(None)