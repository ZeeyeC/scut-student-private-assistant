import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "backend"))
from app.main import create_app

(root / "frontend" / "openapi.json").write_text(
    json.dumps(create_app().openapi(), ensure_ascii=False), encoding="utf8"
)
