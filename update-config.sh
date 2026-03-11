#!/bin/bash
# ============================================================================
# Update app.yaml from config.yaml
# ============================================================================

set -e

CONFIG_FILE="config.yaml"
APP_YAML="app.yaml"

# Check if config.yaml exists
if [ ! -f "$CONFIG_FILE" ]; then
    echo "❌ Error: $CONFIG_FILE not found"
    echo "   Please create config.yaml with your environment settings"
    exit 1
fi

echo "🚀 Canada Life Knowledge Agent - Configuration Update"
echo ""

# Extract values from config.yaml
echo "📄 Reading $CONFIG_FILE..."
ENDPOINT_NAME=$(grep "endpoint_name:" $CONFIG_FILE | awk '{print $2}' | tr -d '"')
VOLUME_PATH=$(grep "volume_path:" $CONFIG_FILE | awk '{print $2}' | tr -d '"')

if [ -z "$ENDPOINT_NAME" ] || [ -z "$VOLUME_PATH" ]; then
    echo "❌ Error: Could not extract values from $CONFIG_FILE"
    echo "   Make sure endpoint_name and volume_path are set"
    exit 1
fi

echo "   - Knowledge Agent: $ENDPOINT_NAME"
echo "   - UC Volume: $VOLUME_PATH"
echo ""

# Update app.yaml
echo "📝 Updating $APP_YAML..."

# Backup current app.yaml
cp $APP_YAML ${APP_YAML}.backup

# Update the values (app.yaml uses single quotes)
sed -i.tmp "s|value: 'ka-.*-endpoint'|value: '$ENDPOINT_NAME'|g" $APP_YAML
sed -i.tmp "s|value: '/Volumes/.*'|value: '$VOLUME_PATH'|g" $APP_YAML
rm -f ${APP_YAML}.tmp

echo "✅ Configuration updated successfully!"
echo ""
echo "📋 Current settings in $APP_YAML:"
grep -A 1 "AGENT_ENDPOINT_NAME\|UC_VOLUME_PATH" $APP_YAML | grep "value:"
echo ""
echo "Next steps:"
echo "  1. Review $APP_YAML to verify settings"
echo "  2. Sync code: databricks sync . /Workspace/Users/<YOUR_EMAIL>/canada-life-ka-app"
echo "  3. Deploy: databricks apps deploy canada-life-ka-agent \\"
echo "            --source-code-path /Workspace/Users/<YOUR_EMAIL>/canada-life-ka-app"
echo ""
echo "💾 Backup saved to: ${APP_YAML}.backup"
