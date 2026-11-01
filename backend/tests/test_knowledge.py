from io import BytesIO
from uuid import uuid4
import importlib.util
from pathlib import Path
import pytest
from app import knowledge
from tests.test_foundation import make_client, register_login


def upload(c, h, name="notes.md", raw="作业要求：复习论语。".encode(), key=None):
    return c.post(
        "/api/knowledge/documents",
        files={"file": (name, raw)},
        headers={**h, "Idempotency-Key": key or str(uuid4())},
    )


def test_documents_owner_receipts_citations_export_delete(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        r = upload(c, h, key="same")
        assert r.status_code == 200, r.text
        assert upload(c, h, key="same").json() == r.json()
        assert upload(c, h, raw=b"changed", key="same").status_code == 409
        source = c.get("/api/knowledge/sources/" + r.json()["id"]).json()
        assert source["data"]["chunks"][0]["location"] == "段落1"
        assert (
            not c.get("/api/tasks").json()
            and not c.get("/api/memories").json()["memories"]
        )
        exported = c.get("/api/data-export").json()
        assert len(exported["knowledge_files_base64"]) == 1
        found = c.post("/api/knowledge/search", json={"query": "论语"}, headers=h)
        assert found.json()["items"][0]["source_id"] == source["id"]
        c.post("/api/auth/logout", headers=h)
        other = register_login(c, "bob@example.com")
        assert c.get("/api/knowledge/sources").json() == []
        assert (
            c.post(
                "/api/knowledge/search",
                json={"query": "论语", "source_ids": [source["id"]]},
                headers=other,
            ).status_code
            == 404
        )
        assert (
            c.request(
                "DELETE",
                "/api/knowledge/sources/" + source["id"],
                json={"revision": source["revision"]},
                headers={**other, "Idempotency-Key": "delete"},
            ).status_code
            == 404
        )


def test_actual_formats_and_data_clear(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "fixtures",
        Path(__file__).resolve().parents[2] / "scripts/verify-frozen-knowledge.py",
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    with make_client(tmp_path) as c:
        h = register_login(c)
        for name, mime, raw in m.fixtures():
            r = upload(c, h, name, raw)
            assert r.status_code == 200, (name, r.text)
            source = c.get("/api/knowledge/sources/" + r.json()["id"]).json()
            assert source["data"]["chunks"]
        pdf = next(
            r
            for r in c.get("/api/knowledge/sources").json()
            if r["data"]["format"] == "pdf"
        )
        assert pdf["data"]["chunks"][0]["location"] == "第1页"
        result = c.post(
            "/api/data-delete",
            json={"confirmation": "删除我的所有数据"},
            headers={**h, "Idempotency-Key": "clear"},
        )
        assert result.status_code == 200, result.text
        assert not any(p.is_file() for p in (tmp_path / "uploads").rglob("*"))


@pytest.mark.parametrize(
    "name,raw",
    [
        ("bad.pdf", b"not pdf"),
        ("bad.docx", b"PKbad"),
        ("bad.exe", b"MZ"),
        ("bad.txt", b"\x00"),
        ("empty.md", b""),
    ],
)
def test_bad_formats_do_not_persist(tmp_path, name, raw):
    with make_client(tmp_path) as c:
        h = register_login(c)
        assert upload(c, h, name, raw).status_code == 422
        assert c.get("/api/knowledge/sources").json() == []


def test_source_delete_epoch_and_replay(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        r = upload(c, h).json()
        old = c.get("/api/memories").json()["settings"]["data"]["privacy_epoch"]
        result = c.request(
            "DELETE",
            "/api/knowledge/sources/" + r["id"],
            json={"revision": r["revision"]},
            headers={**h, "Idempotency-Key": "delete"},
        )
        assert result.status_code == 200, result.text
        assert (
            c.request(
                "DELETE",
                "/api/knowledge/sources/" + r["id"],
                json={"revision": r["revision"]},
                headers={**h, "Idempotency-Key": "delete"},
            ).json()
            == result.json()
        )
        assert c.get("/api/memories").json()["settings"]["data"]["privacy_epoch"] > old
        assert c.get("/api/knowledge/sources/" + r["id"]).status_code == 404


def test_search_connection_test_reports_real_status_without_persisting(
    tmp_path, monkeypatch
):
    from app import web_research

    with make_client(tmp_path) as c:
        h = register_login(c)

        async def fake(query, endpoint):
            assert endpoint == "http://127.0.0.1:8888" and query == "连接测试"
            return {"items": [], "provider": "SearXNG"}

        monkeypatch.setattr(web_research, "search_web", fake)
        result = c.post(
            "/api/integrations/search/test",
            json={"endpoint": "http://127.0.0.1:8888"},
            headers=h,
        )
        assert result.status_code == 200, result.text
        assert result.json()["connected"] is True
        assert not c.get("/api/integrations").json()["search"]["configured"]


def test_data_clear_invalidates_inflight_document_parse(tmp_path, monkeypatch):
    import threading

    started, release = threading.Event(), threading.Event()
    original = knowledge.extract_document

    def slow(*args):
        started.set()
        assert release.wait(10)
        return original(*args)

    monkeypatch.setattr(knowledge, "extract_document", slow)
    with make_client(tmp_path) as c:
        h = register_login(c)
        result = []
        worker = threading.Thread(target=lambda: result.append(upload(c, h)))
        worker.start()
        assert started.wait(5)
        cleared = c.post(
            "/api/data-delete",
            json={"confirmation": "删除我的所有数据"},
            headers={**h, "Idempotency-Key": "clear-during-upload"},
        )
        release.set()
        worker.join(10)
        assert cleared.status_code == 200 and result[0].status_code == 409
        assert c.get("/api/knowledge/sources").json() == []
        assert not any(p.is_file() for p in (tmp_path / "uploads").rglob("*"))


def test_semantic_disable_invalidates_inflight_search_and_orm_snapshot(tmp_path):
    import threading
    from app.semantic_index import SemanticIndex
    from tests.test_semantic_index import FakeChineseEmbedder
    from app.db_sessions import sqlite_transaction

    started, release = threading.Event(), threading.Event()
    with make_client(tmp_path) as c:
        h = register_login(c)
        upload(c, h)
        idx = SemanticIndex(tmp_path / "index", embedder=FakeChineseEmbedder())
        c.app.state.semantic_index = idx
        c.app.state.sessions.configure(
            info={"semantic_index": idx, "data_generations": {}}
        )
        c.put(
            "/api/integrations/semantic",
            json={"enabled": True},
            headers={**h, "Idempotency-Key": "enabled"},
        )
        original = idx.rank

        async def paused(*a, **kw):
            import asyncio

            started.set()
            await asyncio.to_thread(release.wait, 10)
            return await original(*a, **kw)

        idx.rank = paused
        results = []
        worker = threading.Thread(
            target=lambda: results.append(
                c.post("/api/knowledge/search", json={"query": "作业"}, headers=h)
            )
        )
        worker.start()
        assert started.wait(5)
        disabled = c.put(
            "/api/integrations/semantic",
            json={"enabled": False},
            headers={**h, "Idempotency-Key": "disabled"},
        )
        release.set()
        worker.join(10)
        assert disabled.status_code == 200 and results[0].json()["mode"] == "keyword"
        assert idx._client is None
        c.portal.call(idx.close)


def test_office_zip_expansion_limit_and_scan_pdf_are_actionable(tmp_path):
    import zipfile
    from pypdf import PdfWriter
    stream=BytesIO()
    with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml','x')
        archive.writestr('word/document.xml',b'x'*(26*1024*1024))
    with make_client(tmp_path) as c:
        h=register_login(c)
        assert upload(c,h,'bomb.docx',stream.getvalue()).status_code==422
        writer=PdfWriter();writer.add_blank_page(100,100);stream=BytesIO();writer.write(stream)
        response=upload(c,h,'scan.pdf',stream.getvalue())
        assert response.status_code==422 and '没有可读取的文字' in response.json()['detail']
        assert c.get('/api/knowledge/sources').json()==[]
