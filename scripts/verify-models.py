"""Opt-in, billable provider probe. Synthetic image verifies transport, not OCR accuracy."""

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path

from langchain_core.tools import tool
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.config import Config
from app.model_gateway import ModelGateway


@tool
def compatibility_ping(value: str) -> str:
    """Return the supplied compatibility test marker."""
    return value


async def main():
    cfg = Config()
    if not (cfg.model_api_key and cfg.text_model and cfg.vision_model):
        print(
            "external_input_required: configure MODEL_API_KEY, TEXT_MODEL, VISION_MODEL in .env"
        )
        return 2
    gateway = ModelGateway(cfg)
    async with asyncio.timeout(120):
        message = (
            await gateway.model()
            .bind_tools([compatibility_ping], tool_choice="compatibility_ping")
            .ainvoke(
                "Call compatibility_ping with value campus-probe. Do not call anything else."
            )
        )
    assert any(
        c["name"] == "compatibility_ping" and c["args"].get("value") == "campus-probe"
        for c in message.tool_calls
    ), "Tool calling probe failed"
    due = (datetime.now(UTC) + timedelta(days=3)).strftime("%Y-%m-%d")
    image = Image.new("RGB", (1400, 300), "white")
    ImageDraw.Draw(image).multiline_text(
        (25, 25),
        f"Assignment 1: Math exercises\nRequirements: Solve chapter 2, questions 1-5.\nDue: {due} 18:00 UTC\n\nAssignment 2: Lab report\nRequirements: Submit a PDF. Deadline not specified.",
        fill="black",
        font_size=28,
        spacing=8,
    )
    out = BytesIO()
    image.save(out, format="PNG")
    extraction = await gateway.extract_assignments(
        out.getvalue(), "image/png", [], None
    )
    assert len(extraction["items"]) == 2, "Expected two assignments in synthetic image"
    assert any(i["due_at"] is None for i in extraction["items"]), (
        "Missing deadline was invented"
    )
    print(
        "PASS: text tool call and real vision structured output (synthetic image only)."
    )
    print(
        "Pending: review a real Chinese screenshot corpus and record field-level accuracy."
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except Exception as exc:  # noqa: BLE001 -- Never expose provider bodies containing credentials.
        # Provider errors may contain response bodies; only expose the exception type.
        print(
            "FAIL:",
            type(exc).__name__,
            "Check provider access, configured model capabilities and server logs.",
        )
        sys.exit(1)
