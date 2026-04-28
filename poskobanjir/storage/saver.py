import json
from pathlib import Path


def ensure_parent(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def save_csv(df, path="data_clean.csv"):
    ensure_parent(path)
    df.to_csv(path, index=False)
    print(f"Saved to {path}")


def save_json(data, path):
    ensure_parent(path)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
    print(f"Saved to {path}")
