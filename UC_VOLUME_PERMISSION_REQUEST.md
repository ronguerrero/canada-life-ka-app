# UC Volume Permission Request for Canada Life Knowledge Agent App

## App Information
- **App Name:** canada-life-ka-agent (also: canada-life-ka)
- **Service Principal Name:** app-3dxp8x canada-life-ka-agent
- **Service Principal ID:** 144130947437924
- **Workspace:** https://adb-7405618358516900.0.azuredatabricks.net/

## Current Issue
The app cannot upload files to the UC volume because it lacks permissions:
- **Volume Path:** `/Volumes/ronguerrero/canadalife/documents`
- **Error:** 403 Forbidden - Missing `USE SCHEMA` permission on `ronguerrero.canadalife`

## Required Permissions

### 1. Schema Permission - `USE SCHEMA`
Grant the service principal access to use the schema.

**Via Databricks CLI:**
```bash
databricks grants update schema ronguerrero.canadalife \
  --principal "app-3dxp8x canada-life-ka-agent" \
  --privilege "USE_SCHEMA" \
  -p adb-7405618358516900
```

**Via SQL:**
```sql
GRANT USE SCHEMA ON SCHEMA ronguerrero.canadalife 
TO `app-3dxp8x canada-life-ka-agent`;
```

**Via UI:**
1. Go to **Catalog** in Databricks
2. Navigate to catalog: `ronguerrero` → schema: `canadalife`
3. Click **Permissions**
4. Click **Grant**
5. Select: **Service Principal** → `app-3dxp8x canada-life-ka-agent`
6. Grant: **USE SCHEMA**

### 2. Volume Permission - `WRITE FILES`
Grant the service principal write access to the volume.

**Via Databricks CLI:**
```bash
databricks grants update volume ronguerrero.canadalife.documents \
  --principal "app-3dxp8x canada-life-ka-agent" \
  --privilege "WRITE_VOLUME" \
  -p adb-7405618358516900
```

**Via SQL:**
```sql
GRANT WRITE VOLUME ON VOLUME ronguerrero.canadalife.documents 
TO `app-3dxp8x canada-life-ka-agent`;
```

**Via UI:**
1. Go to **Catalog** in Databricks
2. Navigate to: `ronguerrero` → `canadalife` → **Volumes** → `documents`
3. Click **Permissions**
4. Click **Grant**
5. Select: **Service Principal** → `app-3dxp8x canada-life-ka-agent`
6. Grant: **WRITE VOLUME**

### 3. Optional: READ FILES (if app needs to list files)
If the app needs to list uploaded files, also grant:

**Via SQL:**
```sql
GRANT READ VOLUME ON VOLUME ronguerrero.canadalife.documents 
TO `app-3dxp8x canada-life-ka-agent`;
```

**Via UI:** Same as above, but grant **READ VOLUME** permission.

## Quick Grant - All Permissions at Once

**Via SQL (run all at once):**
```sql
-- Use the schema
GRANT USE SCHEMA ON SCHEMA ronguerrero.canadalife 
TO `app-3dxp8x canada-life-ka-agent`;

-- Write to volume
GRANT WRITE VOLUME ON VOLUME ronguerrero.canadalife.documents 
TO `app-3dxp8x canada-life-ka-agent`;

-- Read from volume (optional but recommended)
GRANT READ VOLUME ON VOLUME ronguerrero.canadalife.documents 
TO `app-3dxp8x canada-life-ka-agent`;
```

## Verification

After granting permissions, test the upload:
1. Go to: https://canada-life-ka-agent-7405618358516900.0.azure.databricksapps.com
2. Click **Upload Files** in the Documents panel
3. Upload a test file (e.g., Excel spreadsheet)
4. Should see: "Converting spreadsheet to CSV..." then "Upload complete"

Or test via API:
```bash
# Create a test file
echo "test,data" > test.csv

# Upload via curl
curl -X POST "https://canada-life-ka-agent-7405618358516900.0.azure.databricksapps.com/api/upload" \
  -F "file=@test.csv"
```

Should return: `{"success": true, "filename": "test.csv", ...}` instead of 403 error.

## Contact
This permission request was generated for: ron.guerrero@databricks.com

## Notes
- These permissions allow the app to READ and WRITE files to the specific volume only
- The app cannot access other volumes or schemas
- The app cannot DELETE files or modify schema structure
- Permissions can be revoked at any time
- File uploads include automatic Excel-to-CSV conversion

## Security Considerations
- Service principal is scoped to this specific app
- Permissions are limited to the `canadalife` schema and `documents` volume
- No data modification capabilities outside the volume
- All uploads are logged in Databricks audit logs
