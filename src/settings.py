#Read settings from settings.json
import json
from pathlib import Path

"load_settings() reads the settings from settings.json and returns a dictionary."
def load_settings():
    settings_path = Path("settings.json")
    if not settings_path.exists():
        print("❌ settings.json not found! Please create it with the necessary configuration.")
        exit(1)
    
    with open(settings_path, "r") as f:
        try:
            settings = json.load(f)
            print("✅ Settings loaded successfully!")
            return settings
        except json.JSONDecodeError as e:
            print(f"❌ Error parsing settings.json: {e}")
            exit(1)

#return the value of a specific setting, or None if it doesn't exist
def read_setting(param, settings=None, default_value=None):
    if settings is None:
        settings = load_settings()
    key = param.lower().split(".")
    value =  settings
    for k in key:     
        value = value.get(k, None)
        if value is None:
            print(f"⚠️ Setting '{param}' not found in settings.json.")
            return default_value
    
    return value if value != {} else default_value
