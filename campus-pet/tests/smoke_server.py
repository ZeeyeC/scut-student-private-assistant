"""Isolated real API; deliberately no model configuration or personal data."""
import os
import asyncio
from langchain_core.messages import AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from fastapi import Depends

from app import after_class
from app.main import create_app
from app import store
from app.db import Resource
from tests.test_agent import ToolModel
from tests.test_agent_streaming import ChatFlowModel


class PetTestModel(ChatFlowModel):
    """Explicit test fixture. No credentials or external model requests."""
    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        if str(messages[-1].content) == "流式测试":
            app.state.smoke_stream_release.clear()
            yield ChatGenerationChunk(message=AIMessageChunk(content="第一段"))
            await asyncio.wait_for(app.state.smoke_stream_release.wait(), timeout=60)
            yield ChatGenerationChunk(message=AIMessageChunk(content="第二段"))
        else:
            async for chunk in super()._astream(messages, stop, run_manager, **kwargs):
                yield chunk

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
app.state.smoke_stream_release = asyncio.Event()

@app.middleware("http")
async def release_after_busy_shutdown(request, call_next):
    response = await call_next(request)
    if request.url.path == "/api/local/shutdown" and response.status_code == 409:
        app.state.smoke_stream_release.set()
    return response

# Fixed academic clock only in this explicitly isolated verification server.
# Production uses the real server clock and exposes no override endpoint.
after_class.now = lambda: datetime.fromisoformat("2026-10-14T18:30:00+08:00")


@app.post('/__test__/task-ring')
async def task_ring_fixture(user=Depends(app.state.current_user), db=Depends(app.state.get_db)):
    """Fixture only in the disposable server; production never loads this module."""
    owner = str(user.id)
    for block in await store.rows(db, owner, 'plan_block'):
        await db.delete(block)
    today = datetime.now(ZoneInfo('Asia/Shanghai')).replace(hour=9, minute=0, second=0, microsecond=0)
    titles = ['高数习题', '英语阅读', '物理实验', '代码练习', '论文笔记', '单词复习', '线代练习', '项目报告']
    for i, title in enumerate(titles + ['未来任务', '仅截止任务', '已完成任务', '已完成时段']):
        tid, sid = f'ring-task-{i}', f'ring-step-{i}'
        db.add(Resource(id=tid, owner_id=owner, kind='task', data={
            'title':title, 'status':'completed' if i == 10 else 'open', 'requirements':['任务要求验收：完成并检查结果'],
            'due_at':(today+timedelta(hours=12)).isoformat(), 'due_text':'', 'remedy_due_at':None,
            'priority':2, 'course_id':None, 'uncertain_fields':[], 'submission_method':'',
        }))
        db.add(Resource(id=sid, owner_id=owner, kind='step', data={
            'task_id':tid, 'title':'学习步骤', 'description':'核对答案与记录', 'estimated_minutes':30,
            'spent_minutes':0, 'dependency_ids':[], 'dependency_keys':[], 'acceptance_criteria':['完成'], 'status':'open',
        }))
        if i == 9:
            continue
        start = today + timedelta(minutes=i*30, days=1 if i == 8 else 0)
        db.add(Resource(id=f'ring-block-{i}', owner_id=owner, kind='plan_block', data={
            'task_id':tid, 'step_id':sid, 'starts_at':start.isoformat(), 'ends_at':(start+timedelta(minutes=25)).isoformat(),
            'locked':False, 'status':'completed' if i == 11 else 'suggested',
        }))
    db.add(Resource(id='ring-duplicate', owner_id=owner, kind='plan_block', data={
        'task_id':'ring-task-0', 'step_id':'ring-step-0', 'starts_at':(today+timedelta(hours=10)).isoformat(),
        'ends_at':(today+timedelta(hours=10,minutes=25)).isoformat(), 'locked':False, 'status':'suggested',
    }))
    await store.bump(db, owner)
    return {'ids':[f'ring-task-{i}' for i in range(8)]}


if __name__ == "__main__":
    import uvicorn
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=5189))
    # Only this disposable verification server can be stopped by the native test.
    app.state.request_shutdown = lambda: setattr(server, "should_exit", True)
    server.run()
