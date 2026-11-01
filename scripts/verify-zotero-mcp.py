"""Read-only real MCP transport against an explicit synthetic Zotero HTTP fixture.
Refuses an occupied Zotero port and never reads a real user's library.
"""

import argparse, asyncio, json, threading, sys
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs
from app.config import Config
from app.zotero_bridge import invoke, ALLOWED

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--service", type=Path)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
article = {
    "key": "ABCD1234",
    "version": 1,
    "data": {
        "key": "ABCD1234",
        "itemType": "journalArticle",
        "title": "Synthetic calculus paper",
        "creators": [
            {"creatorType": "author", "firstName": "Test", "lastName": "Author"}
        ],
        "date": "2026",
        "abstractNote": "Synthetic abstract",
        "publicationTitle": "Synthetic Journal",
        "collections": [],
        "tags": [],
    },
}
note = {
    "key": "NOTE1234",
    "version": 1,
    "data": {
        "key": "NOTE1234",
        "itemType": "note",
        "title": "Synthetic note",
        "parentItem": "ABCD1234",
        "note": "<p>Synthetic full text on calculus.</p>",
        "tags": [],
    },
}
attachment = {
    "key": "ATTACH01",
    "version": 1,
    "data": {
        "key": "ATTACH01",
        "itemType": "attachment",
        "contentType": "application/pdf",
        "filename": "synthetic.pdf",
        "parentItem": "ABCD1234",
        "linkMode": "imported_file",
    },
}
annotation = {
    "key": "ANNO1234",
    "version": 1,
    "data": {
        "key": "ANNO1234",
        "itemType": "annotation",
        "parentItem": "ATTACH01",
        "annotationType": "highlight",
        "annotationText": "Synthetic highlighted calculus",
        "annotationComment": "Synthetic comment",
        "annotationPageLabel": "1",
        "annotationSortIndex": "00000|000001|00000",
        "annotationPosition": '{"pageIndex":0,"rects":[[0,0,10,10]]}',
        "tags": [],
    },
}
collection = {
    "key": "COLL1234",
    "version": 1,
    "data": {
        "key": "COLL1234",
        "name": "Synthetic collection",
        "parentCollection": False,
    },
}
seen = []


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        seen.append(self.path)
        p = urlsplit(self.path)
        query = parse_qs(p.query)
        if p.path.endswith("/items/ATTACH01/fulltext"):
            payload = {"content": "Synthetic indexed paper full text on calculus."}
        elif p.path.endswith("/items/ATTACH01"):
            payload = attachment
        elif p.path.endswith("/collections"):
            payload = [collection]
        elif p.path.endswith("/items/NOTE1234"):
            payload = note
        elif p.path.endswith("/items/ABCD1234"):
            payload = article
        elif p.path.endswith("/items/ATTACH01/children"):
            payload = [annotation]
        elif p.path.endswith("/children"):
            payload = [attachment, note]
        elif p.path.endswith("/items"):
            payload = [note] if query.get("itemType") == ["note"] else [article]
        else:
            self.send_error(404)
            return
        raw = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header(
            "Total-Results", str(len(payload) if isinstance(payload, list) else 1)
        )
        self.send_header("Last-Modified-Version", "1")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        raise AssertionError("No write methods allowed")

    do_PUT = do_POST
    do_DELETE = do_POST


try:
    server = ThreadingHTTPServer(("127.0.0.1", 23119), Handler)
except OSError:
    raise SystemExit(
        "Zotero port23119 occupied; existing library preserved, no connection attempted"
    )
worker = threading.Thread(target=server.serve_forever, daemon=True)
worker.start()


async def run():
    config = Config(_env_file=None, model_api_key="")
    import app.zotero_bridge as bridge

    original = bridge.connection
    if args.service:

        def frozen(config, data, token):
            c = original(config, data, token)
            c["command"] = str(args.service.resolve())
            c["args"] = ["--zotero-mcp"]
            return c

        bridge.connection = frozen
    checks = []
    for name, params, expected in [
        ("zotero_get_collections", {"limit": 1}, "Synthetic collection"),
        (
            "zotero_search_items",
            {"query": "calculus", "limit": 5},
            "Synthetic calculus paper",
        ),
        (
            "zotero_get_item_metadata",
            {"item_key": "ABCD1234"},
            "Synthetic calculus paper",
        ),
        (
            "zotero_get_item_fulltext",
            {"item_key": "ABCD1234"},
            "Synthetic indexed paper full text",
        ),
        ("zotero_get_item_fulltext", {"item_key": "NOTE1234"}, "Synthetic full text"),
        (
            "zotero_get_notes",
            {"item_key": "ABCD1234", "limit": 5},
            "Synthetic full text",
        ),
        (
            "zotero_get_annotations",
            {"item_key": "ABCD1234", "limit": 5, "use_pdf_extraction": False},
            "Synthetic highlighted calculus",
        ),
    ]:
        result = await invoke(config, {"mode": "local"}, "", name, params)
        assert expected in result["text"], (name, result)
        assert set(result["tools"]) == ALLOWED
        checks.append(name)
    report = {
        "passed": True,
        "actual_mcp_transport": True,
        "frozen": bool(args.service),
        "tools": checks,
        "http_requests": len(seen),
        "fixture": "Explicit synthetic HTTP server on unoccupied23119; no real library or model calls",
        "real_user_library_acceptance": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False))


try:
    asyncio.run(run())
finally:
    server.shutdown()
    server.server_close()
    worker.join(5)
