"""All model-backed features share one factory and structured invocation path."""

import json

import pytest

from app.config import Config
from app.contracts import AssignmentExtraction, StepProposal
from app.model_gateway import ModelGateway
from app.timetable_contracts import TimetablePageExtraction


@pytest.mark.asyncio
async def test_deepseek_shared_key_endpoint_json_mode_and_dynamic_update(monkeypatch):
    captured = []

    class FakeModel:
        def __init__(self, name, kwargs):
            self.name = name
            self.kwargs = kwargs

        def with_structured_output(self, schema, **options):
            self.schema = schema
            self.options = options
            return self

        async def ainvoke(self, messages):
            captured.append(
                (self.name, self.kwargs, self.schema, self.options, messages)
            )
            if self.schema is StepProposal:
                return {
                    "steps": [
                        {
                            "key": "a",
                            "title": "read",
                            "description": "read",
                            "estimated_minutes": 5,
                            "dependency_keys": [],
                            "acceptance_criteria": ["done"],
                        }
                    ]
                }
            if self.schema is AssignmentExtraction:
                return {"items": [{"title": "read"}]}
            return {"semester_label": None, "candidates": []}

    def factory(name, **kwargs):
        return FakeModel(name, kwargs)

    monkeypatch.setattr("app.model_gateway.init_chat_model", factory)
    config = Config(
        _env_file=None,
        model_provider="openai",
        model_base_url="https://api.deepseek.com",
        model_api_key="synthetic-key",
        text_model="text",
        vision_model="vision",
    )
    gateway = ModelGateway(config)
    assert gateway.model().kwargs["api_key"] == "synthetic-key"
    await gateway.decompose_task({"title": "read"}, [])
    await gateway.extract_assignments(b"png", "image/png", [], None)
    await gateway.extract_timetable(b"png", "some page text", 1)
    assert [c[0] for c in captured] == ["text", "vision", "vision"]
    assert [c[2] for c in captured] == [
        StepProposal,
        AssignmentExtraction,
        TimetablePageExtraction,
    ]
    for _, kwargs, _, options, messages in captured:
        assert kwargs["api_key"] == "synthetic-key"
        assert kwargs["base_url"] == "https://api.deepseek.com"
        assert kwargs["extra_body"] == {"thinking": {"type": "disabled"}}
        assert options == {"method": "json_mode"}
        assert "JSON Schema" in messages[0]["content"]
        assert "synthetic-key" not in json.dumps(messages)
    config.model_api_key = "replacement"
    assert gateway.model(True).kwargs["api_key"] == "replacement"


@pytest.mark.asyncio
async def test_unified_structured_path_rejects_bad_schema_and_keeps_other_provider_default(
    monkeypatch,
):
    class Fake:
        def with_structured_output(self, schema, **options):
            assert options == {}
            return self

        async def ainvoke(self, messages):
            return {"not_the_schema": True}

    gateway = ModelGateway(
        Config(_env_file=None, model_base_url="https://example.com/v1")
    )
    monkeypatch.setattr(gateway, "model", lambda vision: Fake())
    with pytest.raises(ValueError):
        await gateway.structured(
            TimetablePageExtraction, [{"role": "system", "content": "test"}]
        )


@pytest.mark.asyncio
async def test_explicit_direct_mode_does_not_use_broken_environment_proxy(monkeypatch):
    captured = {}
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")

    def factory(name, **kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr("app.model_gateway.init_chat_model", factory)
    gateway = ModelGateway(
        Config(
            _env_file=None,
            model_api_key="unit",
            text_model="unit",
            model_use_system_proxy=False,
        )
    )
    gateway.model()
    assert captured["http_client"]._trust_env is False
    assert captured["http_async_client"]._trust_env is False
    await gateway.aclose()
