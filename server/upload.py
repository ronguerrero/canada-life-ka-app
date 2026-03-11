"""File upload to Unity Catalog volumes via Databricks REST API.

Spreadsheet files (.xlsx, .xls) and CSV files (.csv) are automatically
converted to Delta tables in Unity Catalog (ronguerrero.canadalife catalog)
and added to Genie space.
"""

import io
import os
from typing import Any

import aiohttp
from server.config import get_host_url, get_token, get_token_from_headers, get_app_token, UC_CATALOG, UC_SCHEMA, UC_VOLUME_PATH, TEMP_VOLUME_PATH, GENIE_SPACE_ID

# ---------------------------------------------------------------------------
# Spreadsheet helpers
# ---------------------------------------------------------------------------

EXCEL_EXTENSIONS = {".xlsx", ".xls"}
CSV_EXTENSIONS = {".csv"}
TABULAR_EXTENSIONS = EXCEL_EXTENSIONS | CSV_EXTENSIONS


def _is_spreadsheet(filename: str) -> bool:
    """Return True if the filename is a spreadsheet or CSV file."""
    _, ext = os.path.splitext(filename)
    return ext.lower() in TABULAR_EXTENSIONS


async def _convert_spreadsheet_to_delta_table(
    file_content: bytes, filename: str, request=None
) -> dict:
    """Convert an Excel file to Delta table(s) in Unity Catalog.

    Creates tables in ronguerrero.canadalife catalog.
    Each sheet becomes a separate table or appends to existing table.
    Also adds the table to the Genie space.

    Returns dict with table names and status.
    """
    try:
        import pandas as pd
        from databricks.sdk import WorkspaceClient
        import traceback

        print(f"[DEBUG] Starting Excel to Delta conversion for: {filename}")
        print(f"[DEBUG] File size: {len(file_content)} bytes")
        print(f"[DEBUG] First 50 bytes: {file_content[:50]}")

        stem = os.path.splitext(filename)[0]
        # Sanitize table name (remove spaces, special chars, parentheses, etc.)
        import re
        # Replace spaces, hyphens, dots, and other special chars with underscores
        table_base_name = re.sub(r'[^a-z0-9_]', '_', stem.lower())
        # Remove consecutive underscores
        table_base_name = re.sub(r'_+', '_', table_base_name)
        # Remove leading/trailing underscores
        table_base_name = table_base_name.strip('_')
        print(f"[DEBUG] Original filename: {filename}")
        print(f"[DEBUG] Table base name: {table_base_name}")

        # Get a warehouse for SQL execution using REST API
        try:
            # List warehouses using REST API (authentication handled by _try_request)
            status, data, _ = await _try_request("GET", "/api/2.0/sql/warehouses", request=request)
            if status != 200:
                raise Exception(f"Failed to list warehouses: {data}")

            warehouses = data.get("warehouses", [])
            print(f"[DEBUG] Found {len(warehouses)} warehouses")
            warehouse_id = None
            warehouse_to_start = None

            # First, try to find a running warehouse (prefer serverless)
            for wh in warehouses:
                wh_name = wh.get("name", "")
                wh_state = wh.get("state", "")
                wh_serverless = wh.get("enable_serverless_compute", False)
                wh_id = wh.get("id", "")
                print(f"[DEBUG] Warehouse: {wh_name}, State: {wh_state}, Serverless: {wh_serverless}")
                if wh_state == "RUNNING":
                    if wh_serverless:
                        warehouse_id = wh_id
                        break
                    elif not warehouse_id:  # Use non-serverless as fallback
                        warehouse_id = wh_id

            # If no running warehouse, find one to start (prefer serverless)
            if not warehouse_id:
                for wh in warehouses:
                    wh_state = wh.get("state", "")
                    wh_serverless = wh.get("enable_serverless_compute", False)
                    wh_id = wh.get("id", "")
                    if wh_state in ("STOPPED", "STARTING"):
                        if wh_serverless:
                            warehouse_to_start = wh_id
                            break
                        elif not warehouse_to_start:
                            warehouse_to_start = wh_id

                if warehouse_to_start:
                    # Start the warehouse using REST API
                    print(f"[DEBUG] Starting warehouse: {warehouse_to_start}")
                    status, data, _ = await _try_request(
                        "POST",
                        f"/api/2.0/sql/warehouses/{warehouse_to_start}/start",
                        request=request
                    )
                    if status not in (200, 201):
                        print(f"[WARN] Failed to start warehouse: {data}")

                    # Wait for it to be running (with timeout)
                    import asyncio
                    max_wait = 120  # 2 minutes
                    start_time = asyncio.get_event_loop().time()

                    while asyncio.get_event_loop().time() - start_time < max_wait:
                        status, wh_data, _ = await _try_request(
                            "GET",
                            f"/api/2.0/sql/warehouses/{warehouse_to_start}",
                            request=request
                        )
                        if status == 200:
                            wh_state = wh_data.get("state", "")
                            print(f"[DEBUG] Warehouse state: {wh_state}")
                            if wh_state == "RUNNING":
                                warehouse_id = warehouse_to_start
                                print(f"[DEBUG] Warehouse {warehouse_id} is now running")
                                break
                        await asyncio.sleep(5)

                    if not warehouse_id:
                        print("[ERROR] Warehouse start timeout")
                        return {
                            "success": False,
                            "error": "Warehouse start timeout - please try again",
                            "tables": []
                        }
                else:
                    print("[ERROR] No SQL warehouse available")
                    return {
                        "success": False,
                        "error": "No SQL warehouse available for table creation",
                        "tables": []
                    }

            print(f"[DEBUG] Using warehouse: {warehouse_id}")

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"[ERROR] Failed to get workspace client or warehouse:")
            print(error_details)
            return {
                "success": False,
                "error": f"Failed to get Databricks client: {str(e)}",
                "tables": []
            }

        # Detect if file is actually CSV (even with .xlsx extension)
        _, ext = os.path.splitext(filename)

        # Check if content is CSV by looking at first bytes
        is_csv = False
        try:
            # Try to decode as text and check for CSV patterns
            content_start = file_content[:1000].decode('utf-8-sig', errors='ignore')
            # CSV files typically have comma-separated values in first line
            if ',' in content_start.split('\n')[0] and content_start.count(',') > 2:
                is_csv = True
                print(f"[DEBUG] Detected CSV content despite {ext} extension")
        except:
            pass

        if is_csv:
            # Handle as CSV directly
            print(f"[DEBUG] Processing as CSV file")
            df = pd.read_csv(io.BytesIO(file_content))

            # Create a fake excel_file object with one sheet
            class FakeExcelFile:
                def __init__(self, dataframe, filename):
                    self.sheet_names = [os.path.splitext(os.path.basename(filename))[0]]
                    self._df = dataframe

            excel_file = FakeExcelFile(df, filename)
            # Store the dataframe for later use
            excel_file._cached_df = df
        else:
            # Handle as Excel
            engine = 'openpyxl' if ext.lower() == '.xlsx' else 'xlrd'
            print(f"[DEBUG] File extension: {ext}, Using engine: {engine}")

            try:
                excel_file = pd.ExcelFile(io.BytesIO(file_content), engine=engine)
                print(f"[DEBUG] Successfully loaded Excel file with {len(excel_file.sheet_names)} sheets")
            except Exception as e:
                print(f"[ERROR] Failed to load Excel file: {e}")
                raise

        created_tables = []
        errors = []

        for sheet_name in excel_file.sheet_names:
            try:
                # Read sheet into DataFrame
                if hasattr(excel_file, '_cached_df'):
                    # CSV file - use cached dataframe
                    df = excel_file._cached_df
                else:
                    # Excel file - read sheet
                    df = pd.read_excel(excel_file, sheet_name=sheet_name)

                # Skip empty sheets
                if df.empty:
                    continue

                # Sanitize column names (Delta doesn't allow spaces and special chars)
                print(f"[DEBUG] Original columns: {list(df.columns)}")
                sanitized = [
                    re.sub(r'_+', '_', re.sub(r'[^a-z0-9_]', '_', col.lower())).strip('_')
                    for col in df.columns
                ]
                print(f"[DEBUG] After sanitization: {sanitized}")

                # Deduplicate column names by adding numeric suffixes
                seen = {}
                unique_cols = []
                for col in sanitized:
                    if col not in seen:
                        seen[col] = 0
                        unique_cols.append(col)
                    else:
                        seen[col] += 1
                        unique_cols.append(f"{col}_{seen[col] + 1}")

                print(f"[DEBUG] After deduplication: {unique_cols}")

                # Verify no duplicates in unique_cols
                if len(unique_cols) != len(set(unique_cols)):
                    raise Exception(f"CRITICAL: Deduplication failed! Still have duplicates: {unique_cols}")

                df.columns = unique_cols
                print(f"[DEBUG] Final DataFrame columns: {list(df.columns)}")

                # Double-check pandas accepted the column names correctly
                actual_cols = list(df.columns)
                if actual_cols != unique_cols:
                    raise Exception(f"CRITICAL: Pandas didn't set columns correctly! Expected {unique_cols}, got {actual_cols}")

                # Create table name
                if len(excel_file.sheet_names) == 1:
                    table_name = table_base_name
                else:
                    # Sanitize sheet name same way as filename
                    safe_sheet = re.sub(r'[^a-z0-9_]', '_', sheet_name.lower())
                    safe_sheet = re.sub(r'_+', '_', safe_sheet).strip('_')
                    table_name = f"{table_base_name}_{safe_sheet}"

                full_table_name = f"{UC_CATALOG}.{UC_SCHEMA}.{table_name}"

                # Convert DataFrame to Spark DataFrame and write as Delta table
                # We'll use SQL to create the table via statement execution

                # First, convert DataFrame to CSV for uploading
                csv_buffer = io.StringIO()
                df.to_csv(csv_buffer, index=False, header=True)
                csv_content = csv_buffer.getvalue()
                print(f"[DEBUG] CSV header line: {csv_content.split(chr(10))[0]}")
                print(f"[DEBUG] CSV first data row: {csv_content.split(chr(10))[1] if len(csv_content.split(chr(10))) > 1 else 'N/A'}")

                # Create a temp file in DBFS to load from
                import tempfile
                import base64

                # Upload CSV to temp location in volume first
                temp_filename = f"temp_{table_name}.csv"
                csv_bytes = csv_content.encode('utf-8')

                # Upload to UC volume temporarily
                from server.config import get_host_url, get_token, get_app_token
                host = get_host_url()
                try:
                    token = get_app_token()
                except:
                    token = get_token(request)

                temp_path = f"{TEMP_VOLUME_PATH}/{temp_filename}"
                upload_url = f"{host}/api/2.0/fs/files{temp_path}"

                import aiohttp
                async with aiohttp.ClientSession() as session:
                    async with session.put(
                        upload_url,
                        headers={
                            "Authorization": f"Bearer {token}",
                            "Content-Type": "application/octet-stream"
                        },
                        data=csv_bytes
                    ) as response:
                        if response.status not in (200, 201, 204):
                            raise Exception(f"Failed to upload temp CSV: {response.status}")

                # Create table from CSV using SQL
                # Infer schema from pandas dtypes
                column_defs = []
                for col, dtype in df.dtypes.items():
                    if dtype == 'int64':
                        sql_type = 'BIGINT'
                    elif dtype == 'float64':
                        sql_type = 'DOUBLE'
                    elif dtype == 'bool':
                        sql_type = 'BOOLEAN'
                    else:
                        sql_type = 'STRING'

                    # Column names are already sanitized, just use them directly
                    column_defs.append(f"`{col}` {sql_type}")

                # Drop table first to clear any residual state
                drop_table_sql = f"DROP TABLE IF EXISTS {full_table_name}"
                print(f"[DEBUG] Dropping existing table: {full_table_name}")
                try:
                    status, _, error = await _execute_sql(warehouse_id, drop_table_sql, request)
                    if status == 200:
                        print(f"[DEBUG] Table dropped successfully")
                    else:
                        print(f"[DEBUG] Drop table failed (may not exist): {error}")
                except Exception as e:
                    print(f"[DEBUG] Drop table failed (may not exist): {e}")

                # Store upload timestamp
                from datetime import datetime
                import_time = datetime.now().isoformat()

                create_table_sql = f"""
                CREATE TABLE {full_table_name} (
                    {', '.join(column_defs)}
                )
                USING DELTA
                TBLPROPERTIES (
                    'original_filename' = '{filename}',
                    'upload_type' = 'spreadsheet',
                    'upload_timestamp' = '{import_time}'
                )
                """

                # Execute create table
                print(f"[DEBUG] Creating table: {full_table_name}")
                print(f"[DEBUG] CREATE TABLE SQL:\n{create_table_sql}")
                status, create_result, error = await _execute_sql(warehouse_id, create_table_sql, request)
                if status != 200:
                    raise Exception(f"Failed to create table: {error}")
                print(f"[DEBUG] Table created successfully")
                print(f"[DEBUG] Create result: {create_result}")

                # Load data from CSV
                # CSV has header with deduplicated column names matching table schema
                load_sql = f"""
                COPY INTO {full_table_name}
                FROM '{temp_path}'
                FILEFORMAT = CSV
                FORMAT_OPTIONS ('header' = 'true')
                """

                print(f"[DEBUG] Loading data with COPY INTO")
                print(f"[DEBUG] COPY INTO SQL:\n{load_sql}")
                status, load_result, error = await _execute_sql(warehouse_id, load_sql, request)
                if status != 200:
                    raise Exception(f"COPY INTO failed: {error}")
                print(f"[DEBUG] COPY INTO completed")
                print(f"[DEBUG] Load result: {load_result}")
                print(f"[DEBUG] Data loaded successfully")

                # Clean up temp CSV
                async with aiohttp.ClientSession() as session:
                    delete_url = f"{host}/api/2.0/fs/files{temp_path}"
                    async with session.delete(
                        delete_url,
                        headers={"Authorization": f"Bearer {token}"}
                    ) as response:
                        pass  # Ignore errors on cleanup

                # Add table to Genie space using REST API
                try:
                    genie_space_id = GENIE_SPACE_ID
                    print(f"[DEBUG] Adding table {full_table_name} to Genie space {genie_space_id}")

                    # Get current space with serialized definition using REST API
                    get_space_url = f"{host}/api/2.0/genie/spaces/{genie_space_id}?include_serialized_space=true"

                    async with aiohttp.ClientSession() as session:
                        async with session.get(
                            get_space_url,
                            headers={"Authorization": f"Bearer {token}"}
                        ) as response:
                            if response.status == 200:
                                space_data = await response.json()
                                print(f"[DEBUG] Retrieved Genie space: {space_data.get('title')}")

                                if 'serialized_space' in space_data and space_data['serialized_space']:
                                    import json
                                    # Parse the serialized space
                                    space_config = json.loads(space_data['serialized_space'])

                                    # Add table to data_sources if not already present
                                    if 'data_sources' not in space_config:
                                        space_config['data_sources'] = {'tables': []}
                                    if 'tables' not in space_config['data_sources']:
                                        space_config['data_sources']['tables'] = []

                                    # Check if table already exists
                                    existing_tables = [t.get('identifier') for t in space_config['data_sources']['tables']]
                                    if full_table_name not in existing_tables:
                                        space_config['data_sources']['tables'].append({
                                            'identifier': full_table_name
                                        })

                                        # IMPORTANT: Sort tables by identifier (required by Genie API)
                                        space_config['data_sources']['tables'].sort(key=lambda t: t.get('identifier', ''))

                                        # Update space with new config using REST API
                                        updated_serialized = json.dumps(space_config)
                                        update_space_url = f"{host}/api/2.0/genie/spaces/{genie_space_id}"

                                        async with session.patch(
                                            update_space_url,
                                            headers={
                                                "Authorization": f"Bearer {token}",
                                                "Content-Type": "application/json"
                                            },
                                            json={"serialized_space": updated_serialized}
                                        ) as update_response:
                                            if update_response.status in (200, 201):
                                                print(f"[DEBUG] Successfully added table to Genie space")
                                            else:
                                                error_text = await update_response.text()
                                                print(f"[DEBUG] Failed to update Genie space: {update_response.status} - {error_text}")
                                    else:
                                        print(f"[DEBUG] Table already exists in Genie space")
                                else:
                                    print(f"[DEBUG] No serialized_space found, cannot add table")
                            else:
                                error_text = await response.text()
                                print(f"[DEBUG] Failed to get Genie space: {response.status} - {error_text}")

                except Exception as e:
                    import traceback
                    print(f"Warning: Failed to add table to Genie: {e}")
                    print(f"[DEBUG] Traceback: {traceback.format_exc()}")

                created_tables.append({
                    "table_name": full_table_name,
                    "rows": len(df),
                    "columns": len(df.columns)
                })

            except Exception as e:
                errors.append(f"Failed to process sheet '{sheet_name}': {str(e)}")

        if created_tables:
            print(f"[DEBUG] Successfully created {len(created_tables)} table(s)")
            return {
                "success": True,
                "tables": created_tables,
                "errors": errors if errors else None
            }
        else:
            print(f"[DEBUG] No tables created. Errors: {errors}")
            return {
                "success": False,
                "error": "No tables created. " + "; ".join(errors),
                "tables": []
            }

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"[ERROR] Exception in _convert_spreadsheet_to_delta_table:")
        print(error_details)
        return {
            "success": False,
            "error": f"Conversion failed: {str(e)}",
            "tables": [],
            "debug": error_details
        }


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------

async def _execute_sql(warehouse_id: str, statement: str, request=None) -> tuple:
    """Execute SQL statement using REST API.

    Returns (status_code, result_data, error_message).
    """
    import asyncio

    payload = {
        "warehouse_id": warehouse_id,
        "statement": statement,
        "wait_timeout": "50s"
    }

    status, data, _ = await _try_request(
        "POST",
        "/api/2.0/sql/statements",
        request=request,
        json=payload
    )

    if status not in (200, 201):
        return (status, None, str(data))

    # Wait for statement to complete
    statement_id = data.get("statement_id")
    if not statement_id:
        return (status, data, None)

    # Poll for completion
    max_wait = 120
    start_time = asyncio.get_event_loop().time()

    while asyncio.get_event_loop().time() - start_time < max_wait:
        status, result, _ = await _try_request(
            "GET",
            f"/api/2.0/sql/statements/{statement_id}",
            request=request
        )

        if status == 200:
            state = result.get("status", {}).get("state")
            if state == "SUCCEEDED":
                return (200, result, None)
            elif state in ("FAILED", "CANCELED"):
                error = result.get("status", {}).get("error", {}).get("message", "Unknown error")
                return (500, None, error)

        await asyncio.sleep(2)

    return (408, None, "Statement execution timeout")


async def _try_request(method: str, url: str, request=None, **kwargs) -> tuple:
    """
    Try request with user token first, fall back to service principal.

    Returns (response_status, response_data_or_text, token_used).
    """
    host = get_host_url()
    full_url = f"{host}{url}"

    # Collect tokens to try: user first, then SP
    tokens_to_try = []

    # For Databricks Apps, try user token first (from request headers)
    if request:
        try:
            user_token = get_token_from_headers(request)
            if user_token:
                tokens_to_try.append(("user", user_token))
                print(f"[DEBUG] Will try user token from request headers")
        except Exception as e:
            print(f"[DEBUG] Failed to get user token from headers: {e}")

    # ALWAYS add service principal as fallback (for scope errors like Files API)
    try:
        sp_token = get_app_token()
        tokens_to_try.append(("sp", sp_token))
        print(f"[DEBUG] Will also try service principal token as fallback")
    except RuntimeError as e:
        print(f"[DEBUG] Failed to get service principal token: {e}")

    if not tokens_to_try:
        return (0, "No authentication token available", None)

    extra_headers = kwargs.pop("extra_headers", {})

    for token_type, token in tokens_to_try:
        headers = {"Authorization": f"Bearer {token}"}
        headers.update(extra_headers)

        try:
            async with aiohttp.ClientSession() as session:
                req_method = getattr(session, method.lower())
                async with req_method(full_url, headers=headers, **kwargs) as response:
                    # Retry with SP token if user token fails with auth errors
                    if response.status in (400, 401, 403) and token_type == "user" and len(tokens_to_try) > 1:
                        # User token is invalid or lacks scope, try SP next
                        continue
                    if response.content_type and "json" in response.content_type:
                        data = await response.json()
                        return (response.status, data, token_type)
                    else:
                        text = await response.text()
                        return (response.status, text, token_type)
        except Exception as e:
            if token_type == "user" and len(tokens_to_try) > 1:
                continue
            return (0, str(e), token_type)

    return (0, "All authentication attempts failed", None)


# ---------------------------------------------------------------------------
# Single-file upload to UC volume
# ---------------------------------------------------------------------------

async def _upload_single_file(
    file_content: bytes, filename: str, request=None
) -> dict[str, Any]:
    """Upload a single file (already in its final format) to the UC volume."""
    safe_filename = filename.replace(" ", "_")
    volume_file_path = f"{UC_VOLUME_PATH}/{safe_filename}"
    url = f"/api/2.0/fs/files{volume_file_path}"

    status, data, token_type = await _try_request(
        "PUT",
        url,
        request=request,
        data=file_content,
        extra_headers={"Content-Type": "application/octet-stream"},
    )

    if status in (200, 201, 204):
        return {
            "success": True,
            "path": volume_file_path,
            "filename": safe_filename,
        }
    else:
        # Extract a human-readable error message
        if isinstance(data, dict):
            error_msg = data.get("message", str(data))
        else:
            error_msg = str(data)
        return {
            "success": False,
            "path": "",
            "filename": safe_filename,
            "error": f"Upload failed ({status}): {error_msg}",
        }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def upload_file_to_volume(
    file_content: bytes,
    filename: str,
    request=None,
) -> dict:
    """
    Upload a file to the configured Unity Catalog volume.

    Spreadsheet files (.xlsx, .xls) and CSV files (.csv) are automatically
    converted to Delta tables in Unity Catalog (ronguerrero.canadalife)
    and added to Genie space.
    """
    if _is_spreadsheet(filename):
        # ------- Spreadsheet to Delta table conversion -------
        try:
            result = await _convert_spreadsheet_to_delta_table(file_content, filename, request=request)

            if result["success"]:
                tables = result["tables"]
                table_names = [t["table_name"] for t in tables]

                message_parts = [f"Created {len(tables)} Delta table(s):"]
                for table in tables:
                    message_parts.append(
                        f"  • {table['table_name']} ({table['rows']} rows, {table['columns']} columns)"
                    )
                message_parts.append("\nTables added to Genie space for analysis.")

                return {
                    "success": True,
                    "path": "",  # No file path, it's a table
                    "message": "\n".join(message_parts),
                    "converted": True,
                    "converted_files": table_names,
                    "tables": tables
                }
            else:
                return {
                    "success": False,
                    "path": "",
                    "message": f"Failed to convert to Delta table: {result.get('error', 'Unknown error')}",
                    "converted": False,
                }
        except Exception as exc:
            import traceback
            error_detail = traceback.format_exc()
            return {
                "success": False,
                "path": "",
                "message": f"Failed to convert spreadsheet to Delta table: {exc}\n{error_detail}",
                "converted": False,
            }

    else:
        # ------- Direct upload path (CSV, PDF, etc.) -------
        result = await _upload_single_file(file_content, filename, request=request)
        if result["success"]:
            return {
                "success": True,
                "path": result["path"],
                "message": f"File '{filename}' uploaded successfully to {result['path']}",
                "converted": False,
            }
        else:
            return {
                "success": False,
                "path": "",
                "message": result.get("error", "Upload failed"),
                "converted": False,
            }


async def list_volume_files(request=None) -> list[dict]:
    """
    List files in the Unity Catalog volume.

    Tries user token first, falls back to service principal.
    """
    url = f"/api/2.0/fs/directories{UC_VOLUME_PATH}"

    status, data, token_type = await _try_request("GET", url, request=request)

    if status == 200 and isinstance(data, dict):
        files = []
        for item in data.get("contents", []):
            if not item.get("is_directory", False):
                files.append({
                    "name": item.get("name", ""),
                    "path": item.get("path", ""),
                    "size": item.get("file_size", 0),
                    "last_modified": item.get("last_modified", 0),
                })
        return files
    else:
        print(f"List files error ({status}, auth={token_type}): {data}")
        return []
