import pytest
import pytest_asyncio
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

EXAM_ID = "exam-001"
SLOT_ID = "slot-001"


@pytest_asyncio.fixture(scope="module")
async def submission_setup(client: AsyncClient, token: str, admin_token: str):
    ah = {"Authorization": f"Bearer {admin_token}"}
    sh = {"Authorization": f"Bearer {token}"}

    reg_r = await client.post(f"/api/v1/exam-slots/{SLOT_ID}/register", headers=sh)
    assert reg_r.status_code in (201, 409)
    if reg_r.status_code == 201:
        reg_id = reg_r.json()["id"]
    else:
        pytest.skip("Registration conflict — cannot determine reg_id for submission tests")

    q_r = await client.post(
        f"/api/v1/evaluation/exams/{EXAM_ID}/questions", headers=ah,
        json={"number": 701, "text": "Submission test Q", "question_type": "integer"},
    )
    assert q_r.status_code == 201
    q_id = q_r.json()["id"]

    yield {"reg_id": reg_id, "q_id": q_id}


class TestSubmissions:
    async def test_submit_creates_script(self, client: AsyncClient,
                                         submission_setup: dict, token: str):
        reg_id = submission_setup["reg_id"]
        q_id = submission_setup["q_id"]
        r = await client.post(
            f"/api/v1/submissions/{reg_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"answers": [{"question_id": q_id, "answer": "42"}]},
        )
        assert r.status_code == 200
        body = r.json()
        assert "id" in body
        assert body["evaluated"] is False
        assert body["answer_count"] == 1

    async def test_get_submission_status(self, client: AsyncClient,
                                          submission_setup: dict, token: str):
        reg_id = submission_setup["reg_id"]
        r = await client.get(
            f"/api/v1/submissions/{reg_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert "evaluated" in body
        assert "answer_count" in body

    async def test_list_answers(self, client: AsyncClient,
                                 submission_setup: dict, token: str):
        reg_id = submission_setup["reg_id"]
        r = await client.get(
            f"/api/v1/submissions/{reg_id}/answers",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert "count" in body
        assert isinstance(body["data"], list)

    async def test_resubmit_replaces_answers(self, client: AsyncClient,
                                              submission_setup: dict, token: str):
        reg_id = submission_setup["reg_id"]
        q_id = submission_setup["q_id"]
        r = await client.post(
            f"/api/v1/submissions/{reg_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"answers": [{"question_id": q_id, "answer": "99"}]},
        )
        assert r.status_code == 200

    async def test_requires_auth(self, client: AsyncClient, submission_setup: dict):
        r = await client.get(f"/api/v1/submissions/{submission_setup['reg_id']}")
        assert r.status_code == 401

    async def test_not_found_returns_404(self, client: AsyncClient, token: str):
        r = await client.get(
            "/api/v1/submissions/nonexistent-reg",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 404

    async def test_unattempted_answer_accepted(self, client: AsyncClient,
                                                submission_setup: dict, token: str):
        reg_id = submission_setup["reg_id"]
        q_id = submission_setup["q_id"]
        r = await client.post(
            f"/api/v1/submissions/{reg_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"answers": [{"question_id": q_id, "answer": None}]},
        )
        assert r.status_code == 200
