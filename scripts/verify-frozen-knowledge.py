"""Exercise bundled document converters and retrieval in the actual frozen service.
Called by verify-frozen-timetable's existing isolated identity-checked harness.
No real user data, network, model inference or semantic model download.
"""

from io import BytesIO
from uuid import uuid4
import json
import zipfile


def fixtures():
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

    writer = PdfWriter()
    page = writer.add_blank_page(600, 800)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject(
                {NameObject("/F1"): writer._add_object(font)}
            )
        }
    )
    stream = DecodedStreamObject()
    stream.set_data(
        b"BT /F1 16 Tf 50 700 Td (Synthetic physics homework: complete exercises 1 to 3.) Tj ET"
    )
    page[NameObject("/Contents")] = writer._add_object(stream)
    out = BytesIO()
    writer.write(out)
    yield "physics.pdf", "application/pdf", out.getvalue()
    out = BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr(
            "[Content_Types].xml",
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
        )
        z.writestr(
            "_rels/.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
        )
        z.writestr(
            "word/document.xml",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Synthetic chemistry homework</w:t></w:r></w:p></w:body></w:document>',
        )
    yield (
        "chemistry.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        out.getvalue(),
    )
    from pptx import Presentation

    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[1])
    slide.shapes.title.text = "Synthetic mathematics"
    slide.placeholders[1].text = "Review calculus derivatives"
    out = BytesIO()
    prs.save(out)
    yield (
        "math.pptx",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        out.getvalue(),
    )
    from openpyxl import Workbook

    wb = Workbook()
    wb.active.append(["Synthetic biology", "Read chapter 4"])
    out = BytesIO()
    wb.save(out)
    yield (
        "biology.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        out.getvalue(),
    )
    yield "notes.md", "text/markdown", "合成语文资料：复习论语。".encode()


def knowledge_checks(get, request):
    sources = []
    for filename, mime, raw in fixtures():
        boundary = "campus-" + uuid4().hex
        body = (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\nContent-Type: {mime}\r\n\r\n'.encode()
            + raw
            + f"\r\n--{boundary}--\r\n".encode()
        )
        saved = json.load(
            request(
                "/knowledge/documents",
                body,
                f"multipart/form-data; boundary={boundary}",
            )
        )
        source = get("/knowledge/sources/" + saved["id"])
        assert source["data"]["chunks"], filename
        assert source["data"]["filename"] == filename
        sources.append(source)
    assert any(
        "页" in str(c["location"]) or "page" in str(c["location"]).lower()
        for c in sources[0]["data"]["chunks"]
    )
    result = json.load(
        request("/knowledge/search", json.dumps({"query": "homework"}).encode())
    )
    assert result["items"]
    status = get("/integrations")
    assert not status["search"]["configured"]
    assert status["semantic"]["available"] is False
    assert not get("/tasks") or all(s["kind"] == "task" for s in get("/tasks"))
    request(
        "/knowledge/sources/" + sources[0]["id"],
        json.dumps({"revision": sources[0]["revision"]}).encode(),
        method="DELETE",
    ).read()
    assert all(s["id"] != sources[0]["id"] for s in get("/knowledge/sources"))
    return {
        "converters": ["PDF", "DOCX", "PPTX", "XLSX", "Markdown"],
        "source_citations": "verified",
        "delete": "verified",
        "search": "keyword",
        "semantic_model": "not downloaded",
        "real_model_calls": 0,
    }
