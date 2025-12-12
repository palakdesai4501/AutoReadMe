"""
AI Agent Core - LangGraph implementation for repository documentation.
"""

import os
import tempfile
import shutil
import html
import json
import re
from typing import TypedDict, List
from typing_extensions import Annotated
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import git
from langgraph.graph import StateGraph, END
from storage import upload_to_s3

# Monkey patch to fix langchain-openai 0.1.7 compatibility with newer httpx/openai SDK
# The issue: httpx>=0.28.0 removed 'proxies' argument, but langchain-openai 0.1.7 still passes it
# Reference: https://community.openai.com/t/error-with-openai-1-56-0-client-init-got-an-unexpected-keyword-argument-proxies/1040332
# Must patch BEFORE importing ChatOpenAI

# Patch httpx.Client first (where the actual error occurs)
try:
    import httpx
    
    _original_httpx_client_init = httpx.Client.__init__
    
    def _patched_httpx_client_init(self, *args, **kwargs):
        # Remove proxies parameter (not supported in httpx>=0.28.0)
        kwargs.pop('proxies', None)
        return _original_httpx_client_init(self, *args, **kwargs)
    
    httpx.Client.__init__ = _patched_httpx_client_init
    
    # Also patch AsyncClient if it exists
    if hasattr(httpx, 'AsyncClient'):
        _original_async_client_init = httpx.AsyncClient.__init__
        
        def _patched_async_client_init(self, *args, **kwargs):
            kwargs.pop('proxies', None)
            return _original_async_client_init(self, *args, **kwargs)
        
        httpx.AsyncClient.__init__ = _patched_async_client_init
except (ImportError, AttributeError):
    pass

# Patch OpenAI client as well
try:
    import openai
    from openai import OpenAI as _OriginalOpenAI
    
    # Create a wrapper class that filters proxies
    class _PatchedOpenAI(_OriginalOpenAI):
        def __init__(self, *args, **kwargs):
            # Remove proxies parameter (not supported in newer openai SDK)
            kwargs.pop('proxies', None)
            super().__init__(*args, **kwargs)
    
    # Replace OpenAI in the openai module
    openai.OpenAI = _PatchedOpenAI
except (ImportError, AttributeError):
    pass

# Now import ChatOpenAI after patching
from langchain_openai import ChatOpenAI

# Also patch ChatOpenAI to prevent it from passing proxies
try:
    _original_chat_openai_init = ChatOpenAI.__init__
    
    def _patched_chat_openai_init(self, *args, **kwargs):
        # Remove proxies if passed to ChatOpenAI
        kwargs.pop('proxies', None)
        return _original_chat_openai_init(self, *args, **kwargs)
    
    ChatOpenAI.__init__ = _patched_chat_openai_init
except (AttributeError, TypeError):
    pass


class AgentState(TypedDict):
    """State managed by the LangGraph agent."""
    repo_url: str
    job_id: str
    local_path: str
    files: List[str]
    documents: Annotated[List[dict], "List of {'file': str, 'summary': str, 'dependencies': List[str]} dictionaries"]
    compiled_html: str
    final_url: str


# Global progress callback - set by the Celery task before invoking agent
_progress_callback = None


def set_progress_callback(callback):
    """Set the global progress callback function."""
    global _progress_callback
    _progress_callback = callback


def update_progress(stage: str, message: str, **extra):
    """Update progress if callback is set."""
    global _progress_callback
    if _progress_callback:
        _progress_callback(stage=stage, message=message, **extra)


def clone_repo(state: AgentState) -> AgentState:
    """
    Node 1: Clone the repository to a temporary directory.
    
    Args:
        state: Current agent state
        
    Returns:
        Updated state with local_path set
    """
    job_id = state["job_id"]
    repo_url = state["repo_url"]
    
    # Update progress
    update_progress('cloning', 'Cloning repository...')
    print(f"[CLONE_NODE] Starting clone for job {job_id}")
    
    # Create temporary directory for this job
    temp_dir = tempfile.mkdtemp(prefix=f"autoreadme_{job_id}_")
    
    try:
        # Clone the repository
        repo = git.Repo.clone_from(repo_url, temp_dir)
        
        return {
            **state,
            "local_path": temp_dir,
        }
    except Exception as e:
        # Clean up on error
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        raise Exception(f"Failed to clone repository: {str(e)}")


def index_files(state: AgentState) -> AgentState:
    """
    Node 2: Walk through the directory and index code files.
    
    Excludes .git, node_modules, and binary files.
    
    Args:
        state: Current agent state
        
    Returns:
        Updated state with files list populated
    """
    # Update progress
    update_progress('analyzing', 'Indexing repository files...')
    print(f"[INDEX_NODE] Starting file indexing for job {state['job_id']}")
    
    local_path = state["local_path"]
    files = []
    
    if not os.path.exists(local_path):
        print(f"[INDEX_NODE] ERROR: Local path does not exist: {local_path}")
        raise Exception(f"Local path does not exist: {local_path}")
    
    # Directories and patterns to exclude
    exclude_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", "env", ".env"}
    exclude_extensions = {
        ".pyc", ".pyo", ".pyd", ".so", ".dll", ".exe", ".bin",
        ".jpg", ".jpeg", ".png", ".gif", ".svg", ".ico",
        ".pdf", ".zip", ".tar", ".gz", ".mp4", ".mp3",
    }
    
    # Supported code file extensions
    code_extensions = {
        ".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs",
        ".java", ".cpp", ".c", ".h", ".hpp", ".cs", ".rb",
        ".php", ".swift", ".kt", ".scala", ".md", ".json",
        ".yaml", ".yml", ".toml", ".xml", ".html", ".css",
    }
    
    path = Path(local_path)
    
    for file_path in path.rglob("*"):
        # Skip directories
        if file_path.is_dir():
            continue
        
        # Skip excluded directories
        if any(excluded in file_path.parts for excluded in exclude_dirs):
            continue
        
        # Skip binary files and check for code extensions
        file_ext = file_path.suffix.lower()
        if file_ext in exclude_extensions:
            continue
        
        # Only include code files
        if file_ext in code_extensions or file_path.name in {"Dockerfile", "Makefile", "README.md"}:
            # Store relative path from repo root
            rel_path = str(file_path.relative_to(path))
            files.append(rel_path)
    
    print(f"[INDEX_NODE] Found {len(files)} files to process")
    if len(files) == 0:
        print(f"[INDEX_NODE] WARNING: No files found in repository at {local_path}")
    
    return {
        **state,
        "files": files,
    }


def prioritize_files(files: List[str]) -> List[str]:
    """
    Prioritize files for documentation generation.
    
    Priority order:
    1. README.md and documentation files
    2. Main entry points (main.py, app.py, index.js, etc.)
    3. Configuration files (package.json, requirements.txt, Dockerfile, etc.)
    4. Core source files (src/, app/, lib/, components/)
    5. Other files
    
    Args:
        files: List of file paths
        
    Returns:
        Prioritized list of files
    """
    priority_files = []
    main_files = []
    config_files = []
    core_files = []
    other_files = []
    
    # Priority patterns
    doc_patterns = ["README", "readme", "CHANGELOG", "LICENSE", "CONTRIBUTING"]
    main_patterns = ["main.py", "app.py", "index.js", "index.ts", "index.tsx", 
                     "main.js", "main.ts", "server.py", "app.js", "app.ts"]
    config_patterns = ["package.json", "requirements.txt", "Dockerfile", "docker-compose",
                      "setup.py", "pyproject.toml", "Cargo.toml", "go.mod", "pom.xml",
                      "tsconfig.json", "webpack.config", "vite.config", "tailwind.config",
                      "cloudbuild.yaml", ".github/workflows"]
    
    for file_path in files:
        file_lower = file_path.lower()
        file_name = Path(file_path).name.lower()
        
        # Check documentation files
        if any(pattern in file_lower for pattern in doc_patterns):
            priority_files.append(file_path)
        # Check main entry points
        elif any(pattern == file_name for pattern in main_patterns):
            main_files.append(file_path)
        # Check config files
        elif any(pattern in file_lower for pattern in config_patterns):
            config_files.append(file_path)
        # Check core source directories
        elif any(part in file_path.lower() for part in ["/src/", "/app/", "/lib/", "/components/", "/core/"]):
            core_files.append(file_path)
        else:
            other_files.append(file_path)
    
    # Combine in priority order
    prioritized = priority_files + main_files + config_files + core_files + other_files
    return prioritized


def process_single_file(file_path: str, local_path: str, llm) -> dict:
    """
    Process a single file and extract summary and dependencies.
    
    Args:
        file_path: Relative path to the file
        local_path: Root path of the repository
        llm: Initialized LLM instance
        
    Returns:
        Dictionary with 'file', 'summary', and 'dependencies' keys
    """
    full_path = Path(local_path) / file_path
    
    try:
        # Read file content
        with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        
        # Skip empty files
        if not content.strip():
            print(f"[PROCESS_FILE] Skipping empty file: {file_path}")
            return None
        
        # Truncate very large files
        max_chars = 10000
        is_truncated = False
        if len(content) > max_chars:
            content = content[:max_chars] + "\n... (truncated for brevity)"
            is_truncated = True
        
        # Determine file type for better context
        file_ext = Path(file_path).suffix.lower()
        file_type = file_ext[1:] if file_ext else "text"
        
        # Extract import statements for better dependency detection
        imports = []
        if file_ext == '.py':
            # Python imports: import x, from x import y, from .x import y
            import_pattern = r'(?:^|\n)(?:from\s+([\.\w]+)\s+)?import\s+([\w\s,]+)'
            matches = re.findall(import_pattern, content, re.MULTILINE)
            for match in matches:
                module = match[0] if match[0] else match[1].split(',')[0].strip()
                if module and not module.startswith('.'):
                    # External package, skip
                    continue
                elif module.startswith('.'):
                    # Relative import - convert to potential file path
                    base_dir = str(Path(file_path).parent)
                    module_path = module.replace('.', '/').lstrip('/')
                    imports.append(f"{base_dir}/{module_path}.py" if base_dir != '.' else f"{module_path}.py")
        elif file_ext in ['.js', '.jsx', '.ts', '.tsx']:
            # JavaScript/TypeScript imports: import x from './y', import {x} from '../z'
            import_pattern = r'import\s+.*?from\s+["\']([\.\/\w\-]+)["\']'
            matches = re.findall(import_pattern, content)
            for match in matches:
                if match.startswith('.'):
                    # Relative import
                    base_dir = str(Path(file_path).parent)
                    rel_path = match
                    # Resolve relative path
                    if rel_path.endswith('.js') or rel_path.endswith('.ts') or rel_path.endswith('.jsx') or rel_path.endswith('.tsx'):
                        imports.append(str((Path(local_path) / base_dir / rel_path).relative_to(Path(local_path))))
                    else:
                        # Try common extensions
                        for ext in ['.ts', '.tsx', '.js', '.jsx']:
                            potential = str((Path(local_path) / base_dir / (rel_path + ext)).relative_to(Path(local_path)))
                            imports.append(potential)
        
        imports_str = ', '.join(imports[:10]) if imports else 'None found'
        
        # Prompt for JSON output with summary and dependencies
        prompt = f"""Analyze the following code file and return ONLY a valid JSON object (no markdown, no code blocks, no explanations).

File: {file_path}
File Type: {file_type}
{'Note: File content was truncated due to length' if is_truncated else ''}

Code:
```{file_type}
{content}
```

Detected import statements (for reference): {imports_str}

Return a JSON object with this exact structure:
{{
  "summary": "A clear 2-4 sentence description of what this file does, its purpose, and key components",
  "dependencies": ["relative/path/to/file1.py", "relative/path/to/file2.js"]
}}

CRITICAL: For dependencies array:
1. Extract ALL internal file imports from the code (look for import/from statements)
2. Convert import paths to actual file paths relative to repository root
3. Include files that are imported, required, or referenced in the code
4. DO NOT include external npm/pip packages (like 'react', 'flask', 'express')
5. DO NOT include standard library modules
6. Use the exact relative path format as files appear in the repository
7. If you see "from utils import x", find the actual utils.py file path
8. If you see "import ./components/Button", convert to the actual file path

Examples:
- "from app.models import User" -> ["app/models.py"] or ["app/models/__init__.py"]
- "import {{ Button }} from './Button'" -> ["frontend/src/components/Button.tsx"]
- "from .config import settings" -> ["src/config.py"] (relative to current file's directory)

Return ONLY the JSON object, nothing else."""

        try:
            response = llm.invoke(prompt)
            response_text = response.content if hasattr(response, 'content') else str(response)
            
            if not response_text or not response_text.strip():
                print(f"[PROCESS_FILE] Empty response from LLM for {file_path}")
                return {
                    "file": file_path,
                    "summary": "No summary available - LLM returned empty response.",
                    "dependencies": [],
                }
            
            # Strip markdown code blocks if present
            response_text = response_text.strip()
            if response_text.startswith("```"):
                # Remove ```json or ``` markers
                response_text = re.sub(r'^```(?:json)?\s*', '', response_text, flags=re.MULTILINE)
                response_text = re.sub(r'```\s*$', '', response_text, flags=re.MULTILINE)
                response_text = response_text.strip()
            
            # Parse JSON with fallback
            try:
                parsed = json.loads(response_text)
                summary = parsed.get("summary", "No summary available.")
                dependencies = parsed.get("dependencies", [])
                
                # Ensure dependencies is a list
                if not isinstance(dependencies, list):
                    dependencies = []
                
                # Ensure summary is not empty
                if not summary or not summary.strip():
                    summary = "No summary available."
                
                return {
                    "file": file_path,
                    "summary": summary,
                    "dependencies": dependencies,
                }
            except json.JSONDecodeError as e:
                # Fallback: treat response as summary with no dependencies
                print(f"[PROCESS_FILE] JSON parse error for {file_path}: {e}. Response preview: {response_text[:200]}")
                # Use the response as summary even if not JSON
                summary_text = response_text if response_text else "No summary available."
                return {
                    "file": file_path,
                    "summary": summary_text,
                    "dependencies": [],
                }
        except Exception as e:
            print(f"[PROCESS_FILE] LLM call failed for {file_path}: {str(e)}")
            import traceback
            traceback.print_exc()
            # Return a document even if LLM fails, so we don't lose the file
            return {
                "file": file_path,
                "summary": f"Error processing file: {str(e)}",
                "dependencies": [],
            }
            
    except Exception as e:
        print(f"[PROCESS_FILE] Error processing {file_path}: {str(e)}")
        import traceback
        traceback.print_exc()
        return None


def generate_docs(state: AgentState) -> AgentState:
    """
    Node 3: Generate documentation for each file using GPT-4o-mini.
    
    Processes ALL files in parallel using ThreadPoolExecutor.
    
    Args:
        state: Current agent state
        
    Returns:
        Updated state with documents list populated (each with summary and dependencies)
    """
    # Update progress
    update_progress('analyzing', f'Generating documentation for {len(state["files"])} files...', 
                   files_found=len(state["files"]))
    print(f"[GENERATE_DOCS] Starting doc generation for job {state['job_id']}")
    
    local_path = state["local_path"]
    files = state["files"]
    documents = []
    
    # Process ALL files (no limit)
    files_to_process = files
    
    if len(files_to_process) == 0:
        print(f"[GENERATE_DOCS] ERROR: No files to process! Files list is empty.")
        return {
            **state,
            "documents": [],
        }
    
    print(f"[GENERATE_DOCS] Processing {len(files_to_process)} files in parallel")
    
    # Initialize LLM (GPT-4o-mini for cost efficiency)
    # ChatOpenAI will automatically read OPENAI_API_KEY from environment
    llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0.3,
    )
    
    # Process files in parallel using ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=10) as executor:
        # Submit all tasks
        future_to_file = {
            executor.submit(process_single_file, file_path, local_path, llm): file_path
            for file_path in files_to_process
        }
        
        # Collect results as they complete
        completed = 0
        for future in as_completed(future_to_file):
            file_path = future_to_file[future]
            completed += 1
            
            try:
                result = future.result()
                if result:
                    documents.append(result)
                    print(f"[GENERATE_DOCS] Successfully processed: {file_path}")
                else:
                    print(f"[GENERATE_DOCS] No result for: {file_path} (returned None)")
                
                # Update progress periodically
                if completed % 5 == 0:
                    update_progress('analyzing', 
                                  f'Processed {completed}/{len(files_to_process)} files...',
                                  files_processed=completed)
            except Exception as e:
                print(f"[GENERATE_DOCS] Error getting result for {file_path}: {str(e)}")
                import traceback
                traceback.print_exc()
                continue
    
    print(f"[GENERATE_DOCS] Completed processing {len(documents)} files")
    
    if len(documents) == 0:
        print(f"[GENERATE_DOCS] WARNING: No documents were generated! Total files processed: {len(files_to_process)}")
    
    return {
        **state,
        "documents": documents,
    }


def compile_artifact(state: AgentState) -> AgentState:
    """
    Node 4: Compile documents into a single HTML file with table of contents.
    
    Args:
        state: Current agent state
        
    Returns:
        Updated state with compiled HTML content
    """
    # Update progress
    update_progress('uploading', 'Compiling documentation...', 
                   documents_generated=len(state["documents"]))
    print(f"[COMPILE_NODE] Starting compilation for job {state['job_id']}")
    documents = state["documents"]
    repo_url = state["repo_url"]
    job_id = state["job_id"]
    
    # Extract repo name from URL for display
    repo_name = repo_url.split("/")[-1].replace(".git", "") if repo_url else "Repository"
    
    # Build table of contents
    toc_items = []
    doc_sections = []
    
    # Check if documents list is empty
    if not documents:
        print(f"[COMPILE_NODE] WARNING: No documents to compile! Documents list is empty.")
        doc_sections.append('''
        <section class="doc-section">
            <h2>No Documentation Generated</h2>
            <div class="doc-content">
                <p>No files were successfully processed. This could be due to:</p>
                <ul style="margin-left: 2rem; margin-top: 1rem;">
                    <li>No code files found in the repository</li>
                    <li>All files failed to process</li>
                    <li>Repository is empty or contains only excluded files</li>
                </ul>
            </div>
        </section>
        ''')
    else:
        for idx, doc in enumerate(documents, 1):
            file_path = doc.get("file", f"file_{idx}")
            doc_text = doc.get("summary", doc.get("doc", ""))  # Support both 'summary' and 'doc' keys
            
            # Skip if no content
            if not doc_text or not doc_text.strip():
                print(f"[COMPILE_NODE] WARNING: Skipping {file_path} - no content")
                continue
            
            # Escape HTML to prevent XSS
            escaped_file_path = html.escape(file_path)
            escaped_doc_text = html.escape(doc_text)
            
            # Create anchor ID from file path
            anchor_id = f"doc-{idx}"
            toc_items.append(f'<li><a href="#{anchor_id}">{escaped_file_path}</a></li>')
            
            # Create section HTML
            doc_sections.append(f'''
            <section id="{anchor_id}" class="doc-section">
                <h2>{escaped_file_path}</h2>
                <div class="doc-content">
                    <p>{escaped_doc_text}</p>
                </div>
            </section>
            ''')
    
    # Compile full HTML document
    html_content = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{repo_name} - Documentation</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            line-height: 1.6;
            background-color: #F5E7C6;
            color: #222222;
        }}
        .sidebar {{
            position: fixed;
            left: 0;
            top: 0;
            width: 280px;
            height: 100vh;
            overflow-y: auto;
            background-color: #FFFFFF;
            border-right: 1px solid #222222;
            padding: 2rem 1rem;
            z-index: 100;
        }}
        .sidebar h1 {{
            font-size: 1.5rem;
            font-weight: bold;
            margin-bottom: 1rem;
            color: #FF6D1F;
        }}
        .sidebar ul {{
            list-style: none;
            padding: 0;
            margin: 0;
        }}
        .sidebar li {{
            margin-bottom: 0.5rem;
        }}
        .sidebar a {{
            color: #222222;
            text-decoration: none;
            padding: 0.5rem;
            display: block;
            border-radius: 0.25rem;
            transition: background 0.2s;
            word-wrap: break-word;
            overflow-wrap: break-word;
        }}
        .sidebar a:hover {{
            background-color: #F5E7C6;
            color: #FF6D1F;
        }}
        .main-content {{
            margin-left: 280px;
            padding: 2rem 4rem;
            max-width: 1200px;
            background-color: #F5E7C6;
        }}
        .header {{
            border-bottom: 2px solid #222222;
            padding-bottom: 1rem;
            margin-bottom: 2rem;
        }}
        .header h1 {{
            font-size: 2rem;
            font-weight: bold;
            color: #222222;
        }}
        .header p {{
            color: #222222;
            opacity: 0.7;
            margin-top: 0.5rem;
        }}
        .header a {{
            color: #FF6D1F;
            text-decoration: none;
        }}
        .header a:hover {{
            text-decoration: underline;
        }}
        .doc-section {{
            margin-bottom: 3rem;
            padding-bottom: 2rem;
            border-bottom: 1px solid #222222;
        }}
        .doc-section h2 {{
            font-size: 1.5rem;
            font-weight: 600;
            color: #222222;
            margin-bottom: 1rem;
        }}
        .doc-content {{
            color: #222222;
            line-height: 1.8;
        }}
        .doc-content p {{
            margin-bottom: 1rem;
        }}
        @media (max-width: 768px) {{
            .sidebar {{
                position: relative;
                width: 100%;
                height: auto;
                border-right: none;
                border-bottom: 1px solid #222222;
            }}
            .main-content {{
                margin-left: 0;
                padding: 1rem;
            }}
        }}
    </style>
</head>
<body>
    <div class="sidebar">
        <h1>Table of Contents</h1>
        <ul>
            {''.join(toc_items) if toc_items else '<li style="color: #666; padding: 0.5rem;">No files available</li>'}
        </ul>
    </div>
    
    <div class="main-content">
        <div class="header">
            <h1>{repo_name}</h1>
            <p>Generated Documentation • {datetime.now().strftime("%B %d, %Y at %I:%M %p")}</p>
            <p><a href="{repo_url}" target="_blank" class="text-blue-600 hover:underline">View Repository</a></p>
        </div>
        
        {''.join(doc_sections)}
    </div>
</body>
    </html>'''
    
    print(f"[COMPILE_NODE] Compiled HTML: {len(html_content)} characters")
    
    return {
        **state,
        "compiled_html": html_content,
    }


def upload_artifact(state: AgentState) -> AgentState:
    """
    Node 5: Upload compiled HTML to S3 and get public URL.
    
    Args:
        state: Current agent state
        
    Returns:
        Updated state with final_url set
    """
    # Update progress
    update_progress('uploading', 'Uploading documentation to storage...')
    print(f"[UPLOAD_NODE] Starting upload for job {state['job_id']}")
    compiled_html = state.get("compiled_html", "")
    job_id = state["job_id"]
    
    if not compiled_html:
        print(f"[UPLOAD_NODE] ERROR: No compiled HTML content")
        raise Exception("No compiled HTML content to upload")
    
    print(f"[UPLOAD_NODE] Compiled HTML length: {len(compiled_html)} characters")
    
    # Generate S3 filename: {job_id}/index.html
    filename = f"{job_id}/index.html"
    
    try:
        print(f"[UPLOAD_NODE] Uploading to S3: {filename}")
        # Upload to S3 with proper content type
        public_url = upload_to_s3(
            content=compiled_html,
            filename=filename,
            content_type="text/html"
        )
        print(f"[UPLOAD_NODE] Successfully uploaded to S3: {public_url}")
        
        return {
            **state,
            "final_url": public_url,
        }
    except Exception as e:
        print(f"[UPLOAD_NODE] ERROR: S3 upload failed: {str(e)}")
        raise Exception(f"Failed to upload artifact to S3: {str(e)}")


def build_agent_graph():
    """
    Build and compile the LangGraph agent workflow.
    
    Returns:
        Compiled LangGraph application
    """
    # Create the graph
    workflow = StateGraph(AgentState)
    
    # Add nodes
    workflow.add_node("clone", clone_repo)
    workflow.add_node("index", index_files)
    workflow.add_node("generate", generate_docs)
    workflow.add_node("compile", compile_artifact)
    workflow.add_node("upload", upload_artifact)
    
    # Add edges
    workflow.set_entry_point("clone")
    workflow.add_edge("clone", "index")
    workflow.add_edge("index", "generate")
    workflow.add_edge("generate", "compile")
    workflow.add_edge("compile", "upload")
    workflow.add_edge("upload", END)
    
    # Compile the graph
    app = workflow.compile()
    
    return app


# Create the compiled graph instance
agent_app = build_agent_graph()
