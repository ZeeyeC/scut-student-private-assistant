"""Isolated pet UI regression server; no personal configuration or paid models."""

import tempfile
from datetime import datetime
from pathlib import Path

from app import after_class
from app.main import create_app
from tests.test_agent import ToolModel

root = Path(tempfile.mkdtemp(prefix="campus-pet-e2e-"))
app = create_app(
    {
        "app_mode": "shared",
        "settings_file": str(root / "model.env"),
        "database_url": f"sqlite+aiosqlite:///{root}/test.db",
        "agent_db_path": str(root / "agent.db"),
        "upload_dir": str(root / "uploads"),
        "public_origin": "http://127.0.0.1:5290",
        "secure_cookie": False,
        "model_api_key": "",
        "text_model": "",
        "vision_model": "",
        "scut_adapter_path": "",
    }
)
after_class.now = lambda: datetime.fromisoformat("2026-10-14T18:30:00+08:00")
app.state.agent_model_factory = lambda: ToolModel()
