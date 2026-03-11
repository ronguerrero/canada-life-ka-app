# Permission Request for Canada Life Knowledge Agent App

## App Information
- **App Name:** canada-life-ka-agent
- **Service Principal Name:** app-3dxp8x canada-life-ka-agent
- **Service Principal ID:** 144130947437924
- **Workspace:** https://adb-7405618358516900.0.azuredatabricks.net/

## Current Issue
The app cannot monitor sync status for the knowledge agent because it lacks permissions to access:
1. Vector Search Index API (returns 403 Forbidden)
2. Pipeline API (returns 403 Forbidden)

## Required Permissions

### 1. Vector Search Index Access
Grant `CAN MANAGE` or `CAN USE` permission on the vector search index used by knowledge agent `ka-base-model-e5eb120b`.

**Via Databricks CLI:**
```bash
# First, find the index name
databricks serving-endpoints get ka-8665bea3-endpoint -p adb-7405618358516900 --output json

# Then grant permission (replace INDEX_NAME with actual index)
databricks vector-search-indexes update \
  --name "INDEX_NAME" \
  --add-permissions '{"service_principal_name": "app-3dxp8x canada-life-ka-agent", "permission_level": "CAN_MANAGE"}' \
  -p adb-7405618358516900
```

**Via UI:**
1. Go to Machine Learning → Vector Search → Indexes
2. Find the index for knowledge agent `ka-8665bea3`
3. Click Permissions
4. Add service principal: `app-3dxp8x canada-life-ka-agent`
5. Grant: `CAN MANAGE` or `CAN USE`

### 2. Pipeline Access
Grant `CAN MANAGE` or `CAN VIEW` permission on the DLT pipeline associated with the knowledge agent.

**Via Databricks CLI:**
```bash
# First, find the pipeline ID from the knowledge agent config
# Then grant permission (replace PIPELINE_ID with actual ID)
databricks pipelines update \
  --pipeline-id "PIPELINE_ID" \
  --add-permissions '{"service_principal_name": "app-3dxp8x canada-life-ka-agent", "permission_level": "CAN_MANAGE"}' \
  -p adb-7405618358516900
```

**Via UI:**
1. Go to Workflows → Delta Live Tables
2. Find the pipeline for knowledge agent `ka-8665bea3`
3. Click Permissions
4. Add service principal: `app-3dxp8x canada-life-ka-agent`
5. Grant: `CAN MANAGE` or `CAN VIEW`

### 3. Optional: Workspace-Level API Access
If the above doesn't work, the service principal might need workspace-level permissions.

**Via UI:**
1. Go to Settings → Admin Console → Service Principals
2. Find: `app-3dxp8x canada-life-ka-agent`
3. Ensure it has appropriate entitlements:
   - Databricks SQL access
   - Workspace access

## Verification

After granting permissions, verify with:
```bash
# Test if app can now access the APIs
curl "https://canada-life-ka-agent-7405618358516900.0.azure.databricksapps.com/api/sync-status"
```

Should return detailed sync status instead of empty JSON.

## Contact
This permission request was generated for: ron.guerrero@databricks.com

## Notes
- These permissions allow the app to READ sync status only
- The app cannot modify or delete data
- Permissions can be revoked at any time
- The app already has access to the serving endpoint for chat
