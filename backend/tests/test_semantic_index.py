import asyncio
import threading
import pytest
from app.semantic_index import COLLECTION_NAME, VECTOR_DIM, SemanticIndex

CLUSTERS = [
    ("微积分", "高数", "导数", "极限", "积分"),
    ("力学", "电磁", "物理", "牛顿"),
    ("编程", "算法", "代码", "数据结构"),
]


class FakeChineseEmbedder:
    def __init__(self, *, local_files_only=False, **_):
        self.local_files_only = local_files_only
        self.embed_calls = 0

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * VECTOR_DIM
        for idx, words in enumerate(CLUSTERS):
            v[idx] = float(sum(text.count(w) for w in words) * 10)
        for ch in text:
            v[16 + (ord(ch) % (VECTOR_DIM - 16))] += 1.0
        v[0] = v[0] or 0.01
        return v

    def embed(self, texts):
        self.embed_calls += 1
        return [self._vec(t) for t in texts]

    def query_embed(self, query):
        return [self._vec(query)]


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_status_missing_no_autodownload(tmp_path):
    idx = SemanticIndex(tmp_path)
    st = await idx.status()
    assert st["available"] is False and st["status"] == "missing"
    assert not idx.marker_path.exists()
    assert (
        await idx.rank(
            "alice",
            "微积分",
            [{"id": "1", "revision": 1, "data": {"content": "高数极限"}}],
        )
        == {}
    )
    assert not idx.models_dir.exists()


@pytest.mark.anyio
async def test_rank_isolation_payload_clear_and_reindex(tmp_path):
    emb = FakeChineseEmbedder()
    idx = SemanticIndex(tmp_path, embedder=emb)
    alice_recs = [
        {
            "id": "math",
            "revision": 1,
            "data": {"key": "高数笔记", "content": "极限与导数积分"},
        },
        {
            "id": "phys",
            "revision": 2,
            "data": {"key": "大学物理", "content": "牛顿力学与电磁"},
        },
    ]
    bob_recs = [
        {
            "id": "bob_doc",
            "revision": 1,
            "data": {"key": "算法", "content": "数据结构与编程"},
        }
    ]

    res_a = await idx.rank("alice", "微积分导数复习", alice_recs, epoch=3)
    res_b = await idx.rank("bob", "算法编程", bob_recs, epoch=7)
    assert (
        set(res_a) == {"math", "phys"}
        and res_a["math"]["score"] > res_a["phys"]["score"]
    )
    assert res_a["math"]["revision"] == 1 and set(res_b) == {"bob_doc"}

    pts, _ = idx._client.scroll(
        collection_name=COLLECTION_NAME, limit=20, with_payload=True
    )
    for pt in pts:
        assert set(pt.payload.keys()) == {"owner", "id", "revision", "epoch"}
        assert "极限" not in str(pt.payload) and "content" not in pt.payload

    calls_before = emb.embed_calls
    await idx.rank("alice", "微积分", alice_recs, epoch=3)
    assert emb.embed_calls == calls_before

    alice_recs[1]["revision"] = 5
    alice_recs[1]["data"]["content"] = "微积分高数导数极限进阶"
    res_upd = await idx.rank("alice", "微积分导数", alice_recs, epoch=3)
    assert emb.embed_calls == calls_before + 1 and res_upd["phys"]["revision"] == 5

    await idx.clear_owner("alice")
    rem, _ = idx._client.scroll(
        collection_name=COLLECTION_NAME, limit=20, with_payload=True
    )
    assert [p.payload["owner"] for p in rem] == ["bob"]
    await idx.close()


@pytest.mark.anyio
async def test_offline_restart_uses_local_files_only_and_cancel_holds_lock(tmp_path):
    seen_flags = []

    def factory(**kw):
        seen_flags.append(kw.get("local_files_only"))
        return FakeChineseEmbedder(**kw)

    idx1 = SemanticIndex(tmp_path, embedder=factory)
    assert (await idx1.prepare())["available"] is True and seen_flags == [False]
    await idx1.close()

    idx2 = SemanticIndex(tmp_path, embedder=factory)
    ranked = await idx2.rank(
        "alice",
        "微积分",
        [{"id": "r1", "revision": 1, "data": {"content": "高数极限"}}],
    )
    assert seen_flags == [False, True] and "r1" in ranked

    started, release, in_thread = threading.Event(), threading.Event(), False

    def slow_embed(texts):
        nonlocal in_thread
        in_thread = True
        started.set()
        release.wait(1.0)
        in_thread = False
        return [[0.1] * VECTOR_DIM for _ in texts]

    idx2._embedder.embed = slow_embed
    task = asyncio.create_task(
        idx2.rank(
            "alice", "微积分", [{"id": "r1", "revision": 2, "data": {"content": "新"}}]
        )
    )
    await asyncio.to_thread(started.wait, 1.0)
    task.cancel()
    await asyncio.sleep(0.02)
    assert idx2._lock.locked() and in_thread is True
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not idx2._lock.locked()
    await idx2.close()


@pytest.mark.anyio
async def test_corrupt_disposable_index_can_be_cleared_and_rebuilt(tmp_path):
    idx = SemanticIndex(tmp_path, embedder=FakeChineseEmbedder())
    await idx.rank(
        "alice", "微积分", [{"id": "a", "revision": 1, "data": {"content": "高数极限"}}]
    )
    await idx.close()
    (tmp_path / "vectors/meta.json").write_text("{broken")
    rebuilt = SemanticIndex(tmp_path, embedder=FakeChineseEmbedder())
    await rebuilt.clear_owner("alice")
    assert "a" in await rebuilt.rank(
        "alice", "微积分", [{"id": "a", "revision": 1, "data": {"content": "高数极限"}}]
    )
    await rebuilt.close()


@pytest.mark.anyio
async def test_rank_cannot_repopulate_after_owner_invalidation(tmp_path):
    idx = SemanticIndex(tmp_path, embedder=FakeChineseEmbedder())
    generation = idx.generation("alice")
    await idx.clear_owner("alice")
    result = await idx.rank(
        "alice",
        "微积分",
        [{"id": "a", "revision": 1, "data": {"content": "高数"}}],
        generation=generation,
    )
    assert result == {}
    await idx.close()
