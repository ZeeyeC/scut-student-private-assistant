"""Public-page connector: pinned DNS, bounded redirects, official Fetch extraction."""

import asyncio
import ipaddress
import re
import socket
from datetime import datetime, timezone
from urllib.parse import urlsplit, urljoin

import httpx
from fastapi import HTTPException


def extract_html(html):
    # Same ReadabiliPy + Markdownify pipeline as official Fetch, with the
    # packaged pure-Python extractor. Never installs Node on a user's machine.
    from readabilipy import simple_json_from_html_string
    from markdownify import markdownify

    content = simple_json_from_html_string(html, use_readability=False).get("content")
    return markdownify(content or "", heading_style="ATX")


def parse_public_url(url):
    try:
        if len(url) > 2048 or any(ord(c) < 33 for c in url) or "\\" in url:
            raise ValueError()
        p = urlsplit(url)
        if (
            p.scheme not in {"https", "http"}
            or not p.hostname
            or p.username
            or p.password
            or p.port not in (None, 443 if p.scheme == "https" else 80)
        ):
            raise ValueError()
        if p.hostname.casefold().rstrip(".") in {"localhost", "localhost.localdomain"}:
            raise ValueError()
        p.hostname.encode("idna")
        return p
    except (ValueError, UnicodeError):
        raise HTTPException(
            422, "请输入不含账号的公共HTTP/HTTPS网页地址，仅支持默认端口"
        ) from None


async def resolve_public(url):
    p = parse_public_url(url)
    try:
        records = await asyncio.to_thread(
            socket.getaddrinfo,
            p.hostname,
            p.port or (443 if p.scheme == "https" else 80),
            0,
            socket.SOCK_STREAM,
        )
        ips = sorted({r[4][0] for r in records})
        # TUN/Fake-IP resolvers return RFC2544 placeholders for public names.
        # Never connect to them. Resolve an actual public IPv4 over HTTPS first.
        fake_network = ipaddress.ip_network("198.18.0.0/15")
        if any(
            ipaddress.ip_address(ip).version == 4
            and ipaddress.ip_address(ip) in fake_network
            for ip in ips
        ):
            async with httpx.AsyncClient(
                trust_env=False, timeout=8, follow_redirects=False
            ) as resolver:
                result = await resolver.get(
                    "https://dns.google/resolve",
                    params={"name": p.hostname, "type": "A"},
                )
                result.raise_for_status()
                payload = result.json()
                ips = [
                    a["data"] for a in payload.get("Answer", []) if a.get("type") == 1
                ]
        if not ips or any(
            not ipaddress.ip_address(ip).is_global
            or getattr(ipaddress.ip_address(ip), "ipv4_mapped", None) is not None
            for ip in ips
        ):
            raise ValueError()
    except (OSError, ValueError, httpx.HTTPError):
        raise HTTPException(
            422, "网页地址无法解析为公共网络地址；不支持本机、私网或受保护地址"
        ) from None
    return p, ips[0]


async def read_webpage(url):
    try:
        async with asyncio.timeout(20):
            async with httpx.AsyncClient(
                trust_env=False, timeout=10, follow_redirects=False
            ) as client:
                for redirect in range(4):
                    parsed, ip = await resolve_public(url)
                    target = httpx.URL(url).copy_with(host=ip)
                    # Connect to validated IP; keep original TLS hostname and HTTP Host.
                    async with client.stream(
                        "GET",
                        target,
                        headers={
                            "Host": parsed.hostname.encode("idna").decode(),
                            "User-Agent": "CampusCompanion/2.7 (study-research)",
                            "Accept": "text/html,text/plain",
                        },
                        extensions={"sni_hostname": parsed.hostname},
                    ) as response:
                        if response.status_code in {301, 302, 303, 307, 308}:
                            if redirect == 3 or not response.headers.get("location"):
                                raise HTTPException(422, "网页重定向过多或缺少地址")
                            url = urljoin(url, response.headers["location"])
                            continue
                        if response.status_code >= 400:
                            raise HTTPException(
                                422, "网页无法读取，可能需要登录或拒绝了访问"
                            )
                        mime = (
                            response.headers.get("content-type", "")
                            .split(";")[0]
                            .lower()
                        )
                        if mime not in {
                            "text/html",
                            "text/plain",
                            "application/xhtml+xml",
                        }:
                            raise HTTPException(
                                422, "仅支持公开的HTML或纯文本网页，文件请通过资料上传"
                            )
                        raw = bytearray()
                        async for chunk in response.aiter_bytes(chunk_size=65536):
                            raw.extend(chunk)
                            if len(raw) > 2 * 1024 * 1024:
                                raise HTTPException(
                                    413, "网页超过2 MiB，请选择较短页面"
                                )
                        html = raw.decode(
                            response.encoding or "utf-8", errors="replace"
                        )
                        title = parsed.hostname
                        if mime != "text/plain":
                            from bs4 import BeautifulSoup

                            soup = BeautifulSoup(html, "html.parser")
                            if soup.title:
                                title = (
                                    soup.title.get_text(" ", strip=True)[:300] or title
                                )
                            text = await asyncio.to_thread(extract_html, html)
                        else:
                            text = html
                        if not text.strip():
                            raise HTTPException(
                                422, "网页没有可读取的正文，可能需要登录或执行脚本"
                            )
                        return {
                            "url": url,
                            "title": title,
                            "text": text[:30000],
                            "truncated": len(text) > 30000,
                            "fetched_at": datetime.now(timezone.utc).isoformat(),
                            "untrusted": True,
                        }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            422, "网页连接失败或超时，请检查网络或换一个公开链接"
        ) from None


def validate_search_endpoint(endpoint):
    endpoint = endpoint.strip().rstrip("/")
    if not endpoint:
        return ""
    try:
        p = urlsplit(endpoint)
        if (
            len(endpoint) > 2048
            or any(ord(c) < 33 for c in endpoint)
            or "\\" in endpoint
            or not p.hostname
            or p.username
            or p.password
            or p.query
            or p.fragment
        ):
            raise ValueError()
        if p.scheme != "https" and not (
            p.scheme == "http" and p.hostname in {"127.0.0.1", "localhost", "::1"}
        ):
            raise ValueError()
        _ = p.port
        return endpoint
    except ValueError:
        raise HTTPException(
            422, "搜索服务须为HTTPS或本机HTTP地址，不含账号、查询参数或片段"
        ) from None


async def search_web(query, endpoint):
    if not endpoint:
        raise HTTPException(409, "尚未配置SearXNG搜索服务；仍可直接读取公开网页链接")
    if not query.strip() or len(query) > 300:
        raise HTTPException(422, "搜索词应为1至300字")
    endpoint = validate_search_endpoint(endpoint)
    try:
        async with httpx.AsyncClient(
            timeout=15, trust_env=False, follow_redirects=False
        ) as client:
            target = (
                endpoint
                if urlsplit(endpoint).path.endswith("/search")
                else endpoint + "/search"
            )
            async with client.stream(
                "GET", target, params={"q": query, "format": "json"}
            ) as response:
                response.raise_for_status()
                raw = bytearray()
                async for part in response.aiter_bytes(chunk_size=65536):
                    raw.extend(part)
                    if len(raw) > 2 * 1024 * 1024:
                        raise ValueError()
                import json

                payload = json.loads(raw)
        items = []
        for r in payload.get("results", [])[:30]:
            if not isinstance(r, dict):
                continue
            try:
                parse_public_url(r.get("url", ""))
            except HTTPException:
                continue
            items.append(
                {
                    "title": str(r.get("title", ""))[:300],
                    "url": r["url"],
                    "content": str(r.get("content", ""))[:1200],
                    "untrusted": True,
                }
            )
            if len(items) >= 5:
                break
        return {
            "items": items,
            "provider": "SearXNG",
            "query": query,
            "untrusted": True,
        }
    except Exception:
        raise HTTPException(
            422, "搜索服务连接失败或未开放JSON，请检查服务地址和配置"
        ) from None


def research_router(config, get_db, current_user):
    from fastapi import APIRouter, Depends
    from pydantic import Field
    from app.contracts import StrictModel

    class ReadRequest(StrictModel):
        url: str = Field(min_length=1, max_length=2048)

    class SearchRequest(StrictModel):
        query: str = Field(min_length=1, max_length=300)

    router = APIRouter(prefix="/api/research")

    @router.post("/read")
    async def read(body: ReadRequest, user=Depends(current_user), db=Depends(get_db)):
        await db.commit()
        return await read_webpage(body.url)

    @router.post("/search")
    async def search(
        body: SearchRequest, user=Depends(current_user), db=Depends(get_db)
    ):
        from app.integrations_routes import search_endpoint

        endpoint = await search_endpoint(db, str(user.id), config)
        await db.commit()
        return await search_web(body.query, endpoint)

    return router
