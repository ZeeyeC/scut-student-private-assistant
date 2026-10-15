"""Explicit test server. Never use this entrypoint for normal startup."""

import os
import tempfile
from pathlib import Path

from app.main import create_app
from tests.test_agent import ToolModel
from tests.test_assignments import FakeVision

root = Path(tempfile.mkdtemp(prefix="campus-e2e-"))
app = create_app(
    {
        "app_mode": os.getenv("CAMPUS_E2E_MODE", "shared"),
        "settings_file": str(root / "model.env"),
        "model_api_key": "",
        "text_model": "",
        "vision_model": "",
        "database_url": f"sqlite+aiosqlite:///{root}/db.sqlite",
        "upload_dir": str(root / "uploads"),
        "agent_db_path": str(root / "agent.db"),
        "public_origin": "http://127.0.0.1:5173",
        "scut_adapter_path": str(
            Path(__file__).parent
            / "fixtures"
            / (
                "test-adapter-list.json"
                if os.getenv("SCUT_E2E_LIST")
                else "test-adapter.json"
            )
        ),
    }
)
app.state.gateway = FakeVision()
if os.getenv("CAMPUS_E2E_ACADEMIC"):
    from tests.test_draft_usability import AcademicDraftModel

    app.state.agent_model_factory = lambda: AcademicDraftModel()
elif os.getenv("CAMPUS_E2E_DEADLINE"):
    from tests.test_task_deadline import DeadlineModel

    app.state.agent_model_factory = lambda: DeadlineModel()
elif os.getenv("CAMPUS_E2E_CALENDAR"):
    from tests.test_calendar_events import CalendarModel

    app.state.agent_model_factory = lambda: CalendarModel()
elif os.getenv("CAMPUS_E2E_CHAT_STREAM"):
    from tests.test_agent_streaming import ChatFlowModel

    app.state.agent_model_factory = lambda: ChatFlowModel()
else:
    app.state.agent_model_factory = lambda: ToolModel()
