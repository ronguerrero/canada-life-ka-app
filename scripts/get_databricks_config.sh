#!/bin/bash

# Helper script to retrieve Databricks configuration values for the Knowledge Agent app
# This script uses the Databricks CLI to fetch the correct configuration values

set -e

AGENT_ID="8665bea3-53f0-4b3e-9157-696991361f6e"
AGENT_PREFIX="8665bea3"

echo "=========================================="
echo "Databricks Knowledge Agent Configuration"
echo "=========================================="
echo ""
echo "Agent ID: $AGENT_ID"
echo ""

# Check if databricks CLI is installed
if ! command -v databricks &> /dev/null; then
    echo "ERROR: Databricks CLI not found."
    echo "Install it with: pip install databricks-cli"
    echo ""
    echo "Then configure it with: databricks configure --token"
    exit 1
fi

echo "Fetching configuration values from Databricks..."
echo ""

# Get serving endpoints
echo "1. Finding Agent Endpoint Name..."
echo "   Looking for endpoints matching: $AGENT_PREFIX"
ENDPOINT_LIST=$(databricks serving-endpoints list --output json 2>/dev/null || echo "[]")

if [ "$ENDPOINT_LIST" != "[]" ]; then
    ENDPOINT_NAME=$(echo "$ENDPOINT_LIST" | jq -r ".endpoints[] | select(.name | contains(\"$AGENT_PREFIX\")) | .name" | head -1)
    if [ -n "$ENDPOINT_NAME" ]; then
        echo "   ✓ Found: $ENDPOINT_NAME"
    else
        echo "   ✗ No endpoint found matching '$AGENT_PREFIX'"
        echo "   Suggested: ka-$AGENT_PREFIX-endpoint"
        ENDPOINT_NAME="ka-$AGENT_PREFIX-endpoint"
    fi
else
    echo "   ⚠ Unable to fetch endpoints (may require permissions)"
    echo "   Suggested: ka-$AGENT_PREFIX-endpoint"
    ENDPOINT_NAME="ka-$AGENT_PREFIX-endpoint"
fi
echo ""

# Get vector search indexes
echo "2. Finding Vector Search Index Name..."
echo "   Looking for indexes matching: $AGENT_PREFIX"
INDEX_LIST=$(databricks vector-search indexes list --output json 2>/dev/null || echo "{}")

if [ "$INDEX_LIST" != "{}" ]; then
    INDEX_NAME=$(echo "$INDEX_LIST" | jq -r ".vector_indexes[]? | select(.name | contains(\"$AGENT_PREFIX\")) | .name" | head -1)
    if [ -n "$INDEX_NAME" ]; then
        echo "   ✓ Found: $INDEX_NAME"
    else
        echo "   ✗ No index found matching '$AGENT_PREFIX'"
        echo "   You must get this from the Databricks UI:"
        echo "   Go to: ML → Agent Bricks → Knowledge Assistant → Your Agent"
        INDEX_NAME="REQUIRED-FROM-DATABRICKS-UI"
    fi
else
    echo "   ⚠ Unable to fetch indexes (may require permissions)"
    echo "   You must get this from the Databricks UI:"
    echo "   Go to: ML → Agent Bricks → Knowledge Assistant → Your Agent"
    INDEX_NAME="REQUIRED-FROM-DATABRICKS-UI"
fi
echo ""

# Get pipelines
echo "3. Finding DLT Pipeline ID..."
echo "   Looking for pipelines related to Knowledge Agent"
PIPELINE_LIST=$(databricks pipelines list --output json 2>/dev/null || echo "[]")

if [ "$PIPELINE_LIST" != "[]" ]; then
    # Try to find pipeline with agent prefix in name
    PIPELINE_ID=$(echo "$PIPELINE_LIST" | jq -r ".[] | select(.name | contains(\"$AGENT_PREFIX\") or contains(\"canada\") or contains(\"knowledge\")) | .pipeline_id" | head -1)
    if [ -n "$PIPELINE_ID" ]; then
        PIPELINE_NAME=$(echo "$PIPELINE_LIST" | jq -r ".[] | select(.pipeline_id == \"$PIPELINE_ID\") | .name")
        echo "   ✓ Found: $PIPELINE_ID"
        echo "     Name: $PIPELINE_NAME"
    else
        echo "   ✗ No pipeline found matching '$AGENT_PREFIX' or 'canada'"
        echo "   You must get this from the Databricks UI:"
        echo "   Go to: Workflows → Delta Live Tables → Find your agent's pipeline"
        PIPELINE_ID="REQUIRED-FROM-DATABRICKS-UI"
    fi
else
    echo "   ⚠ Unable to fetch pipelines (may require permissions)"
    echo "   You must get this from the Databricks UI:"
    echo "   Go to: Workflows → Delta Live Tables → Find your agent's pipeline"
    PIPELINE_ID="REQUIRED-FROM-DATABRICKS-UI"
fi
echo ""

# Print summary
echo "=========================================="
echo "Configuration Summary"
echo "=========================================="
echo ""
echo "Copy these values to app.yaml and server/config.py:"
echo ""
echo "AGENT_ID: '$AGENT_ID'"
echo "AGENT_ENDPOINT_NAME: '$ENDPOINT_NAME'"
echo "VS_INDEX_NAME: '$INDEX_NAME'"
echo "PIPELINE_ID: '$PIPELINE_ID'"
echo ""

# Generate updated config snippets
echo "=========================================="
echo "app.yaml Configuration"
echo "=========================================="
cat << EOF
env:
  - name: 'DATABRICKS_HOST'
    value: 'https://adb-7405618358516900.0.azuredatabricks.net'
  - name: 'AGENT_ID'
    value: '$AGENT_ID'
  - name: 'AGENT_ENDPOINT_NAME'
    value: '$ENDPOINT_NAME'
  - name: 'UC_VOLUME_PATH'
    value: '/Volumes/ronguerrero/canadalife/documents'
  - name: 'VS_INDEX_NAME'
    value: '$INDEX_NAME'
  - name: 'PIPELINE_ID'
    value: '$PIPELINE_ID'
EOF
echo ""

echo "=========================================="
echo "server/config.py Configuration"
echo "=========================================="
cat << EOF
DATABRICKS_HOST = os.environ.get("DATABRICKS_HOST", "https://adb-7405618358516900.0.azuredatabricks.net")
AGENT_ID = os.environ.get("AGENT_ID", "$AGENT_ID")
AGENT_ENDPOINT_NAME = os.environ.get("AGENT_ENDPOINT_NAME", "$ENDPOINT_NAME")
UC_VOLUME_PATH = os.environ.get("UC_VOLUME_PATH", "/Volumes/ronguerrero/canadalife/documents")
VS_INDEX_NAME = os.environ.get("VS_INDEX_NAME", "$INDEX_NAME")
PIPELINE_ID = os.environ.get("PIPELINE_ID", "$PIPELINE_ID")
EOF
echo ""

# Check for placeholder values
if [[ "$INDEX_NAME" == *"REQUIRED"* ]] || [[ "$PIPELINE_ID" == *"REQUIRED"* ]]; then
    echo "=========================================="
    echo "⚠ ACTION REQUIRED"
    echo "=========================================="
    echo ""
    echo "Some values could not be automatically retrieved."
    echo "You must manually get these values from the Databricks UI:"
    echo ""
    if [[ "$INDEX_NAME" == *"REQUIRED"* ]]; then
        echo "1. Vector Index Name:"
        echo "   - Go to: https://adb-7405618358516900.0.azuredatabricks.net/ml/bricks/ka/configure/$AGENT_ID"
        echo "   - Look for 'Vector Index' or 'Knowledge Sources' section"
        echo "   - Copy the full index name"
        echo ""
    fi
    if [[ "$PIPELINE_ID" == *"REQUIRED"* ]]; then
        echo "2. Pipeline ID:"
        echo "   - Go to: Workflows → Delta Live Tables"
        echo "   - Find the pipeline associated with your Knowledge Agent"
        echo "   - Click on it and copy the UUID from the URL"
        echo ""
    fi
fi

echo "=========================================="
echo "Verification Commands"
echo "=========================================="
echo ""
echo "Test endpoint access:"
echo "  databricks serving-endpoints get $ENDPOINT_NAME"
echo ""
if [[ "$INDEX_NAME" != *"REQUIRED"* ]]; then
    echo "Test index access:"
    echo "  databricks vector-search indexes get $INDEX_NAME"
    echo ""
fi
if [[ "$PIPELINE_ID" != *"REQUIRED"* ]]; then
    echo "Test pipeline access:"
    echo "  databricks pipelines get $PIPELINE_ID"
    echo ""
fi

echo "For more details, see CONFIGURATION.md"
