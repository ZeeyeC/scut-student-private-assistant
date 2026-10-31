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


# Deterministic chat-image fixtures; never a real vision/model provider.
from tests.test_chat_images import ImageVision
from langchain_core.messages import HumanMessage, ToolMessage, AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
import asyncio
import io
from PIL import Image

class ChatImageVision:
    def __init__(self):
        self.attempts = {}
    async def extract_assignments(self, raw, *args):
        color = Image.open(io.BytesIO(raw)).convert("RGB").getpixel((0, 0))
        if color == (0, 0, 255):
            await asyncio.Event().wait()
        if color == (255, 0, 0):
            key = __import__("hashlib").sha256(raw).hexdigest()
            self.attempts[key] = self.attempts.get(key, 0) + 1
            if self.attempts[key] == 1:
                raise TimeoutError("synthetic failure")
        return await ImageVision().extract_assignments(raw, *args)

class ChatImageModel(TextTimetableModel):
    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        text = next(str(m.content) for m in reversed(messages) if isinstance(m, HumanMessage))
        last = messages[-1]
        if text.startswith("识别这张作业截图"):
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content="已识别两项作业，请校对草稿后保存。"))])
        if text == "修改第二项为英语听力":
            if isinstance(last, ToolMessage) and last.name == "list_assignment_drafts":
                draft = json.loads(last.content)[0]
                call = {"name": "update_assignment_draft", "args": {"draft_id": draft["id"], "revision": draft["revision"], "item_index": 1, "changes": {"title": "英语听力"}}}
            elif isinstance(last, ToolMessage):
                return ChatResult(generations=[ChatGeneration(message=AIMessage(content="已修改第二项，请校对后保存。"))])
            else:
                call = {"name": "list_assignment_drafts", "args": {}}
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content="", tool_calls=[{**call, "id": __import__("uuid").uuid4().hex, "type": "tool_call"}]))])
        return super()._generate(messages, stop, run_manager, **kwargs)

app.state.agent_model_factory = lambda: ChatImageModel()
app.state.gateway.extract_assignments = ChatImageVision().extract_assignments
