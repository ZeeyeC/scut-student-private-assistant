"""Offline SDK wire probe; mocked HTTP is not a real-model acceptance test."""

import json

import httpx
import pytest
from langchain_core.tools import tool
from openai import OpenAI

from app.config import Config
from app.contracts import AssignmentExtraction
from app.model_gateway import ModelGateway


@tool
def compatibility_ping(value: str) -> str:
    """Return the supplied marker."""
    return value


@pytest.mark.parametrize("vision", [False, True])
@pytest.mark.parametrize("via_openrouter", [False, True])
def test_luna_uses_responses_for_tools_and_image_structure(vision, via_openrouter):
    requests = []
    model_name = "openai/gpt-6-luna" if via_openrouter else "gpt-6-luna"
    base_url = "https://openrouter.ai/api/v1" if via_openrouter else None

    def respond(request):
        payload = json.loads(request.content)
        requests.append((request.url.path, payload))
        if vision:
            output = [
                {
                    "id": "msg_test",
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                    "content": [
                        {
                            "type": "output_text",
                            "annotations": [],
                            "text": json.dumps(
                                {
                                    "items": [{"title": "合成测试作业"}],
                                    "warnings": ["合成测试"],
                                }
                            ),
                        }
                    ],
                }
            ]
        else:
            output = [
                {
                    "id": "fc_test",
                    "type": "function_call",
                    "call_id": "call_test",
                    "name": "compatibility_ping",
                    "arguments": '{"value":"probe"}',
                    "status": "completed",
                }
            ]
        return httpx.Response(
            200,
            json={
                "id": "resp_test",
                "object": "response",
                "created_at": 1,
                "status": "completed",
                "model": "gpt-6-luna",
                "output": output,
            },
        )

    cfg = Config(
        _env_file=None,
        text_model=model_name,
        vision_model=model_name,
        model_api_key="offline-test-key",
        model_base_url=base_url,
    )
    model = ModelGateway(cfg).model(vision)
    # Use the actual locked SDK serializer and parser, with all HTTP intercepted.
    model.http_client = httpx.Client(transport=httpx.MockTransport(respond))
    model.root_client = OpenAI(
        api_key="offline-test-key",
        http_client=model.http_client,
        base_url=model.openai_api_base,
    )
    model.client = model.root_client.chat.completions
    if vision:
        result = model.with_structured_output(AssignmentExtraction).invoke(
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Synthetic transport test"},
                        {
                            "type": "image_url",
                            "image_url": {"url": "data:image/png;base64,dGVzdA=="},
                        },
                    ],
                }
            ]
        )
        assert result.warnings == ["合成测试"]
    else:
        result = model.bind_tools([compatibility_ping]).invoke("Call the test tool")
        assert result.tool_calls[0]["args"] == {"value": "probe"}
    path, payload = requests[0]
    assert path == ("/api/v1/responses" if via_openrouter else "/v1/responses")
    assert payload["model"] == model_name
    assert payload["reasoning"]["effort"] == "low"
    assert "temperature" not in payload
    if vision:
        assert payload["input"][0]["content"][1]["type"] == "input_image"
        assert payload["text"]["format"]["type"] == "json_schema"
    else:
        assert [t["name"] for t in payload["tools"]] == ["compatibility_ping"]
