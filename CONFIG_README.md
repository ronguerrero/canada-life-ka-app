# Configuration Guide

This app uses a simple configuration system to make it easy to customize for different environments.

## Quick Start

### 1. Edit Configuration

Open `config.yaml` and update these values:

```yaml
knowledge_agent:
  endpoint_name: "ka-XXXXXXXX-endpoint"  # ← Your KA endpoint

unity_catalog:
  volume_path: "/Volumes/catalog/schema/volume"  # ← Your UC volume
```

### 2. Apply Configuration

```bash
./update-config.sh
```

This updates `app.yaml` with your values.

### 3. Deploy

```bash
# Sync code
databricks sync . /Workspace/Users/<YOUR_EMAIL>/canada-life-ka-app \
  --exclude "node_modules" --exclude ".venv" --exclude ".git"

# Deploy
databricks apps deploy canada-life-ka-agent \
  --source-code-path /Workspace/Users/<YOUR_EMAIL>/canada-life-ka-app
```

---

## Configuration Files

### `config.yaml`
- **Purpose:** Environment-specific settings
- **Edit this:** Yes - customize for each environment
- **Version control:** Can be committed or kept separate for different environments

### `app.yaml`
- **Purpose:** Databricks Apps deployment configuration  
- **Edit this:** No - generated from config.yaml
- **Version control:** Generated file, don't manually edit

### `update-config.sh`
- **Purpose:** Script to update app.yaml from config.yaml
- **Edit this:** No - unless changing the update logic
- **Version control:** Yes - part of the app

---

## Finding Configuration Values

### Knowledge Agent Endpoint Name

1. Go to **Machine Learning** → **Serving** → **Serving Endpoints**
2. Find your knowledge agent endpoint
3. Copy the name (format: `ka-XXXXXXXX-endpoint`)
4. Paste into `config.yaml` under `endpoint_name`

### UC Volume Path

1. Go to **Catalog** in Databricks
2. Navigate to your catalog → schema → Volumes
3. Copy the full path (format: `/Volumes/catalog/schema/volume`)
4. Paste into `config.yaml` under `volume_path`

---

## Multiple Environments

To manage multiple environments (dev, staging, prod):

### Option 1: Multiple Config Files

```bash
# Create environment-specific configs
cp config.yaml config-dev.yaml
cp config.yaml config-prod.yaml

# Edit each with environment-specific values
# Then copy the one you want before deploying
cp config-prod.yaml config.yaml
./update-config.sh
```

### Option 2: Git Branches

```bash
# Use different branches for different environments
git checkout dev-environment
# Edit config.yaml for dev
./update-config.sh

git checkout prod-environment  
# Edit config.yaml for prod
./update-config.sh
```

---

## Verification

After updating configuration, verify the values:

```bash
# Check app.yaml has correct values
grep -A 1 "AGENT_ENDPOINT_NAME\|UC_VOLUME_PATH" app.yaml

# Should show:
#   - name: AGENT_ENDPOINT_NAME
#     value: 'ka-XXXXXXXX-endpoint'
#   - name: UC_VOLUME_PATH
#     value: '/Volumes/catalog/schema/volume'
```

---

## Troubleshooting

### "Could not extract values from config.yaml"
- Check `config.yaml` syntax
- Ensure `endpoint_name:` and `volume_path:` are present
- Values should be in quotes

### Configuration not taking effect
- Run `./update-config.sh` after editing `config.yaml`
- Verify `app.yaml` was updated (check modification time)
- Redeploy the app for changes to take effect

### app.yaml looks wrong
- Restore from backup: `cp app.yaml.backup app.yaml`
- Run `./update-config.sh` again
- If still issues, manually edit `app.yaml`

---

## For Customers

When deploying to a customer environment:

1. ✅ Copy all app files to customer machine
2. ✅ Edit `config.yaml` with customer's values
3. ✅ Run `./update-config.sh`
4. ✅ Verify `app.yaml` has correct values
5. ✅ Deploy using standard deployment steps

No need to manually edit multiple files - just update `config.yaml`!
