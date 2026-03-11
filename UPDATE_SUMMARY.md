# Update Summary - Canada Life Knowledge Agent App

## Overview

The Canada Life Knowledge Agent app has been updated to use the correct agent ID (`8665bea3-53f0-4b3e-9157-696991361f6e`) instead of the old agent ID (`ka-base-model-e5eb120b` / `86db5cec`).

## Changes Made

### 1. Configuration Updates

**Files Updated:**
- `/Users/ron.guerrero/canada-life-ka-app/app.yaml`
- `/Users/ron.guerrero/canada-life-ka-app/server/config.py`

**New Configuration Values:**
```yaml
AGENT_ID: '8665bea3-53f0-4b3e-9157-696991361f6e'
AGENT_ENDPOINT_NAME: 'ka-8665bea3-endpoint'
VS_INDEX_NAME: '__databricks_internal_catalog_tiles_arclight_7405618358516900.8665bea3_PLACEHOLDER.ka_8665bea3_PLACEHOLDER_index'
PIPELINE_ID: 'PLACEHOLDER-UPDATE-FROM-DATABRICKS-UI'
```

### 2. Enhanced Sync Monitoring

**Added to `/Users/ron.guerrero/canada-life-ka-app/server/sync.py`:**

1. **New `_get_knowledge_agent_details()` function**
   - Attempts to query the Knowledge Agent API directly at `/api/2.0/agent-bricks/knowledge-assistant/{AGENT_ID}`
   - Provides additional sync status information if accessible
   - Falls back gracefully if the API is not exposed or lacks permissions

2. **Enhanced `get_sync_status()` function**
   - Now includes Knowledge Agent API response in the status
   - Returns a new `knowledge_agent` field in the response with:
     - `agent_id`: The configured agent ID
     - `accessible`: Whether the Knowledge Agent API is reachable
     - `sync_state`: Direct sync state from the agent (if available)
     - `last_sync`: Timestamp of last sync operation
     - `knowledge_sources`: List of configured knowledge sources

3. **Better sync detection from Databricks UI**
   - Monitors `state.config_update` field on serving endpoint (changes to `IN_PROGRESS` during sync)
   - Tracks pipeline state changes (`IDLE` → `RUNNING` when sync starts)
   - Monitors vector index sync progress with row counts
   - Combines all three signals for comprehensive sync detection

### 3. Documentation

**New Files Created:**
- `/Users/ron.guerrero/canada-life-ka-app/CONFIGURATION.md` - Complete guide for finding and configuring all required values
- `/Users/ron.guerrero/canada-life-ka-app/UPDATE_SUMMARY.md` - This file

## Action Required

### CRITICAL: Update Placeholder Values

You must update the following placeholder values with the actual values from your Databricks workspace:

#### 1. Vector Index Name (VS_INDEX_NAME)

**Current (placeholder):**
```
__databricks_internal_catalog_tiles_arclight_7405618358516900.8665bea3_PLACEHOLDER.ka_8665bea3_PLACEHOLDER_index
```

**How to find the correct value:**
1. Go to: https://adb-7405618358516900.0.azuredatabricks.net/ml/bricks/ka/configure/8665bea3-53f0-4b3e-9157-696991361f6e?o=7405618358516900
2. Look for the "Vector Index" or "Knowledge Sources" section
3. Copy the full index name
4. Update both `app.yaml` and `server/config.py`

**OR** use Databricks CLI:
```bash
databricks vector-search indexes list | grep 8665bea3
```

#### 2. Pipeline ID (PIPELINE_ID)

**Current (placeholder):**
```
PLACEHOLDER-UPDATE-FROM-DATABRICKS-UI
```

**How to find the correct value:**
1. Go to Workflows → Delta Live Tables in your Databricks workspace
2. Find the pipeline associated with agent `8665bea3`
3. Click on the pipeline and copy the UUID from the URL
4. Update both `app.yaml` and `server/config.py`

**OR** use Databricks CLI:
```bash
databricks pipelines list | grep -i "canada\|8665bea3"
```

#### 3. Verify Agent Endpoint Name

The endpoint name is set to `ka-8665bea3-endpoint` based on the standard naming pattern. **Verify this is correct:**

1. Go to Machine Learning → Serving → Serving Endpoints
2. Find your Knowledge Agent endpoint
3. Confirm the name matches `ka-8665bea3-endpoint`
4. If different, update both `app.yaml` and `server/config.py`

**OR** use Databricks CLI:
```bash
databricks serving-endpoints list | grep -i "8665bea3\|canada"
```

## How the App Now Detects Sync Operations

### When User Clicks "Sync" in Databricks UI

The app will detect the sync through these signals:

1. **Serving Endpoint Update** (fastest detection, ~5-10 seconds)
   - The `/api/2.0/serving-endpoints/{endpoint_name}` API returns `state.config_update = "IN_PROGRESS"`
   - The app polls this endpoint every 5 seconds
   - When sync completes, it changes back to `NOT_UPDATING`

2. **Pipeline State Change** (reliable, ~10-30 seconds)
   - The `/api/2.0/pipelines/{pipeline_id}` API returns `state = "RUNNING"` or `"STARTING"`
   - Indicates documents are being processed
   - Returns to `IDLE` when complete

3. **Vector Index Sync State** (detailed progress, continuous)
   - The `/api/2.0/vector-search/indexes/{index_name}` API shows:
     - `status.ready = false` or `pipeline_status.state = "RUNNING"`
     - `indexed_row_count` increases as documents are indexed
   - Returns to `ready = true` and `state = "online"` when complete

4. **Knowledge Agent API** (optional, if exposed)
   - The `/api/2.0/agent-bricks/knowledge-assistant/{agent_id}` API may provide:
     - Direct sync status
     - Last sync timestamp
     - Knowledge source details
   - Falls back to other methods if not accessible (403/404)

### Sync Status Response Format

The `/api/sync/status` endpoint now returns:

```json
{
  "overall_status": "syncing" | "ready" | "error" | "unknown",
  "overall_message": "Human-readable status message",
  "endpoint": {
    "state": "ready" | "not_ready" | "no_access" | "error",
    "message": "Endpoint status details",
    "config_update": "NOT_UPDATING" | "IN_PROGRESS"
  },
  "index": {
    "state": "online" | "syncing" | "provisioning" | "failed" | "offline",
    "message": "Index status details",
    "indexed_row_count": 1234,
    "last_sync_time": "2026-03-04T12:00:00Z",
    "index_name": "..."
  },
  "pipeline": {
    "state": "idle" | "running" | "starting" | "failed",
    "message": "Pipeline status details",
    "last_update": "2026-03-04T12:00:00Z"
  },
  "knowledge_agent": {
    "agent_id": "8665bea3-53f0-4b3e-9157-696991361f6e",
    "accessible": true | false,
    "sync_state": "syncing" | "ready",
    "last_sync": "2026-03-04T12:00:00Z",
    "knowledge_sources": [...]
  }
}
```

## Testing the Updates

### 1. Test Configuration

```bash
# From the app directory
cd /Users/ron.guerrero/canada-life-ka-app

# Check that config loads correctly
python -c "from server.config import *; print(f'Agent ID: {AGENT_ID}'); print(f'Endpoint: {AGENT_ENDPOINT_NAME}')"
```

### 2. Test Sync Status API

Start the app and test the sync status endpoint:

```bash
# Start the app
python app.py

# In another terminal, test the sync status
curl http://localhost:8000/api/sync/status
```

### 3. Test in Databricks

After deploying to Databricks Apps:

1. Navigate to your deployed app
2. Check the "Sync Status" section in the UI
3. Click "Trigger Sync" or go to the Databricks Knowledge Agent UI and click "Sync"
4. Verify the app shows "Syncing" status
5. Wait for sync to complete and verify it shows "Ready"

## Rollback Instructions

If you need to revert to the old agent configuration:

```bash
cd /Users/ron.guerrero/canada-life-ka-app
git diff app.yaml server/config.py  # Review changes
git checkout HEAD -- app.yaml server/config.py  # Revert changes
```

## Known Limitations

1. **Knowledge Agent API Endpoint May Not Be Exposed**
   - The `/api/2.0/agent-bricks/knowledge-assistant/{agent_id}` endpoint is attempted but may not be publicly available
   - The app gracefully falls back to monitoring the serving endpoint, index, and pipeline
   - This is expected behavior and not an error

2. **Placeholder Values Must Be Updated**
   - The vector index name and pipeline ID contain placeholders
   - The app will not work correctly until these are updated with real values
   - See "Action Required" section above

3. **Sync Detection Latency**
   - There may be a 5-30 second delay between clicking "Sync" in the UI and the app detecting it
   - This is due to API polling intervals and propagation delays
   - The frontend polling interval can be adjusted if needed

## Additional Resources

- **Configuration Guide**: `/Users/ron.guerrero/canada-life-ka-app/CONFIGURATION.md`
- **Databricks Knowledge Assistant Docs**: https://docs.databricks.com/aws/en/generative-ai/agent-bricks/knowledge-assistant
- **Serving Endpoints API**: https://docs.databricks.com/api/workspace/servingendpoints
- **Vector Search API**: https://docs.databricks.com/api/workspace/vectorsearchindexes
- **Pipelines API**: https://docs.databricks.com/api/workspace/pipelines

## Support

For issues or questions:
1. Check logs: `python app.py` will show API request/response details
2. Verify configuration values in `CONFIGURATION.md`
3. Test individual APIs using curl (examples in `CONFIGURATION.md`)
4. Review Databricks workspace for agent/endpoint/index/pipeline status

## Summary of Files Changed

```
/Users/ron.guerrero/canada-life-ka-app/
├── app.yaml                    # Updated with new agent ID and placeholders
├── server/
│   ├── config.py              # Updated with new agent ID and placeholders
│   └── sync.py                # Enhanced with Knowledge Agent API support
├── CONFIGURATION.md           # NEW: Complete configuration guide
└── UPDATE_SUMMARY.md          # NEW: This file
```
