# Customer Deployment Guide - Canada Life Knowledge Agent App

Complete deployment guide with all required permissions and steps.

## Prerequisites

### 1. Databricks Workspace Requirements
- Databricks workspace on AWS or Azure
- Unity Catalog enabled
- Databricks Apps feature enabled (Premium or Enterprise tier)

### 2. Required Resources in Customer Environment
- ✅ Knowledge Agent (Agent Bricks) already deployed
- ✅ Unity Catalog volume for document storage
- ✅ Databricks CLI installed (version 0.229.0+)

---

## Deployment Steps

### Step 1: Authenticate with Customer Workspace

```bash
# Authenticate with Databricks CLI
databricks auth login --host <CUSTOMER_WORKSPACE_URL>

# Example:
# databricks auth login --host https://adb-1234567890.azuredatabricks.net
```

### Step 2: Upload App Files

```bash
# Sync app code to customer workspace
databricks sync /Users/ron.guerrero/canada-life-ka-app \
  /Workspace/Users/<YOUR_EMAIL>/canada-life-ka-app \
  --exclude node_modules \
  --exclude .venv \
  --exclude __pycache__ \
  --exclude .git
```

### Step 3: Update Configuration

Edit `app.yaml` in the customer workspace with their specific values:

```yaml
command:
  - "python"
  - "-m"
  - "uvicorn"
  - "app:app"
  - "--host"
  - "0.0.0.0"
  - "--port"
  - "8000"

env:
  # Update with customer's knowledge agent endpoint name
  - name: AGENT_ENDPOINT_NAME
    value: "ka-XXXXXXXX-endpoint"  # ← CHANGE THIS
  
  # Update with customer's UC volume path
  - name: UC_VOLUME_PATH
    value: "/Volumes/CATALOG/SCHEMA/VOLUME"  # ← CHANGE THIS
```

### Step 4: Create the App

```bash
databricks apps create canada-life-ka-agent \
  --description "Knowledge Agent Chat Interface with Document Upload"
```

### Step 5: Deploy the App

```bash
databricks apps deploy canada-life-ka-agent \
  --source-code-path /Workspace/Users/<YOUR_EMAIL>/canada-life-ka-app
```

---

## Required Permissions

The app's service principal (created automatically during deployment) needs the following permissions:

### Permission 1: Knowledge Agent / Serving Endpoint Access

**Resource:** The knowledge agent's serving endpoint  
**Permission Level:** `CAN QUERY`

**How to Grant (SQL):**
```sql
-- Get the service principal name from the app
-- Format: app-XXXXXX <app-name>

GRANT USE ON SERVING ENDPOINT `<ENDPOINT_NAME>` 
TO `<SERVICE_PRINCIPAL_NAME>`;
```

**How to Grant (UI):**
1. Go to **Machine Learning** → **Serving** → **Serving Endpoints**
2. Find the knowledge agent endpoint (e.g., `ka-XXXXXXXX-endpoint`)
3. Click **Permissions**
4. Click **Grant**
5. Select: **Service Principal** → Find the app's service principal
6. Grant: **Can Query**

---

### Permission 2: Unity Catalog Schema Access

**Resource:** The schema containing the UC volume  
**Permission Level:** `USE SCHEMA`

**How to Grant (SQL):**
```sql
-- Example: If volume is /Volumes/main/documents/uploads
-- Schema is: main.documents

GRANT USE SCHEMA ON SCHEMA <CATALOG>.<SCHEMA> 
TO `<SERVICE_PRINCIPAL_NAME>`;
```

**How to Grant (UI):**
1. Go to **Catalog** in Databricks
2. Navigate to: `<CATALOG>` → `<SCHEMA>`
3. Click **Permissions** tab
4. Click **Grant**
5. Select: **Service Principal** → Find the app's service principal
6. Grant: **USE SCHEMA**

---

### Permission 3: Unity Catalog Volume - Write Access

**Resource:** The UC volume for document storage  
**Permission Level:** `WRITE VOLUME`

**How to Grant (SQL):**
```sql
-- Example: /Volumes/main/documents/uploads

GRANT WRITE VOLUME ON VOLUME <CATALOG>.<SCHEMA>.<VOLUME> 
TO `<SERVICE_PRINCIPAL_NAME>`;
```

**How to Grant (UI):**
1. Go to **Catalog** in Databricks
2. Navigate to: `<CATALOG>` → `<SCHEMA>` → **Volumes** → `<VOLUME>`
3. Click **Permissions** tab
4. Click **Grant**
5. Select: **Service Principal** → Find the app's service principal
6. Grant: **WRITE VOLUME**

---

### Permission 4: Unity Catalog Volume - Read Access

**Resource:** Same UC volume  
**Permission Level:** `READ VOLUME`

**How to Grant (SQL):**
```sql
GRANT READ VOLUME ON VOLUME <CATALOG>.<SCHEMA>.<VOLUME> 
TO `<SERVICE_PRINCIPAL_NAME>`;
```

**How to Grant (UI):**
- Same as Permission 3, but grant **READ VOLUME**

---

## Quick Grant - All UC Permissions at Once

```sql
-- Replace these with actual values:
-- <SERVICE_PRINCIPAL> = app's service principal name (e.g., "app-abc123 canada-life-ka-agent")
-- <CATALOG> = Unity Catalog name (e.g., "main")
-- <SCHEMA> = Schema name (e.g., "documents")  
-- <VOLUME> = Volume name (e.g., "uploads")

-- Schema access
GRANT USE SCHEMA ON SCHEMA <CATALOG>.<SCHEMA> 
TO `<SERVICE_PRINCIPAL>`;

-- Volume write
GRANT WRITE VOLUME ON VOLUME <CATALOG>.<SCHEMA>.<VOLUME> 
TO `<SERVICE_PRINCIPAL>`;

-- Volume read
GRANT READ VOLUME ON VOLUME <CATALOG>.<SCHEMA>.<VOLUME> 
TO `<SERVICE_PRINCIPAL>`;

-- Serving endpoint access
GRANT USE ON SERVING ENDPOINT `<ENDPOINT_NAME>` 
TO `<SERVICE_PRINCIPAL>`;
```

---

## How to Find the Service Principal Name

After creating the app, get the service principal:

```bash
databricks apps get canada-life-ka-agent --output json | \
  jq -r '.service_principal_name'
```

Output example: `app-3dxp8x canada-life-ka-agent`

---

## Verification Checklist

After deployment and granting permissions, verify:

### ✅ App is Running
```bash
databricks apps get canada-life-ka-agent
# Check: status.state = "SUCCEEDED"
```

### ✅ App URL is Accessible
```bash
databricks apps get canada-life-ka-agent --output json | jq -r '.url'
# Open URL in browser and log in
```

### ✅ Chat Works
- Open app in browser
- Type a test message
- Should get response from knowledge agent

### ✅ File Upload Works
- Click "Upload Files"
- Upload a test Excel file
- Should see "Converting spreadsheet to CSV..."
- Check UC volume - should see `.csv` file

### ✅ File List Works
- Should see list of files in the Documents panel
- Files from UC volume should appear

---

## Troubleshooting

### Issue: "403 Forbidden" when chatting
**Cause:** Service principal lacks serving endpoint access  
**Fix:** Grant `CAN QUERY` on the serving endpoint (Permission 1)

### Issue: "403 Forbidden" when uploading files
**Cause:** Service principal lacks UC volume access  
**Fix:** Grant UC permissions (Permissions 2, 3, 4)

### Issue: Excel files not converting to CSV
**Cause:** Missing Python dependencies  
**Fix:** Redeploy app (dependencies install automatically)

### Issue: "Knowledge agent not found"
**Cause:** Wrong endpoint name in `app.yaml`  
**Fix:** Update `AGENT_ENDPOINT_NAME` to correct endpoint

### Issue: Chat history not saving
**Cause:** Browser localStorage disabled  
**Fix:** Enable localStorage or use different browser

---

## Customer Environment Checklist

Before deploying, ensure customer has:

- [ ] Knowledge Agent (Agent Bricks) deployed and working
- [ ] Unity Catalog volume created for document storage
- [ ] Workspace admin access to grant permissions
- [ ] Databricks Apps feature enabled on workspace
- [ ] Users have access to the workspace

---

## App Features

Inform customer about app capabilities:

✅ **Chat Interface**
- Natural language chat with knowledge agent
- Multi-turn conversations
- Chat history persists in browser

✅ **Document Upload**
- Drag & drop or click to upload
- Automatic Excel-to-CSV conversion
- Supports: .xlsx, .xls, .csv, .pdf, .docx, .txt

✅ **File Management**
- View uploaded files
- See file sizes and dates
- Files stored in Unity Catalog volume

✅ **Security**
- Uses customer's authentication
- All permissions scoped to app service principal
- Audit logs track all file operations

---

## Support

After deployment, provide customer with:
- App URL
- This deployment guide
- Contact for technical support

---

## Summary

**Required Components:**
1. Databricks workspace with Unity Catalog
2. Knowledge Agent (Agent Bricks) deployed
3. UC volume for document storage

**Required Permissions:**
1. Serving endpoint: `CAN QUERY`
2. UC schema: `USE SCHEMA`
3. UC volume: `WRITE VOLUME` + `READ VOLUME`

**Deployment Time:** ~15-30 minutes  
**Technical Level:** Databricks admin with Unity Catalog knowledge

