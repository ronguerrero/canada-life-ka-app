# Configuration Guide for Canada Life Knowledge Agent App

This guide explains how to obtain the correct configuration values from your Databricks workspace.

## Required Configuration Values

The app requires these environment variables (configured in `app.yaml` and `server/config.py`):

1. **DATABRICKS_HOST** - Your Databricks workspace URL
2. **AGENT_ID** - The Knowledge Agent UUID
3. **AGENT_ENDPOINT_NAME** - The serving endpoint name for the agent
4. **UC_VOLUME_PATH** - Unity Catalog volume path for document storage

## Optional Configuration Values

These are auto-discovered or inferred at runtime. You only need to set them
if auto-discovery does not work in your environment:

5. **VS_INDEX_NAME** - Vector search index name (auto-discovered from the agent endpoint and vector search API)
6. **PIPELINE_ID** - Delta Live Tables pipeline ID (optional; pipeline status is inferred from the endpoint if not set)

## Auto-Discovery

The app automatically discovers the vector search index name at startup using
a three-stage strategy:

1. **Serving endpoint inspection** -- the app reads the agent serving endpoint
   configuration and scans it for vector search index references.
2. **Vector search index listing** -- the app lists all vector search indexes
   in the workspace and matches them against the agent ID prefix (e.g. `8665bea3`).
3. **Knowledge Agent API** -- the app queries the Knowledge Agent API for
   index configuration details.

The discovered index name is cached for the lifetime of the app process.  You
can verify the result by checking the `/api/health` endpoint, which now
includes `vector_index_discovered` and `vector_index_name` fields.

If you need to override auto-discovery, set the `VS_INDEX_NAME` environment
variable to the full index name.

## How to Find Configuration Values

### 1. Finding Your Agent ID

The Agent ID is visible in the Databricks Knowledge Agent configuration URL:

```
https://adb-<workspace-id>.0.azuredatabricks.net/ml/bricks/ka/configure/<AGENT_ID>?o=<org-id>
```

**Example:**
- URL: `https://adb-7405618358516900.0.azuredatabricks.net/ml/bricks/ka/configure/8665bea3-53f0-4b3e-9157-696991361f6e?o=7405618358516900`
- AGENT_ID: `8665bea3-53f0-4b3e-9157-696991361f6e`

**Steps:**
1. Navigate to your Databricks workspace
2. Go to Machine Learning -> Agent Bricks -> Knowledge Assistant
3. Click on your Knowledge Agent
4. Copy the UUID from the URL bar

### 2. Finding Your Agent Endpoint Name

The agent endpoint name is typically based on the agent ID prefix:

**Pattern:** `ka-<first-8-chars-of-agent-id>-endpoint`

**Example:**
- Agent ID: `8665bea3-53f0-4b3e-9157-696991361f6e`
- Endpoint Name: `ka-8665bea3-endpoint`

**To verify:**
1. In your Knowledge Agent configuration page, click "See Agent status" in the upper right
2. The endpoint name will be displayed
3. Alternatively, go to Machine Learning -> Serving -> Serving Endpoints
4. Find your agent's endpoint in the list

### 3. Vector Index Name (Auto-Discovered)

The vector index name is now **auto-discovered at startup**. You do not need
to configure it manually.

The index name follows this pattern:

```
__databricks_internal_catalog_tiles_arclight_<workspace-id>.<agent-prefix>_<hash>.ka_<agent-prefix>_<hash>_index
```

The app finds this automatically by matching the agent ID prefix against
available vector search indexes. To verify what was discovered, check:

```bash
curl http://localhost:8000/api/health
```

If auto-discovery fails (e.g. due to permissions), you can still set
`VS_INDEX_NAME` manually. To find the name:

1. Navigate to your Knowledge Agent configuration page
2. Look for the "Knowledge Sources" or "Index" section
3. The full index name should be visible there
4. Alternatively, use the Databricks CLI:
   ```bash
   databricks vector-search indexes list
   ```

### 4. Pipeline ID (Optional)

The Pipeline ID is the DLT pipeline that syncs documents from your volume to the vector index.
This is **optional** -- if not configured, the app infers pipeline status from the
serving endpoint's `config_update` state.

**Steps to find it (if needed):**
1. Navigate to Workflows -> Delta Live Tables
2. Find the pipeline associated with your Knowledge Agent
   - It may be named similar to your agent or include the agent ID prefix
3. Click on the pipeline
4. Copy the Pipeline ID from the URL:
   ```
   https://adb-<workspace-id>.0.azuredatabricks.net/#joblist/pipelines/<PIPELINE_ID>
   ```

**Example:**
- Pipeline ID: `12a268f8-abcb-473c-8745-a74f102cfd03`

### 5. UC Volume Path

The Unity Catalog volume path is where your documents are stored.

**Pattern:** `/Volumes/<catalog>/<schema>/<volume>`

**To find it:**
1. Go to Catalog Explorer in Databricks
2. Navigate to your catalog and schema
3. Find the volume used by your Knowledge Agent
4. The full path will be: `/Volumes/<catalog>/<schema>/<volume>`

**Example:**
```
/Volumes/ronguerrero/canadalife/documents
```

## Updating Configuration

Once you have the required values:

1. **For Databricks App deployment**: Update `app.yaml`
   ```yaml
   env:
     - name: 'AGENT_ID'
       value: '8665bea3-53f0-4b3e-9157-696991361f6e'
     - name: 'AGENT_ENDPOINT_NAME'
       value: 'ka-8665bea3-endpoint'
     # VS_INDEX_NAME is auto-discovered -- only set to override
     # PIPELINE_ID is optional -- only set if you want direct pipeline monitoring
   ```

2. **For local development**: Update `server/config.py` defaults or set environment variables
   ```bash
   export AGENT_ID="8665bea3-53f0-4b3e-9157-696991361f6e"
   export AGENT_ENDPOINT_NAME="ka-8665bea3-endpoint"
   # VS_INDEX_NAME and PIPELINE_ID are optional
   ```

## Verifying Your Configuration

After updating the configuration, test each component:

### 1. Test Health and Auto-Discovery
```bash
curl http://localhost:8000/api/health
```

Expected response includes `vector_index_discovered: true` and the full index name.

### 2. Test Serving Endpoint
```bash
curl -X GET "https://<workspace>.azuredatabricks.net/api/2.0/serving-endpoints/<AGENT_ENDPOINT_NAME>" \
  -H "Authorization: Bearer <token>"
```

### 3. Test Agent Chat
```bash
curl -X POST "https://<workspace>.azuredatabricks.net/serving-endpoints/<AGENT_ENDPOINT_NAME>/invocations" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"input": [{"role": "user", "content": "Hello"}]}'
```

## Sync Status Monitoring

The app monitors sync status through multiple methods:

1. **Serving Endpoint State** - Checks `state.config_update` field
   - `NOT_UPDATING` - No sync in progress
   - `IN_PROGRESS` - Configuration update (sync) active

2. **Vector Search Index State** - Checks index sync status (auto-discovered)
   - `online` - Index is ready
   - `syncing` - Documents being indexed
   - `provisioning` - Index being created

3. **Pipeline State** - Checks DLT pipeline status (if PIPELINE_ID is configured)
   - `IDLE` - No sync running
   - `RUNNING` - Sync in progress
   - `FAILED` - Sync failed
   - If PIPELINE_ID is not set, pipeline state is inferred from the endpoint

4. **Knowledge Agent API** (if accessible) - Direct agent status
   - May provide additional sync details
   - Falls back to endpoint/index/pipeline if not accessible

## Detecting UI-Triggered Syncs

When a user clicks "Sync" in the Databricks Knowledge Agent UI:

1. The serving endpoint's `config_update` field changes to `IN_PROGRESS`
2. The DLT pipeline state changes to `RUNNING` or `STARTING`
3. The vector index shows `syncing` state with updated row counts

The app polls these APIs every few seconds (configurable in frontend) to detect changes.

## Troubleshooting

### "Agent endpoint not found" error
- Verify AGENT_ENDPOINT_NAME matches the actual endpoint name
- Check that the endpoint is deployed and ready
- Use `databricks serving-endpoints list` to see all endpoints

### Vector index auto-discovery fails
- Check the `/api/health` endpoint to see if the index was discovered
- Review app startup logs for `[discovery]` messages
- Ensure the service principal has permissions to list vector search indexes
- You can manually set `VS_INDEX_NAME` as a fallback

### "Pipeline not found" error
- Verify PIPELINE_ID is correct (or leave it unset)
- Check that the pipeline exists in Delta Live Tables
- Use `databricks pipelines list` to see all pipelines

### Sync status shows "unknown"
- Check service principal permissions for API access
- Verify OAuth scopes include `serving.serving-endpoints`, `pipelines`, and `vector-search`
- Review app logs for specific API errors

## Additional Resources

- [Databricks Knowledge Assistant Documentation](https://docs.databricks.com/aws/en/generative-ai/agent-bricks/knowledge-assistant)
- [Serving Endpoints API Reference](https://docs.databricks.com/api/workspace/servingendpoints)
- [Vector Search API Reference](https://docs.databricks.com/api/workspace/vectorsearchindexes)
- [Pipelines API Reference](https://docs.databricks.com/api/workspace/pipelines)
