"""组合分析测试。"""


def _write_date_module(client, record_date, module_id, text, title=""):
    current = client.get(
        f"/api/workspaces/{record_date}/modules/{module_id}"
    ).json()
    response = client.put(
        f"/api/workspaces/{record_date}/modules/{module_id}",
        json={
            "text_content": text,
            "display_title": title,
            "revision": current["revision"],
            "status": "draft",
        },
    )
    assert response.status_code == 200


def test_create_analysis_is_bound_to_record_date(client):
    record_date = "2026-07-30"
    _write_date_module(
        client,
        record_date,
        1,
        "测试分析内容",
        "宁德时代 300750",
    )

    response = client.post(
        "/api/analysis",
        json={
            "module_ids": [1],
            "analysis_request": "测试",
            "combination_name": "测试组合",
            "record_date": record_date,
        },
    )
    assert response.status_code == 202
    assert response.json()["record_date"] == record_date

    detail = client.get(f"/api/analysis/{response.json()['id']}/detail")
    assert detail.status_code == 200
    data = detail.json()
    assert data["analysis"]["record_date"] == record_date
    assert data["snapshots"][0]["display_title"] == "宁德时代 300750"
    assert data["snapshots"][0]["text_content"] == "测试分析内容"


def test_analysis_uses_selected_date_not_other_day(client):
    _write_date_module(client, "2026-07-30", 0, "七月三十日内容")
    _write_date_module(client, "2026-07-31", 0, "七月三十一日内容")
    response = client.post(
        "/api/analysis",
        json={
            "module_ids": [0],
            "analysis_request": "",
            "combination_name": "",
            "record_date": "2026-07-30",
        },
    )
    assert response.status_code == 202
    detail = client.get(f"/api/analysis/{response.json()['id']}/detail").json()
    assert detail["snapshots"][0]["text_content"] == "七月三十日内容"


def test_ai_input_contains_date_title_and_module_text():
    from app.services.ai import build_analysis_input

    content = build_analysis_input(
        [
            {
                "record_date": "2026-07-30",
                "order_index": 0,
                "module_name": "股票1",
                "display_title": "宁德时代 300750",
                "text_content": "关注趋势和成交量",
                "assets": [],
            }
        ],
        "重点关注风险",
    )
    texts = "\n".join(item["text"] for item in content if item["type"] == "text")
    assert "2026-07-30" in texts
    assert "宁德时代 300750" in texts
    assert "关注趋势和成交量" in texts
    assert "重点关注风险" in texts
