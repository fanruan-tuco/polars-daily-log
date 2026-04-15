import pytest

@pytest.mark.asyncio
async def test_get_settings(app_client):
    response = await app_client.get("/api/settings")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

@pytest.mark.asyncio
async def test_put_setting(app_client):
    response = await app_client.put("/api/settings/monitor.interval_sec", json={"value": "60"})
    assert response.status_code == 200
    response = await app_client.get("/api/settings")
    found = [s for s in response.json() if s["key"] == "monitor.interval_sec"]
    assert len(found) == 1
    assert found[0]["value"] == "60"


@pytest.mark.asyncio
async def test_default_prompts_includes_activity_summary(app_client):
    response = await app_client.get("/api/settings/default-prompts")
    assert response.status_code == 200
    data = response.json()
    assert "summarize_prompt" in data
    assert "auto_approve_prompt" in data
    assert "period_summary_prompt" in data
    assert "activity_summary_prompt" in data
    # Sanity-check core placeholders are present in the activity prompt
    template = data["activity_summary_prompt"]
    assert "{prev_summaries}" in template
    assert "{timestamp}" in template
    assert "{app_name}" in template
    assert "{ocr_text}" in template
