"""Owner-scoped local semantic index using FastEmbed and local Qdrant."""

from __future__ import annotations

import asyncio
import os
import sys
import subprocess
from pathlib import Path
from typing import Any
import uuid

MODEL = "BAAI/bge-small-zh-v1.5"
VECTOR_DIM = 512
MAX_RECORDS = 200
MAX_QUERY_CHARS = 500
COLLECTION_NAME = "semantic_records"
READY_MARKER = ".ready"


def _point_id(owner: str, record_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_OID, f"{owner}:{record_id}"))


def _to_vector(raw: Any) -> list[float]:
    values = raw.tolist() if hasattr(raw, "tolist") else list(raw)
    return [float(x) for x in values]


def _extract_record(item: Any) -> tuple[str, int, str] | None:
    get = item.get if isinstance(item, dict) else lambda k, d=None: getattr(item, k, d)
    rec_id = str(get("id", "") or "").strip()
    revision = get("revision")
    data = get("data") or {}
    if not rec_id or revision is None:
        return None
    dget = data.get if isinstance(data, dict) else lambda k, d="": getattr(data, k, d)
    key = str(dget("key", "") or "").strip()
    content = str(dget("content", "") or "").strip()
    text = f"{key}\n{content}".strip() or rec_id
    return rec_id, int(revision), text[: MAX_QUERY_CHARS * 4]


async def offload(function, *args):
    # Retain index lock ownership until an in-flight thread really stops.
    import anyio

    task = asyncio.create_task(asyncio.to_thread(function, *args))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        with anyio.CancelScope(shield=True):
            await task
        raise


class SemanticIndex:
    """Lazy, thread-offloaded semantic index with strict owner/epoch isolation."""

    def __init__(
        self, root: Path | str, *, embedder: Any = None, client: Any = None
    ) -> None:
        self.root = Path(root)
        self.models_dir = self.root / "models"
        self.vectors_dir = self.root / "vectors"
        self.marker_path = self.models_dir / READY_MARKER
        self._lock = asyncio.Lock()
        self._generations = {}
        self._embedder_factory = (
            embedder
            if (embedder is not None and not hasattr(embedder, "embed"))
            else None
        )
        self._embedder = (
            embedder if (embedder is not None and hasattr(embedder, "embed")) else None
        )
        self._client = client
        self._status = "ready" if self._embedder is not None else "missing"
        self._error: str | None = None

    def _status_dict(self) -> dict[str, Any]:
        res: dict[str, Any] = {
            "available": self._status == "ready" and self._embedder is not None,
            "status": self._status,
            "model": MODEL,
        }
        if self._error:
            res["error"] = self._error
        return res

    def _create_embedder_sync(self, *, local_files_only: bool) -> Any:
        if self._embedder_factory is not None:
            return self._embedder_factory(
                model_name=MODEL,
                cache_dir=str(self.models_dir),
                threads=2,
                local_files_only=local_files_only,
            )
        os.environ.setdefault("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")
        os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
        from fastembed import TextEmbedding

        return TextEmbedding(
            model_name=MODEL,
            cache_dir=str(self.models_dir),
            threads=2,
            local_files_only=local_files_only,
        )

    def _init_local_sync(self) -> None:
        if self._embedder is None:
            embedder = self._create_embedder_sync(local_files_only=True)
            list(embedder.embed(["ok"]))
            self._embedder = embedder
        self._status = "ready"
        self._error = None

    def _ensure_client_sync(self) -> Any:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams

        if self._client is None:
            self.vectors_dir.mkdir(parents=True, exist_ok=True)
            try:
                self._client = QdrantClient(path=str(self.vectors_dir))
            except (ValueError, OSError, KeyError):
                # Derived index only. A corrupt index must not block forgetting.
                import shutil

                if self.vectors_dir.is_symlink():
                    raise RuntimeError("Linked index directory refused")
                shutil.rmtree(self.vectors_dir)
                self.vectors_dir.mkdir(parents=True)
                self._client = QdrantClient(path=str(self.vectors_dir))
        if not self._client.collection_exists(COLLECTION_NAME):
            self._client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
            )
        return self._client

    def _prepare_sync(self) -> None:
        self.models_dir.mkdir(parents=True, exist_ok=True)
        if self._embedder is None:
            self.marker_path.unlink(missing_ok=True)
            embedder = self._create_embedder_sync(local_files_only=False)
            list(embedder.embed(["warmup"]))
            self._embedder = embedder
        else:
            list(self._embedder.embed(["warmup"]))
        self._ensure_client_sync()
        self.marker_path.write_text(MODEL, encoding="utf-8")
        self._status = "ready"
        self._error = None

    async def status(self) -> dict[str, Any]:
        if self._status == "preparing":
            return self._status_dict()
        async with self._lock:
            if (
                self._embedder is None
                and self._status == "missing"
                and self.marker_path.exists()
            ):
                try:
                    await offload(self._init_local_sync)
                except Exception as exc:
                    self._embedder = None
                    self._status = "error"
                    self._error = (
                        "本地检索模型或索引不可用，请重新准备；关键词检索仍可使用"
                    )
            return self._status_dict()

    async def prepare(self) -> dict[str, Any]:
        self._status = "preparing"
        self._error = None
        async with self._lock:
            self._status = "preparing"
            self._error = None
            try:
                if self._embedder_factory is not None or self._embedder is not None:
                    await offload(self._prepare_sync)
                else:
                    await self._prepare_process()
                    await offload(self._init_local_sync)
                    await offload(self._ensure_client_sync)
            except Exception as exc:
                self._embedder = None
                self._status = "error"
                self._error = "本地检索模型或索引不可用，请重新准备；关键词检索仍可使用"
            return self._status_dict()

    async def _prepare_process(self):
        env = {
            **os.environ,
            "HF_HUB_DISABLE_IMPLICIT_TOKEN": "1",
            "HF_HUB_DISABLE_TELEMETRY": "1",
        }
        for name in (
            "HF_TOKEN",
            "HUGGING_FACE_HUB_TOKEN",
            "MODEL_API_KEY",
            "OPENAI_API_KEY",
        ):
            env.pop(name, None)
        if getattr(sys, "frozen", False):
            command = [sys.executable, "--prepare-semantic", str(self.root)]
        else:
            env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
            command = [
                sys.executable,
                "-m",
                "app.semantic_index",
                "--prepare-semantic",
                str(self.root),
            ]
        process = await asyncio.create_subprocess_exec(
            *command, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        try:
            async with asyncio.timeout(600):
                if await process.wait() != 0:
                    raise RuntimeError("Model download failed")
        finally:
            if process.returncode is None:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), 5)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()

    def _owner_filter(self, owner: str, epoch: int | None = None) -> Any:
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        must = [FieldCondition(key="owner", match=MatchValue(value=owner))]
        if epoch is not None:
            must.append(FieldCondition(key="epoch", match=MatchValue(value=epoch)))
        return Filter(must=must)

    def _clear_owner_sync(self, owner: str) -> None:
        if self._client is None and not self.vectors_dir.exists():
            return
        client = self._ensure_client_sync()
        client.delete(
            collection_name=COLLECTION_NAME, points_selector=self._owner_filter(owner)
        )

    def _rank_sync(
        self, owner: str, query: str, canonical: list[tuple[str, int, str]], epoch: int
    ) -> dict[str, dict[str, Any]]:
        from qdrant_client.models import PointStruct

        client = self._ensure_client_sync()
        desired = {rec_id: (rev, epoch) for rec_id, rev, _ in canonical}
        existing, _ = client.scroll(
            collection_name=COLLECTION_NAME,
            scroll_filter=self._owner_filter(owner),
            limit=30050 if owner.endswith("/knowledge") else MAX_RECORDS + 50,
            with_payload=True,
            with_vectors=False,
        )
        current: dict[str, tuple[int, int]] = {}
        valid_layout = len(existing) == len(desired)
        for pt in existing:
            payload = getattr(pt, "payload", None) or {}
            rid = str(payload.get("id", ""))
            if (
                set(payload.keys()) != {"owner", "id", "revision", "epoch"}
                or not rid
                or rid in current
            ):
                valid_layout = False
                break
            current[rid] = (int(payload["revision"]), int(payload["epoch"]))

        if not valid_layout or current != desired:
            if existing:
                client.delete(
                    collection_name=COLLECTION_NAME,
                    points_selector=self._owner_filter(owner),
                )
            vectors = [
                _to_vector(vec)
                for vec in self._embedder.embed([t for _, _, t in canonical])
            ]
            points = [
                PointStruct(
                    id=_point_id(owner, rec_id),
                    vector=vec,
                    payload={
                        "owner": owner,
                        "id": rec_id,
                        "revision": rev,
                        "epoch": epoch,
                    },
                )
                for (rec_id, rev, _), vec in zip(canonical, vectors, strict=True)
            ]
            if points:
                client.upsert(collection_name=COLLECTION_NAME, points=points)

        query_vec = _to_vector(next(iter(self._embedder.query_embed(query))))
        res = client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vec,
            query_filter=self._owner_filter(owner, epoch=epoch),
            limit=min(200, len(desired)),
            with_payload=True,
        )
        results: dict[str, dict[str, Any]] = {}
        for pt in getattr(res, "points", res) or []:
            payload = getattr(pt, "payload", None) or {}
            rec_id = str(payload.get("id", ""))
            rev = payload.get("revision")
            if (
                payload.get("owner") == owner
                and payload.get("epoch") == epoch
                and rec_id in desired
                and rev == desired[rec_id][0]
            ):
                results[rec_id] = {
                    "score": float(getattr(pt, "score", 0.0)),
                    "revision": int(rev),
                }
        return results

    def generation(self, owner):
        return self._generations.get(owner, 0)

    async def rank(
        self,
        owner: str,
        query: str,
        records: list[Any],
        epoch: int = 0,
        generation: int | None = None,
    ) -> dict[str, dict[str, Any]]:
        clean_owner = (owner or "").strip()
        expected_generation = (
            self.generation(clean_owner) if generation is None else generation
        )
        clean_query = (query or "").strip()[:MAX_QUERY_CHARS]
        canonical: list[tuple[str, int, str]] = []
        seen: set[str] = set()
        for item in list(records or [])[
            : 30000 if clean_owner.endswith("/knowledge") else MAX_RECORDS
        ]:
            parsed = _extract_record(item)
            if parsed is not None and parsed[0] not in seen:
                seen.add(parsed[0])
                canonical.append(parsed)

        async with self._lock:
            if expected_generation != self.generation(clean_owner):
                return {}
            if not canonical:
                if clean_owner:
                    try:
                        await offload(self._clear_owner_sync, clean_owner)
                    except Exception as exc:
                        self._status = "error"
                        self._error = (
                            "本地检索模型或索引不可用，请重新准备；关键词检索仍可使用"
                        )
                return {}
            if not clean_owner or not clean_query:
                return {}
            if self._embedder is None:
                if self._status == "missing" and self.marker_path.exists():
                    try:
                        await offload(self._init_local_sync)
                    except Exception as exc:
                        self._embedder = None
                        self._status = "error"
                        self._error = (
                            "本地检索模型或索引不可用，请重新准备；关键词检索仍可使用"
                        )
                        return {}
                else:
                    return {}
            try:
                return await offload(
                    self._rank_sync, clean_owner, clean_query, canonical, int(epoch)
                )
            except Exception as exc:
                self._status = "error"
                self._error = "本地检索模型或索引不可用，请重新准备；关键词检索仍可使用"
                return {}

    async def clear_owner(self, owner: str) -> None:
        self._generations[owner] = self.generation(owner) + 1
        self._generations[owner + "/knowledge"] = (
            self.generation(owner + "/knowledge") + 1
        )
        clean_owner = (owner or "").strip()
        if clean_owner:
            async with self._lock:
                await offload(self._clear_owner_sync, clean_owner)
                await offload(self._clear_owner_sync, clean_owner + "/knowledge")

    def _close_sync(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None

    async def close(self) -> None:
        async with self._lock:
            await offload(self._close_sync)


def prepare_worker(root):
    index = SemanticIndex(root)
    index.models_dir.mkdir(parents=True, exist_ok=True)
    embedder = index._create_embedder_sync(local_files_only=False)
    list(embedder.embed(["初始化"]))
    index.marker_path.write_text(MODEL, encoding="utf-8")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "--prepare-semantic":
        raise SystemExit(2)
    raise SystemExit(prepare_worker(Path(sys.argv[2])))
