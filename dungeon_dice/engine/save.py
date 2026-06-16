import json
import os
import glob

SAVE_PATH = os.path.join("saves", "save.json")

def save_game(data, filepath=None):
    if filepath is None:
        filepath = SAVE_PATH
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"Error saving game to {filepath}: {e}")

def load_game(filepath=None):
    if filepath is None:
        filepath = SAVE_PATH
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading game from {filepath}: {e}")
            return None
    return None

def get_all_saves():
    save_dir = "saves"
    if not os.path.exists(save_dir):
        return []
    files = glob.glob(os.path.join(save_dir, "save_*.json"))
    saves = []
    for filepath in files:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                data["_filepath"] = filepath
                saves.append(data)
        except Exception as e:
            print(f"Error reading save file {filepath}: {e}")
    try:
        saves.sort(key=lambda s: os.path.getmtime(s["_filepath"]), reverse=True)
    except Exception:
        pass
    return saves
