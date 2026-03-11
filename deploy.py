#!/usr/bin/env python3
"""
Deployment script for Canada Life Knowledge Agent App

This script reads config.yaml and updates app.yaml with the correct values.
"""

import yaml
import sys
from pathlib import Path

def load_config():
    """Load configuration from config.yaml"""
    config_path = Path(__file__).parent / "config.yaml"
    if not config_path.exists():
        print("❌ Error: config.yaml not found")
        print("   Please create config.yaml with your environment settings")
        sys.exit(1)
    
    with open(config_path) as f:
        return yaml.safe_load(f)

def update_app_yaml(config):
    """Update app.yaml with values from config"""
    app_yaml_path = Path(__file__).parent / "app.yaml"
    
    # Read current app.yaml
    with open(app_yaml_path) as f:
        app_yaml = yaml.safe_load(f)
    
    # Update environment variables
    env_vars = {}
    for env in app_yaml.get("env", []):
        env_vars[env["name"]] = env.get("value", env.get("valueFrom"))
    
    # Update with config values
    env_vars["AGENT_ENDPOINT_NAME"] = config["knowledge_agent"]["endpoint_name"]
    env_vars["UC_VOLUME_PATH"] = config["unity_catalog"]["volume_path"]
    
    # Rebuild env list
    app_yaml["env"] = [
        {"name": k, "value": v} for k, v in env_vars.items()
    ]
    
    # Write updated app.yaml
    with open(app_yaml_path, "w") as f:
        yaml.dump(app_yaml, f, default_flow_style=False, sort_keys=False)
    
    print("✅ app.yaml updated successfully")
    print(f"   - Knowledge Agent: {config['knowledge_agent']['endpoint_name']}")
    print(f"   - UC Volume: {config['unity_catalog']['volume_path']}")

def main():
    print("🚀 Canada Life Knowledge Agent - Deployment Configuration")
    print("")
    
    # Load config
    config = load_config()
    print("📄 Loaded config.yaml")
    
    # Update app.yaml
    update_app_yaml(config)
    
    print("")
    print("✅ Configuration complete!")
    print("")
    print("Next steps:")
    print("  1. Review app.yaml to verify settings")
    print("  2. Deploy: databricks apps deploy canada-life-ka-agent \\")
    print("            --source-code-path /Workspace/Users/<YOUR_EMAIL>/canada-life-ka-app")

if __name__ == "__main__":
    main()
