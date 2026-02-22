import json
import os

def load_catalog():
    path = os.path.join(os.path.dirname(__file__), "catalog.json")
    with open(path, "r") as f:
        return json.load(f)