"""Optional real local model acceptance in frozen service, isolated synthetic data."""

import argparse, json, os, shutil, subprocess, tempfile, time
from pathlib import Path
from uuid import uuid4
import httpx
from app.launcher import desktop_config, service_identity

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--service", type=Path, required=True)
parser.add_argument("--model-cache", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
origin = "http://127.0.0.1:5173"
with httpx.Client(base_url=origin, trust_env=False, timeout=45) as client:
    try:
        client.get("/api/healthz", timeout=1)
    except httpx.ConnectError:
        pass
    else:
        raise SystemExit("Port occupied; existing service preserved")
    with tempfile.TemporaryDirectory(prefix="campus-frozen-semantic-") as folder:
        root = Path(folder)
        models = root / "data/knowledge-index/models"
        models.parent.mkdir(parents=True)
        shutil.copytree(args.model_cache, models)
        (models / ".ready").write_text("BAAI/bge-small-zh-v1.5")
        expected = service_identity(desktop_config(root, root, project=False))
        env = {
            **os.environ,
            "HF_HUB_OFFLINE": "1",
            "HF_HUB_DISABLE_IMPLICIT_TOKEN": "1",
            "HF_HUB_DISABLE_TELEMETRY": "1",
        }
        for name in (
            "MODEL_API_KEY",
            "OPENAI_API_KEY",
            "HF_TOKEN",
            "HUGGING_FACE_HUB_TOKEN",
        ):
            env.pop(name, None)
        with (root / "server.log").open("w") as log:
            process = subprocess.Popen(
                [
                    str(args.service.resolve()),
                    "--serve",
                    "--no-browser",
                    "--data-dir",
                    str(root),
                ],
                cwd=root,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            try:
                for _ in range(150):
                    if process.poll() is not None:
                        raise RuntimeError(
                            "Frozen service stopped: "
                            + (root / "server.log").read_text()[-1800:]
                        )
                    try:
                        health = client.get("/api/healthz", timeout=1).json()
                        assert (
                            all(health.get(k) == v for k, v in expected.items())
                            and not health["model_configured"]
                        )
                        break
                    except httpx.ConnectError:
                        time.sleep(0.2)
                else:
                    raise RuntimeError("Frozen startup timed out")
                csrf = client.get("/api/csrf").json()["csrf_token"]
                headers = {"Origin": origin, "X-CSRF-Token": csrf}

                def write(path, body, method="POST"):
                    r = client.request(
                        method,
                        "/api" + path,
                        json=body,
                        headers={**headers, "Idempotency-Key": str(uuid4())},
                    )
                    r.raise_for_status()
                    return r.json() if r.content else None

                write("/local/session", {})
                status = client.get("/api/integrations").json()
                assert status["semantic"]["available"], status
                proposal = write(
                    "/memories/candidates",
                    {
                        "key": "workstyle",
                        "content": "睡前安排复盘，晨起难以集中",
                        "category": "study_preference",
                    },
                )
                candidate = client.get("/api/memories").json()["candidates"][0]
                write(
                    "/memories/candidates/" + candidate["id"] + "/confirm",
                    {"revision": candidate["revision"]},
                )
                write("/integrations/semantic", {"enabled": True}, "PUT")
                r = client.post(
                    "/api/knowledge/documents",
                    files={"file": ("study.md", "睡前安排复盘，晨起难以集中".encode())},
                    headers={**headers, "Idempotency-Key": str(uuid4())},
                )
                r.raise_for_status()
                source = r.json()
                result = write("/knowledge/search", {"query": "夜里温习更有效率"})
                assert result["mode"] == "semantic+keyword" and result["items"], result
                assert result["items"][0]["source_id"] == source["id"]
                write(
                    "/knowledge/sources/" + source["id"],
                    {"revision": source["revision"]},
                    "DELETE",
                )
                assert not write("/knowledge/search", {"query": "夜里温习更有效率"})[
                    "items"
                ]
                report = {
                    "passed": True,
                    "scope": "Actual frozen binary + real local Chinese model, synthetic data, HF offline, no paid provider calls",
                    "model": status["semantic"]["model"],
                    "document_semantic_match": True,
                    "source_delete_not_recalled": True,
                    "canonical_memory_confirmed": True,
                }
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(
                    json.dumps(report, ensure_ascii=False, indent=2) + "\n"
                )
                print(json.dumps(report, ensure_ascii=False))
            finally:
                if process.poll() is None:
                    process.terminate()
                process.wait(timeout=20)
