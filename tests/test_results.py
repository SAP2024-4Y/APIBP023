import pytest
import pytest_asyncio
from httpx import AsyncClient


@pytest_asyncio.fixture(scope="module")
async def results_setup(client: AsyncClient, token: str, admin_token: str) -> dict:
    reg_resp = await client.post(
        "/api/v1/exam-slots/slot-003/register",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert reg_resp.status_code in (201, 409)
    if reg_resp.status_code == 409:
        from sqlalchemy import select
        from src.database import async_session_maker
        from src.models import Registration
        async with async_session_maker() as db:
            result = await db.execute(
                select(Registration)
                .where(Registration.slot_id == "slot-003")
                .limit(1)
            )
            reg_id = (result.scalar_one_or_none()).id
    else:
        reg_id = reg_resp.json()["id"]

    q_resp = await client.post(
        "/api/v1/evaluation/exams/exam-002/questions",
        json={"number": 1, "text": "Results flow question", "question_type": "integer"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert q_resp.status_code in (201, 409)
    if q_resp.status_code == 409:
        q_list = await client.get(
            "/api/v1/evaluation/exams/exam-002/questions",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        q_id = next(q["id"] for q in q_list.json()["data"] if q["number"] == 1)
    else:
        q_id = q_resp.json()["id"]

    await client.put(
        f"/api/v1/evaluation/questions/{q_id}/answer-key",
        json={"correct_answer": "42"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    pol_resp = await client.post(
        "/api/v1/evaluation/exams/exam-002/marking-policy",
        json={"marks_correct": 5.0, "marks_wrong": -1.0, "marks_unattempted": 0.0},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert pol_resp.status_code in (201, 409)

    sub_resp = await client.post(
        f"/api/v1/submissions/{reg_id}",
        json={"answers": [{"question_id": q_id, "answer": "42"}]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert sub_resp.status_code in (200, 201)
    script_id = sub_resp.json()["id"]

    eval_resp = await client.post(
        f"/api/v1/evaluation/scripts/{script_id}/evaluate",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert eval_resp.status_code in (200, 409)

    return {"registration_id": reg_id, "script_id": script_id}


class TestMyResults:
    async def test_requires_auth(self, client: AsyncClient):
        resp = await client.get("/api/v1/results/me")
        assert resp.status_code == 401

    async def test_returns_list(self, client: AsyncClient, token: str, results_setup: dict):
        resp = await client.get(
            "/api/v1/results/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert "count" in body
        assert body["count"] >= 1

    async def test_result_summary_fields(self, client: AsyncClient, token: str, results_setup: dict):
        resp = await client.get(
            "/api/v1/results/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        entry = resp.json()["data"][0]
        assert "registration_id" in entry
        assert "slot_id" in entry
        assert "status" in entry
        assert "score" in entry
        assert "grade" in entry
        assert entry["status"] == "completed"


class TestRegistrationDetail:
    async def test_requires_auth(self, client: AsyncClient, results_setup: dict):
        resp = await client.get(f"/api/v1/results/registrations/{results_setup['registration_id']}")
        assert resp.status_code == 401

    async def test_student_can_view_own(self, client: AsyncClient, token: str, results_setup: dict):
        resp = await client.get(
            f"/api/v1/results/registrations/{results_setup['registration_id']}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["registration_id"] == results_setup["registration_id"]
        assert body["status"] == "completed"
        assert body["score"] is not None
        assert body["grade"] is not None
        assert "questions" in body

    async def test_admin_can_view(self, client: AsyncClient, admin_token: str, results_setup: dict):
        resp = await client.get(
            f"/api/v1/results/registrations/{results_setup['registration_id']}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200

    async def test_not_found(self, client: AsyncClient, token: str):
        resp = await client.get(
            "/api/v1/results/registrations/nonexistent-id",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "REGISTRATION_NOT_FOUND"

    async def test_question_breakdown_present(self, client: AsyncClient, token: str, results_setup: dict):
        resp = await client.get(
            f"/api/v1/results/registrations/{results_setup['registration_id']}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["questions"]) >= 1
        q = body["questions"][0]
        assert "question_number" in q
        assert "question_type" in q
        assert "student_answer" in q
        assert "correct_answer" in q


class TestExamLeaderboard:
    async def test_requires_auth(self, client: AsyncClient):
        resp = await client.get("/api/v1/results/exams/exam-002")
        assert resp.status_code == 401

    async def test_student_forbidden(self, client: AsyncClient, token: str):
        resp = await client.get(
            "/api/v1/results/exams/exam-002",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    async def test_admin_gets_leaderboard(self, client: AsyncClient, admin_token: str, results_setup: dict):
        resp = await client.get(
            "/api/v1/results/exams/exam-002",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["exam_id"] == "exam-002"
        assert "exam_title" in body
        assert "data" in body
        assert body["count"] >= 1

    async def test_leaderboard_entry_fields(self, client: AsyncClient, admin_token: str, results_setup: dict):
        resp = await client.get(
            "/api/v1/results/exams/exam-002",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        entry = resp.json()["data"][0]
        assert "rank" in entry
        assert "student_id" in entry
        assert "score" in entry
        assert "grade" in entry
        assert entry["rank"] == 1

    async def test_exam_not_found(self, client: AsyncClient, admin_token: str):
        resp = await client.get(
            "/api/v1/results/exams/nonexistent-exam",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "EXAM_NOT_FOUND"
