"""Contracts for owner-scoped knowledge sources, chunks, and search."""

from typing import Literal

from pydantic import Field, model_validator

from app.contracts import StrictModel

MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_SOURCES_PER_OWNER = 100
MAX_DOCUMENT_CHARS = 200_000
CHUNK_SIZE = 800
CHUNK_OVERLAP = 100
MAX_ZIP_MEMBERS = 1000
MAX_ZIP_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
MAX_ZIP_SINGLE_MEMBER_BYTES = 25 * 1024 * 1024
MAX_PDF_PAGES = 500

DocumentFormat = Literal["pdf", "docx", "pptx", "xlsx", "txt", "md"]
KnowledgeFormat = Literal["pdf", "docx", "pptx", "xlsx", "txt", "md", "web"]
SUPPORTED_EXTENSIONS: dict[str, DocumentFormat] = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".pptx": "pptx",
    ".xlsx": "xlsx",
    ".txt": "txt",
    ".md": "md",
}


class KnowledgeChunk(StrictModel):
    id: str = Field(min_length=1, max_length=160)
    text: str = Field(min_length=1, max_length=CHUNK_SIZE)
    location: str = Field(min_length=1, max_length=500)


class KnowledgeSourceData(StrictModel):
    filename: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=300)
    format: KnowledgeFormat
    course_id: str | None = None
    chunks: list[KnowledgeChunk] = Field(min_length=1)
    created_at: str = Field(min_length=1, max_length=64)
    source_type: Literal["document", "web"] = "document"
    url: str | None = None
    storage_name: str | None = None
    truncated: bool = False
    untrusted: bool = True


class KnowledgeDelete(StrictModel):
    revision: int = Field(ge=1, strict=True)


class KnowledgeWebCreate(StrictModel):
    url: str = Field(min_length=1, max_length=2048)
    title: str | None = Field(default=None, max_length=300)
    course_id: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def clean(self):
        self.url = self.url.strip()
        if not self.url:
            raise ValueError("网页地址不能为空")
        if self.title is not None:
            self.title = self.title.strip() or None
        if self.course_id is not None:
            self.course_id = self.course_id.strip() or None
        return self


class KnowledgeSearchRequest(StrictModel):
    query: str = Field(min_length=1, max_length=500)
    source_ids: list[str] | None = Field(default=None, max_length=100)
    course_id: str | None = Field(default=None, max_length=100)
    limit: int = Field(default=8, ge=1, le=20)

    @model_validator(mode="after")
    def validate_query(self):
        self.query = self.query.strip()
        if not self.query:
            raise ValueError("检索关键词不能为空")
        if self.course_id is not None:
            self.course_id = self.course_id.strip() or None
        if self.source_ids is not None:
            cleaned = []
            seen = set()
            for sid in self.source_ids:
                s = sid.strip()
                if not s:
                    raise ValueError("资料标识不能为空")
                if s not in seen:
                    seen.add(s)
                    cleaned.append(s)
            self.source_ids = cleaned
        return self


class KnowledgeSearchHit(StrictModel):
    source_id: str
    chunk_id: str
    title: str
    filename: str
    format: KnowledgeFormat
    course_id: str | None = None
    location: str
    text: str
    score: float
    untrusted: bool = True
