import pytest
import pytest_asyncio

@pytest.mark.asyncio
async def test_list_drafts_empty(app_client):
    response = await app_client.get("/api/worklogs?date=2026-04-12")
    assert response.status_code == 200
    assert response.json() == []

@pytest.mark.asyncio
async def test_update_draft(app_client):
    response = await app_client.post("/api/worklogs/seed", json={
        "date": "2026-04-12", "issue_key": "PROJ-101", "time_spent_sec": 3600, "summary": "Fixed SQL",
    })
    assert response.status_code == 201
    draft_id = response.json()["id"]

    response = await app_client.patch(f"/api/worklogs/{draft_id}", json={"summary": "Fixed SQL parser JOIN handling", "time_spent_sec": 7200})
    assert response.status_code == 200

    response = await app_client.get("/api/worklogs?date=2026-04-12")
    drafts = response.json()
    assert len(drafts) == 1
    assert drafts[0]["summary"] == "Fixed SQL parser JOIN handling"
    assert drafts[0]["time_spent_sec"] == 7200
    assert drafts[0]["user_edited"] == 1

@pytest.mark.asyncio
async def test_approve_draft(app_client):
    response = await app_client.post("/api/worklogs/seed", json={
        "date": "2026-04-12", "issue_key": "PROJ-102", "time_spent_sec": 1800, "summary": "Review PR",
    })
    draft_id = response.json()["id"]
    response = await app_client.post(f"/api/worklogs/{draft_id}/approve")
    assert response.status_code == 200

    response = await app_client.get("/api/worklogs?date=2026-04-12")
    draft = [d for d in response.json() if d["id"] == draft_id][0]
    assert draft["status"] == "approved"

@pytest.mark.asyncio
async def test_reject_draft(app_client):
    response = await app_client.post("/api/worklogs/seed", json={
        "date": "2026-04-12", "issue_key": "PROJ-103", "time_spent_sec": 900, "summary": "Meeting",
    })
    draft_id = response.json()["id"]
    response = await app_client.post(f"/api/worklogs/{draft_id}/reject")
    assert response.status_code == 200

    response = await app_client.get("/api/worklogs?date=2026-04-12")
    draft = [d for d in response.json() if d["id"] == draft_id][0]
    assert draft["status"] == "rejected"

@pytest.mark.asyncio
async def test_approve_all(app_client):
    for key in ["PROJ-201", "PROJ-202"]:
        await app_client.post("/api/worklogs/seed", json={"date": "2026-04-13", "issue_key": key, "time_spent_sec": 1800, "summary": "Work"})
    response = await app_client.post("/api/worklogs/approve-all?date=2026-04-13")
    assert response.status_code == 200
    response = await app_client.get("/api/worklogs?date=2026-04-13")
    assert all(d["status"] == "approved" for d in response.json())
