"""投研日期工作区与日历 API 测试。"""
import base64


TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9ZQmcAAAAASUVORK5CYII="
)


def _get_module(client, record_date: str, module_id: int):
    response = client.get(f"/api/workspaces/{record_date}/modules/{module_id}")
    assert response.status_code == 200
    return response.json()


def _update_module(
    client,
    record_date: str,
    module_id: int,
    text: str,
    display_title: str = "",
):
    current = _get_module(client, record_date, module_id)
    response = client.put(
        f"/api/workspaces/{record_date}/modules/{module_id}",
        json={
            "text_content": text,
            "display_title": display_title,
            "revision": current["revision"],
            "status": "draft",
        },
    )
    assert response.status_code == 200
    return response.json()


def test_workspace_contains_twelve_date_scoped_modules(client):
    response = client.get("/api/workspaces/2026-07-30")
    assert response.status_code == 200
    data = response.json()
    assert data["record_date"] == "2026-07-30"
    assert data["total_count"] == 12
    assert len(data["cards"]) == 12
    assert data["completed_count"] == 0


def test_module_content_is_isolated_by_record_date(client):
    _update_module(
        client,
        "2026-07-30",
        1,
        "七月三十日的判断",
        "宁德时代 300750",
    )

    first_day = _get_module(client, "2026-07-30", 1)
    second_day = _get_module(client, "2026-07-31", 1)
    assert first_day["text_content"] == "七月三十日的判断"
    assert first_day["display_title"] == "宁德时代 300750"
    assert second_day["text_content"] == ""
    assert second_day["display_title"] == ""


def test_calendar_reports_completion_by_day(client):
    _update_module(client, "2026-07-30", 0, "本周策略")
    _update_module(client, "2026-07-30", 1, "个股判断", "贵州茅台 600519")

    response = client.get("/api/workspaces/calendar", params={"month": "2026-07"})
    assert response.status_code == 200
    days = {item["date"]: item for item in response.json()["days"]}
    assert days["2026-07-30"]["completed_count"] == 2
    assert days["2026-07-30"]["status"] == "partial"


def test_copy_workspace_skips_existing_and_excludes_review_modules(client):
    _update_module(client, "2026-07-29", 0, "来源策略")
    _update_module(client, "2026-07-29", 9, "来源 AI 复盘")
    _update_module(client, "2026-07-30", 1, "目标已有内容")

    response = client.post(
        "/api/workspaces/2026-07-30/copy",
        json={
            "source_date": "2026-07-29",
            "module_ids": [0, 1, 2, 3, 4, 5, 6, 7, 8, 10],
            "overwrite": False,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert 0 in data["copied_module_ids"]
    assert 1 in data["skipped_module_ids"]

    assert _get_module(client, "2026-07-30", 0)["text_content"] == "来源策略"
    assert _get_module(client, "2026-07-30", 1)["text_content"] == "目标已有内容"
    assert _get_module(client, "2026-07-30", 9)["text_content"] == ""


def test_copy_rejects_source_with_only_empty_entries(client):
    client.get("/api/workspaces/2026-07-28")
    response = client.post(
        "/api/workspaces/2026-07-30/copy",
        json={
            "source_date": "2026-07-28",
            "module_ids": [0, 1],
            "overwrite": False,
        },
    )
    assert response.status_code == 404


def test_image_upload_does_not_invalidate_text_revision(client):
    current = _get_module(client, "2026-07-30", 1)
    original_revision = current["revision"]
    upload = client.post(
        "/api/workspaces/2026-07-30/modules/1/images",
        files={"file": ("pixel.png", TINY_PNG, "image/png")},
    )
    assert upload.status_code == 200, upload.text

    save = client.put(
        "/api/workspaces/2026-07-30/modules/1",
        json={
            "text_content": "上传图片后继续保存文字",
            "display_title": "测试股票 000001",
            "revision": original_revision,
            "status": "draft",
        },
    )
    assert save.status_code == 200, save.text
    assert _get_module(client, "2026-07-30", 1)["image_count"] == 1


def test_calendar_only_marks_completed_analysis_as_analyzed(client):
    from app.database import get_db

    with get_db() as conn:
        conn.execute(
            "INSERT INTO analyses(combination, record_date, status) VALUES ('[0]', ?, 'failed')",
            ("2026-07-30",),
        )
    failed_calendar = client.get(
        "/api/workspaces/calendar",
        params={"month": "2026-07"},
    ).json()
    failed_day = next(item for item in failed_calendar["days"] if item["date"] == "2026-07-30")
    assert failed_day["analysis_count"] == 0

    with get_db() as conn:
        conn.execute(
            "INSERT INTO analyses(combination, record_date, status) VALUES ('[0]', ?, 'completed')",
            ("2026-07-30",),
        )
    completed_calendar = client.get(
        "/api/workspaces/calendar",
        params={"month": "2026-07"},
    ).json()
    completed_day = next(
        item for item in completed_calendar["days"] if item["date"] == "2026-07-30"
    )
    assert completed_day["analysis_count"] == 1
    assert completed_day["status"] == "analyzed"


def test_invalid_dates_are_rejected(client):
    assert client.get("/api/workspaces/2026-02-30").status_code == 422
    assert client.get("/api/workspaces/calendar", params={"month": "2026-13"}).status_code == 422
