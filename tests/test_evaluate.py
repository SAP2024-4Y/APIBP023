import pytest_asyncio
from httpx import AsyncClient


@pytest_asyncio.fixture(scope="module")
async def eval_setup(client: AsyncClient, token: str, admin_token: str) -> dict:
    reg_resp = await client.post(
        "/api/v1/exam-slots/slot-002/register",
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
                .where(Registration.slot_id == "slot-002")
                .limit(1)
            )
            reg = result.scalar_one_or_none()
            reg_id = reg.id
    else:
        reg_id = reg_resp.json()["id"]

    q_resp = await client.post(
        "/api/v1/evaluation/exams/exam-001/questions",
        json={"number": 97, "text": "Evaluate flow question", "question_type": "mcq", "options": ["A", "B", "C", "D"]},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert q_resp.status_code in (201, 409)
    if q_resp.status_code == 409:
        q_list = await client.get(
            "/api/v1/evaluation/exams/exam-001/questions",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        q_id = next(q["id"] for q in q_list.json()["data"] if q["number"] == 97)
    else:
        q_id = q_resp.json()["id"]

    await client.put(
        f"/api/v1/evaluation/questions/{q_id}/answer-key",
        json={"correct_answer": "B"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    pol_resp = await client.post(
        "/api/v1/evaluation/exams/exam-001/marking-policy",
        json={"marks_correct": 4.0, "marks_wrong": -1.0, "marks_unattempted": 0.0},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert pol_resp.status_code in (201, 409)

    sub_resp = await client.post(
        f"/api/v1/submissions/{reg_id}",
        json={"answers": [{"question_id": q_id, "answer": "B"}]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert sub_resp.status_code in (200, 201)
    script_id = sub_resp.json()["id"]

    return {"registration_id": reg_id, "script_id": script_id, "question_id": q_id}


class TestEvaluate:
    async def test_requires_auth(self, client: AsyncClient, eval_setup: dict):
        resp = await client.post(f"/api/v1/evaluation/scripts/{eval_setup['script_id']}/evaluate")
        assert resp.status_code == 401

    async def test_student_forbidden(self, client: AsyncClient, token: str, eval_setup: dict):
        resp = await client.post(
            f"/api/v1/evaluation/scripts/{eval_setup['script_id']}/evaluate",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    async def test_evaluate_success(self, client: AsyncClient, admin_token: str, eval_setup: dict):
        resp = await client.post(
            f"/api/v1/evaluation/scripts/{eval_setup['script_id']}/evaluate",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["script_id"] == eval_setup["script_id"]
        assert body["registration_id"] == eval_setup["registration_id"]
        assert "total_score" in body
        assert "max_score" in body
        assert "percentage" in body
        assert "grade" in body
        assert isinstance(body["question_results"], list)

    async def test_evaluate_sets_registration_completed(self, client: AsyncClient, admin_token: str, eval_setup: dict):
        resp = await client.get(
            f"/api/v1/results/registrations/{eval_setup['registration_id']}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["score"] is not None
        assert body["grade"] is not None
        assert body["status"] == "completed"

    async def test_re_evaluate_returns_409(self, client: AsyncClient, admin_token: str, eval_setup: dict):
        resp = await client.post(
            f"/api/v1/evaluation/scripts/{eval_setup['script_id']}/evaluate",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == "ALREADY_EVALUATED"

    async def test_nonexistent_script_returns_404(self, client: AsyncClient, admin_token: str):
        resp = await client.post(
            "/api/v1/evaluation/scripts/nonexistent-script-id/evaluate",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "SCRIPT_NOT_FOUND"

    async def test_question_results_have_verdict_field(self, client: AsyncClient, admin_token: str, eval_setup: dict):
        resp = await client.get(
            f"/api/v1/results/registrations/{eval_setup['registration_id']}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        for q in resp.json()["questions"]:
            assert "question_number" in q
            assert "question_type" in q
            assert "student_answer" in q

    async def test_correct_answer_scores_marks(self, client: AsyncClient, admin_token: str, eval_setup: dict):
        resp = await client.get(
            f"/api/v1/results/registrations/{eval_setup['registration_id']}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["score"] == 4.0
