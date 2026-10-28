"""Opt-in paid smoke test through the app's single ModelGateway.

Uses only generated study examples. Never reads personal courses, uploads or DBs.
The private settings file is read in memory; no keys/provider bodies in output.
"""

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.config import Config
from app.model_gateway import ModelGateway
from dotenv import dotenv_values
from langchain_core.messages import HumanMessage, ToolMessage
from PIL import Image, ImageDraw, ImageFont


def sample_image(lines):
    image = Image.new("RGB", (1200, 650), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=29)
    for index, line in enumerate(lines):
        draw.text((40, 45 + index * 80), line, fill="black", font=font)
    out = BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


async def verify(config, features=None):
    gateway = ModelGateway(config)
    results = []

    async def check(name, operation):
        try:
            detail = await operation()
            results.append({"feature": name, "passed": True, **(detail or {})})
        except Exception as exc:  # noqa: BLE001 -- do not expose SDK errors or keys
            results.append(
                {
                    "feature": name,
                    "passed": False,
                    "error_type": type(exc).__name__,
                    "http_status": getattr(exc, "status_code", None),
                    "validation": exc.__cause__.errors(
                        include_input=False, include_context=False
                    )
                    if hasattr(exc.__cause__, "errors")
                    else None,
                }
            )

    async def chat():
        response = await gateway.model().ainvoke(
            [
                HumanMessage(
                    content="Synthetic connection test. Reply with the word OK only."
                )
            ]
        )
        assert "OK" in str(response.content).upper()

    async def tools():
        model = gateway.model().bind_tools(
            [
                {
                    "type": "function",
                    "function": {
                        "name": "read_test_schedule",
                        "description": "Read a synthetic test schedule.",
                        "parameters": {
                            "type": "object",
                            "properties": {},
                            "required": [],
                        },
                    },
                }
            ]
        )
        messages = [
            HumanMessage(
                content="Call read_test_schedule to obtain the synthetic test result, then report its test_code. Do not invent the value."
            )
        ]
        first = await model.ainvoke(messages)
        assert (
            len(first.tool_calls) == 1
            and first.tool_calls[0]["name"] == "read_test_schedule"
        )
        second = await model.ainvoke(
            [
                *messages,
                first,
                ToolMessage(
                    content='{"test_code":"DEMO22_OK"}',
                    tool_call_id=first.tool_calls[0]["id"],
                ),
            ]
        )
        assert "DEMO22_OK" in str(second.content)

    async def decomposition():
        result = await gateway.decompose_task(
            {
                "title": "Read chapter 1 and solve exercise 1",
                "requirements": ["Read 5 pages", "Solve exercise 1"],
            },
            [],
        )
        assert result["steps"]
        return {"steps": len(result["steps"])}

    async def assignment():
        raw = sample_image(
            [
                "HOMEWORK NOTICE (synthetic)",
                "Course: Math",
                "Title: Chapter 2 exercises",
                "Requirement: Solve problems 1 to 3",
                "Deadline: 2026-11-06 18:00 (UTC+08:00)",
            ]
        )
        result = await gateway.extract_assignments(raw, "image/png", [], None)
        assert result["items"] and result["items"][0]["due_at"]
        return {"items": len(result["items"]), "deadline_detected": True}

    async def timetable():
        raw = sample_image(
            [
                "SCUT PERSONAL TIMETABLE (synthetic)",
                "Semester: 2026 Fall",
                "Monday | Periods 1,2",
                "Math | Weeks 1-16",
                "Teacher: Lee | Campus: Wushan | Room: A101",
            ]
        )
        result = await gateway.extract_timetable(raw, "", 1)
        assert len(result["candidates"]) == 1
        course = result["candidates"][0]
        assert course["weekday"] == 1 and course["periods"] == [1, 2]
        assert "Math" in (course["name"] or "")
        assert course["weeks_text"] and course["evidence"]
        return {
            "courses": 1,
            "critical_fields_detected": True,
            "evidence_fields": sorted({e["field"] for e in course["evidence"]}),
        }

    for name, operation in [
        ("chat", chat),
        ("tool_round_trip", tools),
        ("task_decomposition", decomposition),
        ("assignment_image", assignment),
        ("timetable_image", timetable),
    ]:
        if features and name not in features:
            continue
        await check(name, operation)
        print(json.dumps(results[-1], ensure_ascii=False), flush=True)
    await gateway.aclose()
    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "provider_host": "api.deepseek.com"
        if gateway.deepseek
        else "configured-provider",
        "text_model": config.text_model,
        "vision_model": config.vision_model,
        "sample_type": "generated synthetic examples; no personal data",
        "real_ocr_benchmark": False,
        "checks": results,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--settings-file", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--feature", action="append")
    args = parser.parse_args()
    values = {
        k.lower(): v
        for k, v in dotenv_values(args.settings_file).items()
        if k.lower() in Config.model_fields and v is not None
    }
    config = Config(_env_file=None, **values)
    if not config.model_api_key:
        raise SystemExit("Private model key is not configured.")
    result = asyncio.run(verify(config, args.feature))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    raise SystemExit(0 if all(c["passed"] for c in result["checks"]) else 1)


if __name__ == "__main__":
    main()
