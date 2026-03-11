"""FastAPI application for Canada Life Knowledge Agent with file upload."""

import os
import json
from pathlib import Path
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from server.agent import chat_with_agent, stream_chat_with_agent
from server.upload import upload_file_to_volume, list_volume_files


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Knowledge Agent App starting up...")
    yield
    print("Knowledge Agent App shutting down...")


# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------

app = FastAPI(title="Canada Life Knowledge Agent", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    stream: bool = False


class ChatResponse(BaseModel):
    content: str
    sources: list[dict] | None = None


# ---------------------------------------------------------------------------
# API Routes
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health():
    """Simple health check -- always returns valid JSON."""
    try:
        return {
            "status": "healthy",
            "service": "canada-life-knowledge-agent",
        }
    except Exception as exc:
        return {
            "status": "error",
            "service": "canada-life-knowledge-agent",
            "error": str(exc),
        }


@app.post("/api/chat")
async def chat_endpoint(request: Request, body: ChatRequest):
    """Chat with the knowledge agent."""
    try:
        messages = [{"role": m.role, "content": m.content} for m in body.messages]

        if body.stream:
            async def event_stream():
                async for chunk in stream_chat_with_agent(messages, request=request):
                    yield f"data: {json.dumps({'content': chunk})}\n\n"
                yield "data: [DONE]\n\n"

            return StreamingResponse(event_stream(), media_type="text/event-stream")
        else:
            result = await chat_with_agent(messages, request=request)
            return ChatResponse(**result)
    except Exception as exc:
        return ChatResponse(content=f"Error: {exc}", sources=None)


@app.post("/api/upload")
async def upload_endpoint(request: Request, file: UploadFile = File(...)):
    """Upload a file to the Unity Catalog volume."""
    allowed_extensions = {
        ".pdf", ".docx", ".doc", ".txt", ".csv", ".xlsx", ".xls",
        ".pptx", ".ppt", ".md", ".json", ".html", ".htm", ".rtf",
    }
    filename = file.filename or "unnamed_file"
    ext = os.path.splitext(filename)[1].lower()

    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{ext}' not supported. Allowed: {', '.join(sorted(allowed_extensions))}",
        )

    content = await file.read()

    max_size = 100 * 1024 * 1024
    if len(content) > max_size:
        raise HTTPException(status_code=400, detail="File size exceeds 100MB limit")

    try:
        result = await upload_file_to_volume(content, filename, request=request)
        if not result["success"]:
            raise HTTPException(status_code=500, detail=result["message"])
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/files")
async def list_files_endpoint(request: Request):
    """List both tables and documents for the sidebar."""
    from server.config import GENIE_SPACE_ID
    try:
        # Get managed files data (tables + documents)
        managed_data = await list_managed_files(request)

        # For backward compatibility, also return 'files' key with documents
        return {
            "files": managed_data.get("documents", []),
            "tables": managed_data.get("tables", []),
            "documents": managed_data.get("documents", []),
            "genie_space_id": GENIE_SPACE_ID
        }
    except Exception as exc:
        import traceback
        return {
            "files": [],
            "tables": [],
            "documents": [],
            "error": str(exc),
            "traceback": traceback.format_exc()
        }


@app.get("/api/sync-status")
async def get_sync_status(request: Request):
    """Get simplified sync status showing managed file count."""
    from server.config import get_host_url, get_token_from_headers, get_app_token, GENIE_SPACE_ID, KNOWLEDGE_ASSISTANT_ID, UC_CATALOG, UC_SCHEMA, DATABRICKS_HOST
    import aiohttp
    import json as json_module

    try:
        host = get_host_url()
        token = get_token_from_headers(request) if request else None
        if not token:
            token = get_app_token()

        async with aiohttp.ClientSession() as session:
            # Get count of managed files (tables + documents)
            # This gives us a simple count of all managed data sources

            # Count tables
            tables_sql = f"SHOW TABLES IN {UC_CATALOG}.{UC_SCHEMA}"
            table_count = 0

            # Count documents in volume (using list endpoint)
            doc_count = 0

            # For simplicity, just return a basic status
            # The full sync details are available in the Databricks UI
            total_files = table_count + doc_count

            # Extract org ID from DATABRICKS_HOST
            # Example: https://adb-4118603371332744.4.azuredatabricks.net/ -> 4118603371332744
            hostname = DATABRICKS_HOST.rstrip('/').replace('https://', '').replace('http://', '').split('.')[0]
            org_id = hostname.split('-')[-1] if '-' in hostname else hostname

            return {
                "total_files": total_files,
                "status": "synced" if total_files > 0 else "pending",
                "config_url": f"{host}/ml/bricks/ka/configure/{KNOWLEDGE_ASSISTANT_ID}?o={org_id}"
            }

    except Exception as exc:
        import traceback
        return {
            "total_files": 0,
            "status": "error",
            "error": str(exc)
        }


@app.get("/api/managed-files")
async def list_managed_files(request: Request):
    """List all managed files (tables and documents) with metadata."""
    from server.config import get_host_url, get_token_from_headers, get_app_token, UC_CATALOG, UC_SCHEMA, GENIE_SPACE_ID
    import aiohttp
    import json as json_module
    import asyncio

    try:
        host = get_host_url()

        # Get token (user token first, then service principal)
        token = None
        if request:
            token = get_token_from_headers(request)
        if not token:
            token = get_app_token()

        async with aiohttp.ClientSession() as session:
            # List warehouses using REST API
            warehouses_url = f"{host}/api/2.0/sql/warehouses"
            async with session.get(
                warehouses_url,
                headers={"Authorization": f"Bearer {token}"}
            ) as response:
                if response.status != 200:
                    text = await response.text()
                    return {"tables": [], "documents": [], "error": f"Failed to list warehouses: {text}"}

                warehouses_data = await response.json()
                warehouses = warehouses_data.get("warehouses", [])

                if not warehouses:
                    return {"tables": [], "documents": [], "error": "No warehouse available"}

                warehouse_id = warehouses[0]["id"]

            # Execute SQL to list tables using REST API
            tables_sql = f"""
            SELECT table_name
            FROM system.information_schema.tables
            WHERE table_catalog = '{UC_CATALOG}'
                AND table_schema = '{UC_SCHEMA}'
                AND table_type = 'MANAGED'
            ORDER BY table_name
            """

            sql_url = f"{host}/api/2.0/sql/statements"
            async with session.post(
                sql_url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json"
                },
                json={
                    "warehouse_id": warehouse_id,
                    "statement": tables_sql,
                    "wait_timeout": "30s"
                }
            ) as response:
                if response.status != 200:
                    text = await response.text()
                    return {"tables": [], "documents": [], "error": f"Failed to execute SQL: {text}"}

                result_data = await response.json()
                statement_id = result_data.get("statement_id")

                # Poll for result
                max_polls = 60
                for _ in range(max_polls):
                    status = result_data.get("status", {}).get("state")
                    if status in ["SUCCEEDED", "FAILED", "CANCELED"]:
                        break

                    await asyncio.sleep(0.5)

                    # Get statement status
                    status_url = f"{sql_url}/{statement_id}"
                    async with session.get(
                        status_url,
                        headers={"Authorization": f"Bearer {token}"}
                    ) as status_response:
                        result_data = await status_response.json()

            # Process results
            tables = []
            status = result_data.get("status", {}).get("state")
            if status == "SUCCEEDED":
                result = result_data.get("result", {})
                data_array = result.get("data_array", [])

                for row in data_array:
                    table_name = row[0]

                    # Try to get metadata from table properties
                    try:
                        props_sql = f"SHOW TBLPROPERTIES {UC_CATALOG}.{UC_SCHEMA}.{table_name}"

                        async with session.post(
                            sql_url,
                            headers={
                                "Authorization": f"Bearer {token}",
                                "Content-Type": "application/json"
                            },
                            json={
                                "warehouse_id": warehouse_id,
                                "statement": props_sql,
                                "wait_timeout": "30s"
                            }
                        ) as props_response:
                            props_data = await props_response.json()
                            props_statement_id = props_data.get("statement_id")

                            # Poll for properties result
                            for _ in range(max_polls):
                                props_status = props_data.get("status", {}).get("state")
                                if props_status in ["SUCCEEDED", "FAILED", "CANCELED"]:
                                    break

                                await asyncio.sleep(0.5)

                                status_url = f"{sql_url}/{props_statement_id}"
                                async with session.get(
                                    status_url,
                                    headers={"Authorization": f"Bearer {token}"}
                                ) as props_status_response:
                                    props_data = await props_status_response.json()

                            original_filename = table_name
                            upload_timestamp = None

                            if props_data.get("status", {}).get("state") == "SUCCEEDED":
                                props_result = props_data.get("result", {})
                                props_array = props_result.get("data_array", [])

                                for prop_row in props_array:
                                    if prop_row[0] == 'original_filename':
                                        original_filename = prop_row[1]
                                    elif prop_row[0] == 'upload_timestamp':
                                        upload_timestamp = prop_row[1]

                            tables.append({
                                "table_name": table_name,
                                "original_filename": original_filename,
                                "upload_timestamp": upload_timestamp,
                                "type": "table"
                            })
                    except:
                        # Fallback if properties can't be read
                        tables.append({
                            "table_name": table_name,
                            "original_filename": table_name,
                            "upload_timestamp": None,
                            "type": "table"
                        })

        # List volume files
        documents = await list_volume_files(request=request)

        return {
            "tables": tables,
            "documents": documents,
            "genie_space_id": GENIE_SPACE_ID
        }

    except Exception as exc:
        import traceback
        return {
            "tables": [],
            "documents": [],
            "error": str(exc),
            "traceback": traceback.format_exc()
        }


@app.delete("/api/managed-files/table/{table_name}")
async def delete_table(table_name: str, request: Request):
    """Delete a Delta table and remove it from Genie space."""
    from server.config import get_host_url, get_token_from_headers, get_app_token, UC_CATALOG, UC_SCHEMA, GENIE_SPACE_ID
    import aiohttp
    import json as json_module
    import asyncio

    try:
        host = get_host_url()

        # Get token (user token first, then service principal)
        token = None
        if request:
            token = get_token_from_headers(request)
        if not token:
            token = get_app_token()

        async with aiohttp.ClientSession() as session:
            # List warehouses using REST API
            warehouses_url = f"{host}/api/2.0/sql/warehouses"
            async with session.get(
                warehouses_url,
                headers={"Authorization": f"Bearer {token}"}
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise HTTPException(status_code=500, detail=f"Failed to list warehouses: {error_text}")

                warehouses_data = await response.json()
                warehouses = warehouses_data.get("warehouses", [])

                if not warehouses:
                    raise HTTPException(status_code=500, detail="No warehouse available")

                warehouse_id = warehouses[0]["id"]

            full_table_name = f"{UC_CATALOG}.{UC_SCHEMA}.{table_name}"

            # STEP 1: Remove from Genie space FIRST (before dropping table)
            # Get current Genie space config
            get_url = f"{host}/api/2.0/genie/spaces/{GENIE_SPACE_ID}?include_serialized_space=true"

            async with session.get(get_url, headers={"Authorization": f"Bearer {token}"}) as response:
                if response.status == 200:
                    space_data = await response.json()
                    if 'serialized_space' in space_data and space_data['serialized_space']:
                        space_config = json_module.loads(space_data['serialized_space'])

                        # Remove table from data_sources
                        if 'data_sources' in space_config and 'tables' in space_config['data_sources']:
                            original_tables = space_config['data_sources']['tables']
                            space_config['data_sources']['tables'] = [
                                t for t in original_tables
                                if t.get('identifier') != full_table_name
                            ]

                            # Only update if table was actually in the list
                            if len(space_config['data_sources']['tables']) < len(original_tables):
                                # Update space
                                update_url = f"{host}/api/2.0/genie/spaces/{GENIE_SPACE_ID}"
                                async with session.patch(
                                    update_url,
                                    headers={
                                        "Authorization": f"Bearer {token}",
                                        "Content-Type": "application/json"
                                    },
                                    json={"serialized_space": json_module.dumps(space_config)}
                                ) as update_response:
                                    if update_response.status not in (200, 201):
                                        error_text = await update_response.text()
                                        raise HTTPException(
                                            status_code=500,
                                            detail=f"Failed to remove table from Genie space: {error_text}"
                                        )
                                    print(f"Successfully removed {full_table_name} from Genie space")
                            else:
                                print(f"Table {full_table_name} was not in Genie space")

            # STEP 2: Now drop the table using REST API
            drop_sql = f"DROP TABLE IF EXISTS {full_table_name}"
            sql_url = f"{host}/api/2.0/sql/statements"

            async with session.post(
                sql_url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json"
                },
                json={
                    "warehouse_id": warehouse_id,
                    "statement": drop_sql,
                    "wait_timeout": "50s"
                }
            ) as response:
                if response.status not in (200, 201):
                    error_text = await response.text()
                    raise HTTPException(status_code=500, detail=f"Failed to drop table: {error_text}")

                result = await response.json()
                statement_id = result.get("statement_id")

                # Poll for completion
                for _ in range(60):
                    status_url = f"{host}/api/2.0/sql/statements/{statement_id}"
                    async with session.get(
                        status_url,
                        headers={"Authorization": f"Bearer {token}"}
                    ) as status_response:
                        if status_response.status == 200:
                            status_data = await status_response.json()
                            state = status_data.get("status", {}).get("state")

                            if state == "SUCCEEDED":
                                print(f"Successfully dropped table {full_table_name}")
                                break
                            elif state in ("FAILED", "CANCELED", "CLOSED"):
                                error = status_data.get("status", {}).get("error", {}).get("message", "Unknown error")
                                raise HTTPException(status_code=500, detail=f"Failed to drop table: {error}")

                        await asyncio.sleep(1)

        return {"success": True, "message": f"Table {table_name} deleted successfully"}

    except HTTPException:
        raise
    except Exception as exc:
        import traceback
        raise HTTPException(status_code=500, detail=f"Failed to delete table: {str(exc)}\n{traceback.format_exc()}")


@app.delete("/api/managed-files/document/{filename}")
async def delete_document(filename: str, request: Request):
    """Delete a document from UC volume."""
    from server.config import get_host_url, get_token, UC_VOLUME_PATH
    import aiohttp

    try:
        host = get_host_url()
        token = get_token(request)

        file_path = f"{UC_VOLUME_PATH}/{filename}"
        delete_url = f"{host}/api/2.0/fs/files{file_path}"

        async with aiohttp.ClientSession() as session:
            async with session.delete(
                delete_url,
                headers={"Authorization": f"Bearer {token}"}
            ) as response:
                if response.status in (200, 204):
                    return {"success": True, "message": f"Document {filename} deleted successfully"}
                else:
                    error_text = await response.text()
                    raise HTTPException(status_code=response.status, detail=f"Failed to delete document: {error_text}")

    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to delete document: {str(exc)}")


# ---------------------------------------------------------------------------
# Serve React Frontend
# ---------------------------------------------------------------------------

frontend_dist = Path(__file__).parent / "frontend" / "dist"

if frontend_dist.exists():
    # Serve static assets (JS, CSS, images)
    app.mount("/assets", StaticFiles(directory=frontend_dist / "assets"), name="assets")

    # Serve favicon and other root-level static files
    @app.get("/favicon.ico")
    async def favicon():
        favicon_path = frontend_dist / "favicon.ico"
        if favicon_path.exists():
            return FileResponse(favicon_path)
        raise HTTPException(status_code=404)

    # File management page
    @app.get("/files.html")
    async def files_page():
        from fastapi.responses import HTMLResponse
        html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>File Management - Canada Life Knowledge Agent</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f5f5f5;
            padding: 20px;
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
        }

        header {
            background: white;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }

        h1 {
            color: #333;
            margin-bottom: 10px;
        }

        .back-link {
            color: #0066cc;
            text-decoration: none;
            font-size: 14px;
        }

        .back-link:hover {
            text-decoration: underline;
        }

        .section {
            background: white;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }

        h2 {
            color: #333;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 2px solid #0066cc;
        }

        .file-list {
            list-style: none;
        }

        .file-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 12px;
            border-bottom: 1px solid #eee;
        }

        .file-item:last-child {
            border-bottom: none;
        }

        .file-info {
            flex: 1;
        }

        .file-name {
            font-weight: 500;
            color: #333;
            margin-bottom: 4px;
        }

        .file-meta {
            font-size: 12px;
            color: #666;
        }

        .file-actions button {
            background: #dc3545;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
        }

        .file-actions button:hover {
            background: #c82333;
        }

        .file-actions button:disabled {
            background: #ccc;
            cursor: not-allowed;
        }

        .empty-state {
            text-align: center;
            padding: 40px;
            color: #666;
        }

        .loading {
            text-align: center;
            padding: 40px;
            color: #666;
        }

        .error {
            background: #f8d7da;
            color: #721c24;
            padding: 12px;
            border-radius: 4px;
            margin-bottom: 20px;
        }

        .badge {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 500;
            margin-left: 8px;
        }

        .badge-table {
            background: #e3f2fd;
            color: #1976d2;
        }

        .badge-document {
            background: #f3e5f5;
            color: #7b1fa2;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>📁 File Management</h1>
            <a href="/" class="back-link">← Back to Chat</a>
        </header>

        <div id="error-container"></div>

        <div class="section">
            <h2>📊 Data Tables (from CSV/Excel uploads)</h2>
            <div id="tables-container">
                <div class="loading">Loading tables...</div>
            </div>
        </div>

        <div class="section">
            <h2>📄 Documents (PDF, Word, etc.)</h2>
            <div id="documents-container">
                <div class="loading">Loading documents...</div>
            </div>
        </div>
    </div>

    <script>
        let files = { tables: [], documents: [] };

        async function loadFiles() {
            try {
                const response = await fetch('/api/managed-files');
                if (!response.ok) throw new Error('Failed to load files');

                files = await response.json();
                renderTables();
                renderDocuments();
            } catch (error) {
                showError('Failed to load files: ' + error.message);
            }
        }

        function renderTables() {
            const container = document.getElementById('tables-container');

            if (!files.tables || files.tables.length === 0) {
                container.innerHTML = '<div class="empty-state">No tables found</div>';
                return;
            }

            const list = document.createElement('ul');
            list.className = 'file-list';

            files.tables.forEach(table => {
                const item = document.createElement('li');
                item.className = 'file-item';

                const info = document.createElement('div');
                info.className = 'file-info';

                const name = document.createElement('div');
                name.className = 'file-name';
                name.textContent = table.original_filename;

                const badge = document.createElement('span');
                badge.className = 'badge badge-table';
                badge.textContent = 'TABLE';
                name.appendChild(badge);

                const meta = document.createElement('div');
                meta.className = 'file-meta';
                meta.textContent = `Table: ${table.table_name}`;
                if (table.upload_timestamp) {
                    meta.textContent += ` • Uploaded: ${new Date(table.upload_timestamp).toLocaleString()}`;
                }

                info.appendChild(name);
                info.appendChild(meta);

                const actions = document.createElement('div');
                actions.className = 'file-actions';

                const deleteBtn = document.createElement('button');
                deleteBtn.textContent = 'Delete';
                deleteBtn.onclick = () => deleteTable(table.table_name);
                actions.appendChild(deleteBtn);

                item.appendChild(info);
                item.appendChild(actions);
                list.appendChild(item);
            });

            container.innerHTML = '';
            container.appendChild(list);
        }

        function renderDocuments() {
            const container = document.getElementById('documents-container');

            if (!files.documents || files.documents.length === 0) {
                container.innerHTML = '<div class="empty-state">No documents found</div>';
                return;
            }

            const list = document.createElement('ul');
            list.className = 'file-list';

            files.documents.forEach(doc => {
                const item = document.createElement('li');
                item.className = 'file-item';

                const info = document.createElement('div');
                info.className = 'file-info';

                const name = document.createElement('div');
                name.className = 'file-name';
                name.textContent = doc.name;

                const badge = document.createElement('span');
                badge.className = 'badge badge-document';
                badge.textContent = 'DOC';
                name.appendChild(badge);

                const meta = document.createElement('div');
                meta.className = 'file-meta';
                meta.textContent = `Size: ${formatBytes(doc.size)} • Modified: ${new Date(doc.last_modified).toLocaleString()}`;

                info.appendChild(name);
                info.appendChild(meta);

                const actions = document.createElement('div');
                actions.className = 'file-actions';

                const deleteBtn = document.createElement('button');
                deleteBtn.textContent = 'Delete';
                deleteBtn.onclick = () => deleteDocument(doc.name);
                actions.appendChild(deleteBtn);

                item.appendChild(info);
                item.appendChild(actions);
                list.appendChild(item);
            });

            container.innerHTML = '';
            container.appendChild(list);
        }

        async function deleteTable(tableName) {
            if (!confirm(`Are you sure you want to delete table "${tableName}"?\\n\\nThis will:\\n• Drop the Delta table\\n• Remove it from the Genie space\\n\\nThis action cannot be undone.`)) {
                return;
            }

            try {
                const response = await fetch(`/api/managed-files/table/${encodeURIComponent(tableName)}`, {
                    method: 'DELETE'
                });

                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.detail || 'Failed to delete table');
                }

                alert(`Table "${tableName}" deleted successfully`);
                loadFiles(); // Reload the list
            } catch (error) {
                showError('Failed to delete table: ' + error.message);
            }
        }

        async function deleteDocument(filename) {
            if (!confirm(`Are you sure you want to delete document "${filename}"?\\n\\nThis will permanently delete the file from the volume.\\n\\nThis action cannot be undone.`)) {
                return;
            }

            try {
                const response = await fetch(`/api/managed-files/document/${encodeURIComponent(filename)}`, {
                    method: 'DELETE'
                });

                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.detail || 'Failed to delete document');
                }

                alert(`Document "${filename}" deleted successfully`);
                loadFiles(); // Reload the list
            } catch (error) {
                showError('Failed to delete document: ' + error.message);
            }
        }

        function showError(message) {
            const container = document.getElementById('error-container');
            container.innerHTML = `<div class="error">${message}</div>`;
            setTimeout(() => {
                container.innerHTML = '';
            }, 5000);
        }

        function formatBytes(bytes) {
            if (bytes === 0) return '0 Bytes';
            const k = 1024;
            const sizes = ['Bytes', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
        }

        // Load files on page load
        loadFiles();
    </script>
</body>
</html>"""
        return HTMLResponse(content=html_content)

    # SPA fallback - serve index.html for all non-API routes
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="API endpoint not found")
        return FileResponse(frontend_dist / "index.html")
else:
    @app.get("/")
    async def root():
        return {
            "message": "Canada Life Knowledge Agent API",
            "note": "Frontend not built. Run 'npm run build' in the frontend directory.",
        }


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
