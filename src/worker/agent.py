"""
LangGraph Agent - Documentation generation pipeline.

Pipeline Nodes:
1. clone_repo    - Clone GitHub repository
2. index_files   - Walk directory and collect code files
3. generate_docs - Process files with GPT-4o-mini
4. compile_artifact - Build HTML documentation
5. upload_artifact  - Upload to S3

Author: AutoReadME Team
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

# --- Monkey Patches for httpx/openai compatibility ---
# Fixes langchain-openai 0.1.7 compatibility with newer httpx/openai SDK
# Reference: https://community.openai.com/t/error-with-openai-1-56-0-client-init-got-an-unexpected-keyword-argument-proxies/1040332

try:
    import httpx
    _original_httpx_client_init = httpx.Client.__init__
    
    def _patched_httpx_client_init(self, *args, **kwargs):
        kwargs.pop('proxies', None)
        return _original_httpx_client_init(self, *args, **kwargs)
    
    httpx.Client.__init__ = _patched_httpx_client_init
    
    if hasattr(httpx, 'AsyncClient'):
        _original_async_client_init = httpx.AsyncClient.__init__
        def _patched_async_client_init(self, *args, **kwargs):
            kwargs.pop('proxies', None)
            return _original_async_client_init(self, *args, **kwargs)
        httpx.AsyncClient.__init__ = _patched_async_client_init
except (ImportError, AttributeError):
    pass

try:
    import openai
    from openai import OpenAI as _OriginalOpenAI
    
    class _PatchedOpenAI(_OriginalOpenAI):
        def __init__(self, *args, **kwargs):
            kwargs.pop('proxies', None)
            super().__init__(*args, **kwargs)
    
    openai.OpenAI = _PatchedOpenAI
except (ImportError, AttributeError):
    pass

from langchain_openai import ChatOpenAI

try:
    _original_chat_openai_init = ChatOpenAI.__init__
    def _patched_chat_openai_init(self, *args, **kwargs):
        kwargs.pop('proxies', None)
        return _original_chat_openai_init(self, *args, **kwargs)
    ChatOpenAI.__init__ = _patched_chat_openai_init
except (AttributeError, TypeError):
    pass

# --- End Monkey Patches ---


class AgentState(TypedDict):
    """State passed between pipeline nodes."""
    repo_url: str
    job_id: str
    local_path: str
    files: List[str]
    documents: Annotated[List[dict], "List of {file, summary, dependencies}"]
    compiled_html: str
    final_url: str


# Global progress callback (set by Celery task)
_progress_callback = None


def set_progress_callback(callback):
    """Set callback for progress updates."""
    global _progress_callback
    _progress_callback = callback


def update_progress(stage: str, message: str, **extra):
    """Update progress if callback is set."""
    if _progress_callback:
        _progress_callback(stage=stage, message=message, **extra)


# =============================================================================
# Node 1: Clone Repository
# =============================================================================

def clone_repo(state: AgentState) -> AgentState:
    """Clone GitHub repository to temp directory."""
    job_id = state["job_id"]
    repo_url = state["repo_url"]
    
    update_progress('cloning', 'Cloning repository...')
    print(f"[CLONE_NODE] Starting clone for job {job_id}")
    
    temp_dir = tempfile.mkdtemp(prefix=f"autoreadme_{job_id}_")
    
    try:
        git.Repo.clone_from(repo_url, temp_dir)
        return {**state, "local_path": temp_dir}
    except Exception as e:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        raise Exception(f"Failed to clone repository: {str(e)}")


# =============================================================================
# Node 2: Index Files
# =============================================================================

def index_files(state: AgentState) -> AgentState:
    """Walk directory tree and collect code files."""
    update_progress('analyzing', 'Indexing repository files...')
    print(f"[INDEX_NODE] Starting file indexing for job {state['job_id']}")
    
    local_path = state["local_path"]
    
    if not os.path.exists(local_path):
        raise Exception(f"Local path does not exist: {local_path}")
    
    # Exclusion patterns
    exclude_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", "env", ".env"}
    exclude_extensions = {
        ".pyc", ".pyo", ".pyd", ".so", ".dll", ".exe", ".bin",
        ".jpg", ".jpeg", ".png", ".gif", ".svg", ".ico",
        ".pdf", ".zip", ".tar", ".gz", ".mp4", ".mp3",
    }
    
    # Supported code files
    code_extensions = {
        ".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs",
        ".java", ".cpp", ".c", ".h", ".hpp", ".cs", ".rb",
        ".php", ".swift", ".kt", ".scala", ".md", ".json",
        ".yaml", ".yml", ".toml", ".xml", ".html", ".css",
    }
    
    files = []
    path = Path(local_path)
    
    for file_path in path.rglob("*"):
        if file_path.is_dir():
            continue
        if any(excluded in file_path.parts for excluded in exclude_dirs):
            continue
        
        file_ext = file_path.suffix.lower()
        if file_ext in exclude_extensions:
            continue
        
        if file_ext in code_extensions or file_path.name in {"Dockerfile", "Makefile", "README.md"}:
            rel_path = str(file_path.relative_to(path))
            files.append(rel_path)
    
    print(f"[INDEX_NODE] Found {len(files)} files to process")
    return {**state, "files": files}


# =============================================================================
# Node 3: Generate Documentation
# =============================================================================

def prioritize_files(files: List[str]) -> List[str]:
    """Sort files by priority: docs → entry points → config → source → other."""
    priority_files, main_files, config_files, core_files, other_files = [], [], [], [], []
    
    doc_patterns = ["README", "readme", "CHANGELOG", "LICENSE", "CONTRIBUTING"]
    main_patterns = ["main.py", "app.py", "index.js", "index.ts", "index.tsx", 
                     "main.js", "main.ts", "server.py", "app.js", "app.ts"]
    config_patterns = ["package.json", "requirements.txt", "Dockerfile", "docker-compose",
                      "setup.py", "pyproject.toml", "Cargo.toml", "go.mod", "pom.xml",
                      "tsconfig.json", "webpack.config", "vite.config", "tailwind.config"]
    
    for file_path in files:
        file_lower = file_path.lower()
        file_name = Path(file_path).name.lower()
        
        if any(p in file_lower for p in doc_patterns):
            priority_files.append(file_path)
        elif any(p == file_name for p in main_patterns):
            main_files.append(file_path)
        elif any(p in file_lower for p in config_patterns):
            config_files.append(file_path)
        elif any(part in file_path.lower() for part in ["/src/", "/app/", "/lib/", "/components/", "/core/"]):
            core_files.append(file_path)
        else:
            other_files.append(file_path)
    
    return priority_files + main_files + config_files + core_files + other_files


def process_single_file(file_path: str, local_path: str, llm) -> dict:
    """Process a single file with LLM to extract summary and dependencies."""
    full_path = Path(local_path) / file_path
    
    try:
        with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        
        if not content.strip():
            return None
        
        # Truncate large files
        max_chars = 10000
        is_truncated = len(content) > max_chars
        if is_truncated:
            content = content[:max_chars] + "\n... (truncated)"
        
        file_ext = Path(file_path).suffix.lower()
        file_type = file_ext[1:] if file_ext else "text"
        
        # Extract imports for context
        imports = []
        if file_ext == '.py':
            import_pattern = r'(?:^|\n)(?:from\s+([\.\w]+)\s+)?import\s+([\w\s,]+)'
            for match in re.findall(import_pattern, content, re.MULTILINE):
                module = match[0] if match[0] else match[1].split(',')[0].strip()
                if module and module.startswith('.'):
                    base_dir = str(Path(file_path).parent)
                    module_path = module.replace('.', '/').lstrip('/')
                    imports.append(f"{base_dir}/{module_path}.py" if base_dir != '.' else f"{module_path}.py")
        elif file_ext in ['.js', '.jsx', '.ts', '.tsx']:
            import_pattern = r'import\s+.*?from\s+["\']([\.\/\w\-]+)["\']'
            for match in re.findall(import_pattern, content):
                if match.startswith('.'):
                    base_dir = str(Path(file_path).parent)
                    for ext in ['.ts', '.tsx', '.js', '.jsx']:
                        imports.append(str((Path(local_path) / base_dir / (match + ext)).relative_to(Path(local_path))))
        
        imports_str = ', '.join(imports[:10]) if imports else 'None found'
        
        # LLM prompt for structured output
        prompt = f"""Analyze this code file and return ONLY a valid JSON object.

File: {file_path}
Type: {file_type}
{'(Truncated)' if is_truncated else ''}

```{file_type}
{content}
```

Imports detected: {imports_str}

Return JSON:
{{
  "summary": "2-4 sentence description of what this file does",
  "dependencies": ["relative/path/to/internal/file.py"]
}}

For dependencies: only include internal file imports, not npm/pip packages."""

        try:
            response = llm.invoke(prompt)
            response_text = response.content if hasattr(response, 'content') else str(response)
            
            if not response_text or not response_text.strip():
                return {"file": file_path, "summary": "No summary available.", "dependencies": []}
            
            # Strip markdown code blocks
            response_text = response_text.strip()
            if response_text.startswith("```"):
                response_text = re.sub(r'^```(?:json)?\s*', '', response_text, flags=re.MULTILINE)
                response_text = re.sub(r'```\s*$', '', response_text, flags=re.MULTILINE).strip()
            
            try:
                parsed = json.loads(response_text)
                return {
                    "file": file_path,
                    "summary": parsed.get("summary", "No summary available."),
                    "dependencies": parsed.get("dependencies", []) if isinstance(parsed.get("dependencies"), list) else [],
                }
            except json.JSONDecodeError:
                return {"file": file_path, "summary": response_text, "dependencies": []}
                
        except Exception as e:
            print(f"[PROCESS_FILE] LLM error for {file_path}: {str(e)}")
            return {"file": file_path, "summary": f"Error: {str(e)}", "dependencies": []}
            
    except Exception as e:
        print(f"[PROCESS_FILE] Error reading {file_path}: {str(e)}")
        return None


def generate_docs(state: AgentState) -> AgentState:
    """Process all files in parallel with GPT-4o-mini."""
    files = state["files"]
    update_progress('analyzing', f'Generating documentation for {len(files)} files...', files_found=len(files))
    print(f"[GENERATE_DOCS] Processing {len(files)} files")
    
    if not files:
        return {**state, "documents": []}
    
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.3)
    documents = []
    
    # Parallel processing with ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_file = {
            executor.submit(process_single_file, f, state["local_path"], llm): f
            for f in files
        }
        
        completed = 0
        for future in as_completed(future_to_file):
            file_path = future_to_file[future]
            completed += 1
            
            try:
                result = future.result()
                if result:
                    documents.append(result)
                    print(f"[GENERATE_DOCS] Processed: {file_path}")
                
                if completed % 5 == 0:
                    update_progress('analyzing', f'Processed {completed}/{len(files)} files...', files_processed=completed)
            except Exception as e:
                print(f"[GENERATE_DOCS] Error for {file_path}: {str(e)}")
    
    print(f"[GENERATE_DOCS] Completed: {len(documents)} documents")
    return {**state, "documents": documents}


# =============================================================================
# Node 4: Compile HTML Artifact
# =============================================================================

def compile_artifact(state: AgentState) -> AgentState:
    """Compile documents into styled HTML with table of contents."""
    update_progress('uploading', 'Compiling documentation...', documents_generated=len(state["documents"]))
    print(f"[COMPILE_NODE] Compiling {len(state['documents'])} documents")
    
    documents = state["documents"]
    repo_url = state["repo_url"]
    repo_name = repo_url.split("/")[-1].replace(".git", "") if repo_url else "Repository"
    
    toc_items = []
    doc_sections = []
    
    if not documents:
        doc_sections.append('''
        <section class="doc-section">
            <h2>No Documentation Generated</h2>
            <div class="doc-content">
                <p>No files were successfully processed.</p>
            </div>
        </section>
        ''')
    else:
        for idx, doc in enumerate(documents, 1):
            file_path = doc.get("file", f"file_{idx}")
            summary = doc.get("summary", doc.get("doc", ""))
            
            if not summary or not summary.strip():
                continue
            
            anchor_id = f"doc-{idx}"
            toc_items.append(f'<li><a href="#{anchor_id}">{html.escape(file_path)}</a></li>')
            doc_sections.append(f'''
            <section id="{anchor_id}" class="doc-section">
                <h2>{html.escape(file_path)}</h2>
                <div class="doc-content"><p>{html.escape(summary)}</p></div>
            </section>
            ''')
    
    # Build complete HTML document
    html_content = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{repo_name} - Documentation</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; background-color: #F5E7C6; color: #222222; }}
        .sidebar {{ position: fixed; left: 0; top: 0; width: 280px; height: 100vh; overflow-y: auto; background-color: #FFFFFF; border-right: 1px solid #222222; padding: 2rem 1rem; z-index: 100; }}
        .sidebar h1 {{ font-size: 1.5rem; font-weight: bold; margin-bottom: 1rem; color: #FF6D1F; }}
        .sidebar ul {{ list-style: none; }}
        .sidebar li {{ margin-bottom: 0.5rem; }}
        .sidebar a {{ color: #222222; text-decoration: none; padding: 0.5rem; display: block; border-radius: 0.25rem; word-wrap: break-word; }}
        .sidebar a:hover {{ background-color: #F5E7C6; color: #FF6D1F; }}
        .main-content {{ margin-left: 280px; padding: 2rem 4rem; max-width: 1200px; }}
        .header {{ border-bottom: 2px solid #222222; padding-bottom: 1rem; margin-bottom: 2rem; }}
        .header h1 {{ font-size: 2rem; font-weight: bold; }}
        .header p {{ opacity: 0.7; margin-top: 0.5rem; }}
        .header a {{ color: #FF6D1F; text-decoration: none; }}
        .doc-section {{ margin-bottom: 3rem; padding-bottom: 2rem; border-bottom: 1px solid #222222; }}
        .doc-section h2 {{ font-size: 1.5rem; font-weight: 600; margin-bottom: 1rem; }}
        .doc-content {{ line-height: 1.8; }}
        .doc-content p {{ margin-bottom: 1rem; }}
        @media (max-width: 768px) {{ .sidebar {{ position: relative; width: 100%; height: auto; border-right: none; border-bottom: 1px solid #222222; }} .main-content {{ margin-left: 0; padding: 1rem; }} }}
    </style>
</head>
<body>
    <div class="sidebar">
        <h1>Table of Contents</h1>
        <ul>{''.join(toc_items) if toc_items else '<li style="color: #666; padding: 0.5rem;">No files available</li>'}</ul>
    </div>
    <div class="main-content">
        <div class="header">
            <h1>{repo_name}</h1>
            <p>Generated Documentation • {datetime.now().strftime("%B %d, %Y at %I:%M %p")}</p>
            <p><a href="{repo_url}" target="_blank">View Repository</a></p>
        </div>
        {''.join(doc_sections)}
    </div>
</body>
</html>'''
    
    print(f"[COMPILE_NODE] Generated {len(html_content)} bytes")
    return {**state, "compiled_html": html_content}


# =============================================================================
# Node 5: Upload to S3
# =============================================================================

def upload_artifact(state: AgentState) -> AgentState:
    """Upload compiled HTML to S3 and return presigned URL."""
    update_progress('uploading', 'Uploading documentation to storage...')
    print(f"[UPLOAD_NODE] Uploading for job {state['job_id']}")
    
    compiled_html = state.get("compiled_html", "")
    job_id = state["job_id"]
    
    if not compiled_html:
        raise Exception("No compiled HTML content to upload")
    
    filename = f"{job_id}/index.html"
    
    try:
        public_url = upload_to_s3(
            content=compiled_html,
            filename=filename,
            content_type="text/html"
        )
        print(f"[UPLOAD_NODE] Success: {public_url}")
        return {**state, "final_url": public_url}
    except Exception as e:
        raise Exception(f"S3 upload failed: {str(e)}")


# =============================================================================
# Build LangGraph Pipeline
# =============================================================================

def build_agent_graph():
    """Construct and compile the LangGraph workflow."""
    workflow = StateGraph(AgentState)
    
    # Add nodes
    workflow.add_node("clone", clone_repo)
    workflow.add_node("index", index_files)
    workflow.add_node("generate", generate_docs)
    workflow.add_node("compile", compile_artifact)
    workflow.add_node("upload", upload_artifact)
    
    # Define edges (linear pipeline)
    workflow.set_entry_point("clone")
    workflow.add_edge("clone", "index")
    workflow.add_edge("index", "generate")
    workflow.add_edge("generate", "compile")
    workflow.add_edge("compile", "upload")
    workflow.add_edge("upload", END)
    
    return workflow.compile()


# Compiled graph instance (singleton)
agent_app = build_agent_graph()
