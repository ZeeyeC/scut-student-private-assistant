import socket
import httpx
import pytest
from fastapi import HTTPException
from app import web_research as wr
from mcp_server_fetch import server as _fetch_server

RealAsyncClient = httpx.AsyncClient


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _patch_client(monkeypatch, handler):
    monkeypatch.setattr(
        wr.httpx,
        "AsyncClient",
        lambda **kw: RealAsyncClient(transport=httpx.MockTransport(handler), **kw),
    )


def _patch_dns(monkeypatch, mapping):
    def fake_getaddrinfo(host, port, *args):
        ips = mapping.get(host, [])
        if isinstance(ips, str):
            ips = [ips]
        if not ips:
            raise socket.gaierror("nxdomain")
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port)) for ip in ips]

    monkeypatch.setattr(wr.socket, "getaddrinfo", fake_getaddrinfo)


def test_parse_public_url_rejects_bypasses():
    assert wr.parse_public_url("https://example.com:443/a").hostname == "example.com"
    assert wr.parse_public_url("http://example.com:80/a").hostname == "example.com"
    bad_urls = [
        "ftp://example.com/file",
        "javascript:alert(1)",
        "https://user:pass@example.com/",
        "http://user@example.com/",
        "https://example.com\\@evil.com/",
        "https://example.com:8443/path",
        "https://example.com:80/path",
        "http://example.com:443/path",
        "http://localhost/test",
    ]
    for u in bad_urls:
        with pytest.raises(HTTPException) as exc:
            wr.parse_public_url(u)
        assert exc.value.status_code == 422


@pytest.mark.anyio
async def test_resolve_public_blocks_private_mapped_and_mixed_dns(monkeypatch):
    _patch_dns(
        monkeypatch,
        {
            "priv.example": ["10.0.0.1"],
            "loop.example": ["127.0.0.1"],
            "mapped.example": ["::ffff:93.184.216.34"],
            "mixed.example": ["93.184.216.34", "192.168.1.1"],
            "pub.example": ["93.184.216.34"],
        },
    )
    for host in ("priv.example", "loop.example", "mapped.example", "mixed.example"):
        with pytest.raises(HTTPException) as exc:
            await wr.resolve_public(f"https://{host}/")
        assert exc.value.status_code == 422
    parsed, ip = await wr.resolve_public("https://pub.example/ok")
    assert parsed.hostname == "pub.example" and ip == "93.184.216.34"


@pytest.mark.anyio
async def test_read_webpage_pinning_html_redirects_and_limits(monkeypatch):
    _patch_dns(
        monkeypatch,
        {"example.com": "93.184.216.34", "internal.example": "10.0.0.8"},
    )
    seen = []

    def handler(req: httpx.Request):
        seen.append(
            (
                req.url.host,
                req.headers.get("Host"),
                req.extensions.get("sni_hostname"),
                req.url.path,
            )
        )
        if req.url.path == "/ok":
            body = "<html><head><title> 课程指南 </title></head><body><h1>第一章</h1><p>线性代数基础</p></body></html>"
            return httpx.Response(
                200, headers={"content-type": "text/html; charset=utf-8"}, text=body
            )
        if req.url.path == "/to-private":
            return httpx.Response(
                302, headers={"location": "https://internal.example/secret"}
            )
        if req.url.path == "/huge":
            return httpx.Response(
                200,
                headers={"content-type": "text/plain"},
                content=b"x" * (2 * 1024 * 1024 + 5),
            )
        if req.url.path == "/pdf":
            return httpx.Response(
                200, headers={"content-type": "application/pdf"}, content=b"%PDF-1.5"
            )
        raise httpx.ConnectError("internal-socket-detail-10.0.0.8")

    _patch_client(monkeypatch, handler)
    res = await wr.read_webpage("https://example.com/ok")
    assert seen[0] == ("93.184.216.34", "example.com", "example.com", "/ok")
    assert (
        res["title"] == "课程指南"
        and "线性代数基础" in res["text"]
        and res["untrusted"] is True
    )

    with pytest.raises(HTTPException) as exc:
        await wr.read_webpage("https://example.com/to-private")
    assert exc.value.status_code == 422

    with pytest.raises(HTTPException) as exc:
        await wr.read_webpage("https://example.com/huge")
    assert exc.value.status_code == 413

    with pytest.raises(HTTPException) as exc:
        await wr.read_webpage("https://example.com/pdf")
    assert exc.value.status_code == 422

    with pytest.raises(HTTPException) as exc:
        await wr.read_webpage("https://example.com/err")
    assert (
        exc.value.status_code == 422
        and "internal-socket-detail" not in exc.value.detail
    )


@pytest.mark.anyio
async def test_search_web_searxng_config_top5_and_sanitized_error(monkeypatch):
    with pytest.raises(HTTPException) as exc:
        await wr.search_web("微积分", "")
    assert exc.value.status_code == 409

    results = [
        {"title": "bad", "url": "http://localhost/private", "content": "skip"}
    ] + [
        {"title": f"T{i}", "url": f"https://example.com/{i}", "content": f"C{i}"}
        for i in range(6)
    ]
    _patch_client(
        monkeypatch, lambda req: httpx.Response(200, json={"results": results})
    )
    out = await wr.search_web("微积分", "https://searx.example.com")
    assert out["provider"] == "SearXNG" and len(out["items"]) == 5
    assert [it["url"] for it in out["items"]] == [
        f"https://example.com/{i}" for i in range(5)
    ]

    def fail_handler(req: httpx.Request):
        raise httpx.ReadTimeout("secret-searx-token-xyz")

    _patch_client(monkeypatch, fail_handler)
    with pytest.raises(HTTPException) as exc:
        await wr.search_web("微积分", "https://searx.example.com")
    assert exc.value.status_code == 422 and "secret-searx-token" not in exc.value.detail


@pytest.mark.anyio
async def test_extraction_does_not_spawn_node_or_install_packages(monkeypatch):
    import subprocess

    def forbidden(*a, **kw):
        raise AssertionError("Web parsing must not spawn Node/npm")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    assert "课程内容" in wr.extract_html("<html><body><p>课程内容</p></body></html>")


@pytest.mark.anyio
async def test_fake_ip_network_resolves_real_public_address_before_connect(monkeypatch):
    _patch_dns(monkeypatch, {"example.com": ["198.18.0.91"]})
    calls = []

    def doh(req):
        calls.append(str(req.url))
        assert req.url.host == "dns.google" and req.url.params["name"] == "example.com"
        return httpx.Response(
            200, json={"Status": 0, "Answer": [{"type": 1, "data": "93.184.216.34"}]}
        )

    _patch_client(monkeypatch, doh)
    _, ip = await wr.resolve_public("https://example.com/a")
    assert ip == "93.184.216.34" and len(calls) == 1
