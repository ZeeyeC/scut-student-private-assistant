"""Synthetic workflow tests, NOT a measured real timetable OCR benchmark."""

import base64
import copy
from io import BytesIO
from uuid import uuid4

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.timetable_documents import prepare_document
from app.timetable_recognition import merge_pages
from tests.test_assignments import png
from tests.test_foundation import make_client, register_login


def pdf(pages=2, password=None, text=False):
    writer = PdfWriter()
    for _ in range(pages):
        page = writer.add_blank_page(width=500, height=700)
        if text:
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
                b"BT /F1 14 Tf 50 650 Td (SCUT timetable: Monday Math Weeks 1-16 Periods 1,2) Tj ET"
            )
            page[NameObject("/Contents")] = writer._add_object(stream)
    if password is not None:
        writer.encrypt(password)
    out = BytesIO()
    writer.write(out)
    return out.getvalue()


def candidate(**changes):
    c = {
        "name": "高等数学",
        "teacher": "李老师",
        "campus": "五山",
        "location": "A101",
        "weekday": 1,
        "weeks_text": "1-16周(单)",
        "periods": [1, 2],
        "evidence": [
            {"field": k, "text": v, "bbox": [0.1, 0.2, 0.8, 0.4]}
            for k, v in [
                ("name", "高等数学"),
                ("weekday", "星期一"),
                ("weeks_text", "1-16周(单)"),
                ("periods", "1-2节"),
            ]
        ],
    }
    return {**c, **changes}


class FakeTimetableVision:
    calls = 0

    def __init__(self, candidates=None, fail_page=None):
        self.candidates = candidates if candidates is not None else [candidate()]
        self.fail_page = fail_page

    async def extract_timetable(self, raw, text, page):
        self.calls += 1
        assert raw.startswith(b"\x89PNG")
        if page == self.fail_page:
            raise RuntimeError("provider secret must not leak")
        return {
            "semester_label": "2026秋季",
            "candidates": self.candidates,
            "warnings": [],
        }


def write(c, h, path, body, method="post", key=None):
    return getattr(c, method)(
        "/api" + path, json=body, headers={**h, "Idempotency-Key": key or str(uuid4())}
    )


def settings(c, h):
    s = c.get("/api/settings").json()
    s["data"].update(
        semester_name="2026秋季",
        week1_monday="2026-09-07",
        periods={
            "1": {"start": "08:00", "end": "08:45"},
            "2": {"start": "08:50", "end": "09:35"},
        },
    )
    assert write(c, h, "/settings", s, "put").status_code == 200


def upload(c, h, raw=None, key=None):
    r = c.post(
        "/api/timetable-assets",
        files={
            "file": ("课表.pdf", raw if raw is not None else pdf(), "application/pdf")
        },
        headers={**h, "Idempotency-Key": key or str(uuid4())},
    )
    assert r.status_code == 200, r.text
    return r.json()


def recognize(c, h, asset, key=None):
    response = write(
        c, h, "/timetable-jobs", {"asset_id": asset["id"], "consent": True}, key=key
    )
    assert response.status_code == 200, response.text
    return c.get("/api/jobs/" + response.json()["id"]).json()


def reviewed(d):
    p = copy.deepcopy(d["data"]["payload"])
    p["semester_confirmed"] = True
    for v in p["candidates"]:
        v["reviewed"] = True
        v["uncertain_fields"] = []
    return p


def edit(c, h, d, p):
    r = write(
        c, h, "/drafts/" + d["id"], {"revision": d["revision"], "payload": p}, "put"
    )
    assert r.status_code == 200, r.text
    return r.json()


def confirm(c, h, d, key=None):
    return write(
        c, h, f"/drafts/{d['id']}/confirm", {"revision": d["revision"]}, key=key
    )


def test_pdf_pages_deduplicate_confirm_replay_restart_and_owner_isolation(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        settings(c, h)
        c.app.state.gateway = FakeTimetableVision()
        a = upload(c, h, key="upload")
        assert upload(c, h, key="upload")["id"] == a["id"]
        assert len(list((tmp_path / "uploads").iterdir())) == 3
        assert [p["type"] for p in a["data"]["pages"]] == ["scanned_pdf", "scanned_pdf"]
        assert c.get("/api/assets/" + a["id"]).content == pdf()
        assert (
            c.get(f"/api/assets/{a['id']}/pages/2").headers["content-type"]
            == "image/png"
        )
        assert c.get(f"/api/assets/{a['id']}/pages/0").status_code == 404
        assert (
            write(
                c, h, "/assignment-jobs", {"asset_id": a["id"], "consent": True}
            ).status_code
            == 422
        )
        assert (
            write(
                c, h, "/timetable-jobs", {"asset_id": a["id"], "consent": False}
            ).status_code
            == 422
        )
        j = recognize(c, h, a, "job")
        assert j["data"]["status"] == "done", j
        assert recognize(c, h, a, "job")["id"] == j["id"]
        assert c.app.state.gateway.calls == 2
        assert j["data"]["completed_pages"] == 2
        assert c.get("/api/courses").json() == []
        d = c.get("/api/drafts/" + j["data"]["draft_id"]).json()
        assert len(d["data"]["payload"]["candidates"]) == 1
        assert {
            e["page"] for e in d["data"]["payload"]["candidates"][0]["evidence"]
        } == {1, 2}
        assert confirm(c, h, d).status_code == 422
        d = edit(c, h, d, reviewed(d))
        result = confirm(c, h, d, "confirm")
        assert result.status_code == 200, result.text
        assert confirm(c, h, d, "confirm").json() == result.json()
        assert confirm(c, h, d).json() == result.json()
        courses = c.get("/api/courses").json()
        assert len(courses) == 1
        assert courses[0]["data"]["weeks"] == list(range(1, 17, 2))
        j2 = recognize(c, h, upload(c, h))
        d2 = c.get("/api/drafts/" + j2["data"]["draft_id"]).json()
        d2 = edit(c, h, d2, reviewed(d2))
        assert confirm(c, h, d2).status_code == 200
        assert c.get("/api/courses").json() == courses
        cookie = dict(c.cookies)
    with make_client(tmp_path) as c:
        c.cookies.update(cookie)
        assert c.get("/api/courses").json() == courses
        assert c.get("/api/timetable-jobs").json()[-1]["data"]["status"] == "done"
        c.post("/api/auth/logout", headers=h)
        register_login(c, "other@example.com")
        for url in [
            f"/api/assets/{a['id']}",
            f"/api/assets/{a['id']}/pages/1",
            f"/api/timetable-assets/{a['id']}",
            f"/api/jobs/{j['id']}",
            f"/api/drafts/{d['id']}",
        ]:
            assert c.get(url).status_code == 404
        assert c.get("/api/timetable-jobs").json() == []
        assert (
            write(
                c,
                register_headers(c),
                "/timetable-jobs",
                {"asset_id": a["id"], "consent": True},
            ).status_code
            == 404
        )


def register_headers(c):
    return {
        "Origin": "http://testserver",
        "X-CSRF-Token": c.get("/api/csrf").json()["csrf_token"],
    }


@pytest.mark.parametrize(
    "change",
    [
        {"weeks_text": None},
        {"weeks_text": "1-40周"},
        {"weeks_text": "待定"},
        {"weekday": None},
        {"periods": []},
        {"periods": [1, 3]},
        {"periods": [99]},
        {"name": "   "},
    ],
)
def test_cannot_bypass_missing_critical_time_by_claiming_reviewed(tmp_path, change):
    with make_client(tmp_path) as c:
        h = register_login(c)
        settings(c, h)
        c.app.state.gateway = FakeTimetableVision([candidate(**change)])
        j = recognize(c, h, upload(c, h, raw=png()))
        assert j["data"]["status"] == "done"
        d = c.get("/api/drafts/" + j["data"]["draft_id"]).json()
        d = edit(c, h, d, reviewed(d))
        assert confirm(c, h, d).status_code == 422
        assert c.get("/api/courses").json() == []


def test_correct_missing_field_and_exclude_candidate_and_guard_evidence(tmp_path):
    with make_client(tmp_path) as c:
        h = register_login(c)
        settings(c, h)
        c.app.state.gateway = FakeTimetableVision(
            [candidate(weeks_text=None), candidate(name="实践课", periods=[])]
        )
        j = recognize(c, h, upload(c, h, raw=png()))
        d = c.get("/api/drafts/" + j["data"]["draft_id"]).json()
        p = reviewed(d)
        p["candidates"][0]["evidence"][0]["text"] = "伪造原文"
        assert (
            write(
                c, h, "/drafts/" + d["id"], {"revision": 1, "payload": p}, "put"
            ).status_code
            == 422
        )
        p = reviewed(d)
        p["candidates"][0]["weeks_text"] = "3-8周"
        p["candidates"][1]["excluded"] = True
        d2 = edit(c, h, d, p)
        assert (
            write(
                c, h, "/drafts/" + d["id"], {"revision": 1, "payload": p}, "put"
            ).status_code
            == 409
        )
        assert confirm(c, h, d2).status_code == 200
        assert c.get("/api/courses").json()[0]["data"]["weeks"] == [3, 4, 5, 6, 7, 8]


def test_partial_model_failure_and_missing_configuration_never_create_partial_draft(
    tmp_path,
):
    with make_client(tmp_path) as c:
        h = register_login(c)
        a = upload(c, h)
        c.app.state.gateway = FakeTimetableVision(fail_page=2)
        j = recognize(c, h, a)
        assert j["data"]["status"] == "failed"
        assert "secret" not in j["data"]["error"]
        assert c.get("/api/drafts").json() == []
        from app.model_gateway import ModelGateway

        c.app.state.gateway = ModelGateway(c.app.state.config)
        j = recognize(c, h, a)
        assert "模型未配置" in j["data"]["error"]
        assert c.get("/api/courses").json() == []


@pytest.mark.parametrize(
    "raw,status",
    [
        (b"%PDF-broken", 422),
        (b"not an image", 422),
        (b"%PDF-" + b"x" * (20 * 1024 * 1024), 413),
        (b"x" * (10 * 1024 * 1024 + 1), 413),
        (pdf(11), 413),
        (pdf(1, password="secret"), 422),
        (pdf(1, password=""), 422),
    ],
)
def test_invalid_documents_rejected_without_assets(tmp_path, raw, status):
    with make_client(tmp_path) as c:
        h = register_login(c)
        r = c.post(
            "/api/timetable-assets",
            files={"file": ("x.pdf", raw)},
            headers={**h, "Idempotency-Key": str(uuid4())},
        )
        assert r.status_code == status, r.text
        assert list((tmp_path / "uploads").iterdir()) == []


def test_text_pdf_preserves_text_and_image_original_bytes():
    suffix, mime, pages = prepare_document(pdf(1, text=True))
    assert suffix == "pdf" and mime == "application/pdf"
    assert pages[0]["type"] == "text_pdf" and "Monday Math" in pages[0]["text"]
    suffix, mime, pages = prepare_document(png())
    assert suffix == "png" and pages[0]["type"] == "image"


def test_missing_evidence_is_uncertain_and_semesters_do_not_merge():
    data = merge_pages(
        [
            {"semester_label": "fall", "candidates": [candidate(evidence=[])]},
            {
                "semester_label": "spring",
                "candidates": [candidate(weeks_text="1-16(单)")],
            },
        ],
        20,
    )
    assert data["semester_label"] == "" and data["semester_confirmed"] is False
    assert len(data["candidates"]) == 1
    assert {"name", "weekday", "periods", "weeks_text"} <= set(
        data["candidates"][0]["uncertain_fields"]
    )
    assert "不一致" in data["warnings"][-1]


def test_export_backup_and_delete_include_original_and_rendered_pages(tmp_path):
    from app.backup import backup, restore

    with make_client(tmp_path) as c:
        h = register_login(c)
        a = upload(c, h)
        cookie = dict(c.cookies)
        files = {p.name: p.read_bytes() for p in (tmp_path / "uploads").iterdir()}
        export = c.get("/api/data-export").json()
        assert export["schema_version"] == 2
        assert export["images_png_base64"] == {}
        assert {
            k: base64.b64decode(v) for k, v in export["asset_files_base64"].items()
        } == files
    backup(
        tmp_path / "test.db",
        tmp_path / "agent.db",
        tmp_path / "uploads",
        tmp_path / "backup.zip",
    )
    restore(tmp_path / "backup.zip", tmp_path / "restored")
    assert {
        p.name: p.read_bytes() for p in (tmp_path / "restored/uploads").iterdir()
    } == files
    with make_client(tmp_path) as c:
        c.cookies.update(cookie)
        assert (
            write(
                c, h, "/data-delete", {"confirmation": "删除我的所有数据"}
            ).status_code
            == 200
        )
        assert list((tmp_path / "uploads").iterdir()) == []
        assert c.get("/api/assets/" + a["id"]).status_code == 404


def test_preview_no_writes_semester_guard_and_invalid_region_is_not_guessed(tmp_path):
    from app.timetable_contracts import TimetableEvidence

    evidence = TimetableEvidence(field="name", text="Math", bbox=[100, 100, 900, 500])
    assert evidence.bbox is None and evidence.bbox_note
    with make_client(tmp_path) as c:
        h = register_login(c)
        settings(c, h)
        c.app.state.gateway = FakeTimetableVision()
        j = recognize(c, h, upload(c, h, raw=png()))
        d = c.get("/api/drafts/" + j["data"]["draft_id"]).json()
        p = reviewed(d)
        preview = write(
            c,
            h,
            f"/drafts/{d['id']}/timetable-preview",
            {"revision": d["revision"], "payload": p},
        )
        assert preview.status_code == 200
        assert preview.json() == {
            "added": ["高等数学"],
            "reused": [],
            "existing_kept": 0,
        }
        assert c.get("/api/courses").json() == []
        p["semester_label"] = "2027春季"
        wrong = edit(c, h, d, p)
        assert confirm(c, h, wrong).status_code == 422
        assert c.get("/api/courses").json() == []
