"""Configuration and authentication helpers for the Canada Life Knowledge Agent.

Simplified: no auto-discovery. The endpoint name is known and configured
in app.yaml / environment variables.
"""

import os
from databricks.sdk import WorkspaceClient

# ---------------------------------------------------------------------------
# Environment detection
# ---------------------------------------------------------------------------

IS_DATABRICKS_APP = bool(os.environ.get("DATABRICKS_APP_NAME"))

# ---------------------------------------------------------------------------
# Configuration constants
# ---------------------------------------------------------------------------

DATABRICKS_HOST = os.environ.get(
    "DATABRICKS_HOST",
    "https://adb-7405618358516900.0.azuredatabricks.net",
)
AGENT_ENDPOINT_NAME = os.environ.get("AGENT_ENDPOINT_NAME", "ka-8665bea3-endpoint")
UC_CATALOG = os.environ.get("UC_CATALOG", "ronguerrero")
UC_SCHEMA = os.environ.get("UC_SCHEMA", "canadalife")
UC_VOLUME_PATH = os.environ.get("UC_VOLUME_PATH", "/Volumes/ronguerrero/canadalife/documents")
TEMP_VOLUME_PATH = os.environ.get("TEMP_VOLUME_PATH", "/Volumes/ronguerrero/canadalife/temp")
GENIE_SPACE_ID = os.environ.get("GENIE_SPACE_ID", "01f1180981a41dee822a9f11a6e0e806")
KNOWLEDGE_ASSISTANT_ID = os.environ.get("KNOWLEDGE_ASSISTANT_ID", "07d15c3f-983e-4510-b7fb-512c2ae89c28")


# ---------------------------------------------------------------------------
# Host URL helper
# ---------------------------------------------------------------------------

def get_host_url() -> str:
    """Get workspace host URL with https:// prefix."""
    host = DATABRICKS_HOST
    if host and not host.startswith("http"):
        host = f"https://{host}"
    return host.rstrip("/")


# ---------------------------------------------------------------------------
# Authentication helpers
# ---------------------------------------------------------------------------

def get_token_from_headers(request) -> str | None:
    """Extract user token from Databricks Apps forwarded headers."""
    if request is None:
        return None
    token = request.headers.get("x-forwarded-access-token")
    if token:
        return token.strip()
    return None


def get_service_principal_token() -> str | None:
    """Get service principal OAuth token for background operations."""
    # In Databricks Apps, the DATABRICKS_TOKEN env var is automatically injected
    token = os.environ.get("DATABRICKS_TOKEN")
    if token:
        print(f"[DEBUG] Using DATABRICKS_TOKEN (length: {len(token)})")
        return token

    print(f"[WARNING] DATABRICKS_TOKEN not found, trying SDK auth")
    print(f"[DEBUG] IS_DATABRICKS_APP: {IS_DATABRICKS_APP}")
    print(f"[DEBUG] DATABRICKS_HOST: {os.environ.get('DATABRICKS_HOST')}")
    print(f"[DEBUG] DATABRICKS_APP_NAME: {os.environ.get('DATABRICKS_APP_NAME')}")

    # In Databricks Apps, the service principal credentials should be auto-detected
    # Let WorkspaceClient auto-detect without explicit parameters
    try:
        from databricks.sdk.config import Config
        cfg = Config()
        auth_headers = cfg.authenticate()
        if auth_headers and "Authorization" in auth_headers:
            token = auth_headers["Authorization"].replace("Bearer ", "")
            if token:
                return token
    except Exception as e:
        print(f"Error getting service principal token with Config: {e}")

    # Fallback: try with explicit host
    try:
        w = WorkspaceClient(host=get_host_url())
        if w.config.token:
            return w.config.token
        auth_headers = w.config.authenticate()
        if auth_headers and "Authorization" in auth_headers:
            return auth_headers["Authorization"].replace("Bearer ", "")
    except Exception as e:
        print(f"Error getting service principal token with WorkspaceClient: {e}")

    return None


def get_token(request=None) -> str:
    """Get the best available token: user token first, then service principal."""
    if request:
        user_token = get_token_from_headers(request)
        if user_token:
            return user_token
    sp_token = get_service_principal_token()
    if sp_token:
        return sp_token
    raise RuntimeError("No authentication token available")


def get_user_token(request) -> str:
    """Get user token specifically -- for agent chat that needs user context."""
    user_token = get_token_from_headers(request)
    if user_token:
        return user_token
    # Fall back to service principal if no user token
    return get_token()


def get_app_token() -> str:
    """Get service principal token for workspace-level operations."""
    sp_token = get_service_principal_token()
    if sp_token:
        return sp_token
    raise RuntimeError("No service principal token available")


def get_workspace_client() -> WorkspaceClient:
    """Get WorkspaceClient for SDK operations (warehouses, SQL execution, etc)."""
    host = get_host_url()
    token = get_service_principal_token()
    if token:
        return WorkspaceClient(host=host, token=token)
    # Fallback to auto-detection
    return WorkspaceClient(host=host)
