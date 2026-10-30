"""Isolated pet UI regression server; no personal configuration or paid models."""

import tempfile
import json
from datetime import datetime
from pathlib import Path

from app import after_class, planner, conversation_constraints, goal_capacity, weekly_review, proactive, negotiation
from app.main import create_app
from tests.test_timetable_recognition import FakeTimetableVision, candidate
from tests.test_timetable_text import TextTimetableModel

root = Path(tempfile.mkdtemp(prefix="campus-pet-e2e-"))
adapter_path = root / "synthetic-scut-adapter.json"
adapter_path.write_text(json.dumps({
    "version": "test-fixture-v1", "verified": True,
    "entry_url": "https://fixture.scut.edu.cn/", "school_origin": "https://fixture.scut.edu.cn",
    "container_selector": "#fixture-timetable", "semester_selector": "#semester", "loading_selector": ".loading",
    "columns": {"name": "课程", "weekday": "星期", "weeks": "周次", "periods": "节次", "location": "地点"},
    "full_capture": False, "verification_scope": "Synthetic test fixture only; not a real school acceptance",
}))
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
        "scut_adapter_path": str(adapter_path),
    }
)
after_class.now = lambda: datetime.fromisoformat("2026-10-14T18:30:00+08:00")
planner.now = lambda: datetime.fromisoformat("2026-10-14T18:30:00+08:00")
for module in (conversation_constraints, goal_capacity, weekly_review, proactive, negotiation):
    module.now = lambda: datetime.fromisoformat("2026-10-14T18:30:00+08:00")
app.state.agent_model_factory = lambda: TextTimetableModel()

# Explicit fake gateway only in this isolated UI test server.
app.state.gateway = FakeTimetableVision([candidate(weeks_text=None)])
