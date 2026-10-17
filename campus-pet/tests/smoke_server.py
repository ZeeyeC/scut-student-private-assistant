"""Isolated real API; deliberately no model configuration or personal data."""
import os
from datetime import datetime
from pathlib import Path

from app import after_class
from app.main import create_app
from tests.test_agent import ToolModel
from tests.test_agent_streaming import ChatFlowModel


class PetTestModel(ChatFlowModel):
    """Explicit test fixture. No credentials or external model requests."""
    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        if str(messages[-1].content).startswith("commit:"):
            return ToolModel._generate(self, messages, stop, run_manager, **kwargs)
        return super()._generate(messages, stop, run_manager, **kwargs)

root = Path(os.environ["PET_TEST_DATA"])
app = create_app({
    "app_mode": "local",
    "settings_file": str(root / "model.env"),
    "model_api_key": "", "text_model": "", "vision_model": "",
    "database_url": "sqlite+aiosqlite:///" + str(root / "campus.db"),
    "upload_dir": str(root / "uploads"), "agent_db_path": str(root / "agent.db"),
    "public_origin": "http://127.0.0.1:5189", "scut_adapter_path": "",
})
app.state.agent_model_factory = lambda: PetTestModel()
# Fixed academic clock only in this explicitly isolated verification server.
# Production uses the real server clock and exposes no override endpoint.
after_class.now = lambda: datetime.fromisoformat("2026-10-14T18:30:00+08:00")


if __name__ == "__main__":
    import uvicorn
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=5189))
    # Only this disposable verification server can be stopped by the native test.
    app.state.request_shutdown = lambda: setattr(server, "should_exit", True)
    server.run()
