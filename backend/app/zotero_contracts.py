import ipaddress
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, model_validator

from app.contracts import StrictModel


def _is_loopback_host(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class ZoteroSettingsWrite(StrictModel):
    revision: int = Field(ge=0, strict=True)
    enabled: bool = Field(strict=True)
    mode: Literal["local", "remote"]
    endpoint: str = Field(default="", max_length=2048)
    token: str | None = Field(default=None, max_length=4096, repr=False)
    clear_token: bool = Field(default=False, strict=True)

    @model_validator(mode="before")
    @classmethod
    def _sanitize_token(cls, data):
        if isinstance(data, dict) and "token" in data:
            tok = data.get("token")
            if tok is not None:
                if (
                    not isinstance(tok, str)
                    or len(tok) > 4096
                    or any(c in "\r\n" or not c.isprintable() for c in tok)
                ):
                    data["token"] = None
                    raise ValueError("访问令牌格式无效，不能包含换行或控制字符")
                data["token"] = tok.strip() or None
        return data

    @model_validator(mode="after")
    def _validate_settings(self):
        if self.mode == "local":
            self.endpoint = ""
            return self
        ep = self.endpoint.strip()
        if not ep or "\\" in ep or any(ord(c) <= 32 or ord(c) == 127 for c in ep):
            self.token = None
            raise ValueError("远程端点 URL 格式无效")
        try:
            parsed = urlsplit(ep)
            port = parsed.port
        except ValueError:
            self.token = None
            raise ValueError("远程端点 URL 端口或格式无效") from None
        scheme = parsed.scheme.lower()
        host = (parsed.hostname or "").lower()
        if (
            scheme not in ("https", "http")
            or not host
            or not parsed.netloc
            or (port is not None and port < 1)
            or parsed.username is not None
            or parsed.password is not None
            or "@" in parsed.netloc
            or parsed.query
            or parsed.fragment
            or "?" in ep
            or "#" in ep
        ):
            self.token = None
            raise ValueError("远程端点必须为不含凭据、查询参数或片段的 URL")
        if scheme == "http" and not _is_loopback_host(host):
            self.token = None
            raise ValueError("远程端点仅支持 HTTPS 或本地回环 HTTP")
        self.endpoint = ep
        return self


class ZoteroSearch(StrictModel):
    query: str = Field(min_length=1, max_length=300)
    limit: int = Field(default=5, ge=1, le=10, strict=True)
    collection_key: str | None = Field(default=None, pattern=r"^[A-Z0-9]{8}$")

    @model_validator(mode="after")
    def _clean_query(self):
        self.query = self.query.strip()
        if not self.query:
            raise ValueError("检索关键词不能为空")
        return self


class ZoteroItem(StrictModel):
    item_key: str = Field(pattern=r"^[A-Z0-9]{8}$")
    section: Literal["metadata", "fulltext", "notes"] = "metadata"


class ZoteroCollections(StrictModel):
    limit: int = Field(default=10, ge=1, le=20, strict=True)
