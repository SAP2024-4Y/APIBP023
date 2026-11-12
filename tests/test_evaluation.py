import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

EXAM_ID = "exam-001"


class TestQuestions:
    async def test_add_mcq_question(self, client: AsyncClient, admin_token: str):
        r = await client.post(
            f"/api/v1/evaluation/exams/{EXAM_ID}/questions",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "number": 501,
                "text": "What is 2 + 2?",
                "question_type": "mcq",
                "options": ["3", "4", "5", "6"],
            },
        )
        assert r.status_code == 201
        body = r.json()
        assert body["question_type"] == "mcq"
        assert body["options"] == ["3", "4", "5", "6"]
        assert "id" in body

    async def test_add_integer_question(self, client: AsyncClient, admin_token: str):
        r = await client.post(
            f"/api/v1/evaluation/exams/{EXAM_ID}/questions",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"number": 502, "text": "What is 6 × 7?", "question_type": "integer"},
        )
        assert r.status_code == 201
        assert r.json()["question_type"] == "integer"

    async def test_add_descriptive_question(self, client: AsyncClient, admin_token: str):
        r = await client.post(
            f"/api/v1/evaluation/exams/{EXAM_ID}/questions",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "number": 503,
                "text": "Describe photosynthesis.",
                "question_type": "descriptive",
            },
        )
        assert r.status_code == 201
        assert r.json()["question_type"] == "descriptive"

    async def test_duplicate_number_returns_409(self, client: AsyncClient, admin_token: str):
        headers = {"Authorization": f"Bearer {admin_token}"}
        payload = {"number": 504, "text": "Dup", "question_type": "mcq", "options": ["A", "B"]}
        await client.post(f"/api/v1/evaluation/exams/{EXAM_ID}/questions", headers=headers, json=payload)
        r = await client.post(f"/api/v1/evaluation/exams/{EXAM_ID}/questions", headers=headers, json=payload)
        assert r.status_code == 409

    async def test_student_forbidden(self, client: AsyncClient, token: str):
        r = await client.post(
            f"/api/v1/evaluation/exams/{EXAM_ID}/questions",
            headers={"Authorization": f"Bearer {token}"},
            json={"number": 999, "text": "Hack", "question_type": "mcq", "options": ["A"]},
        )
        assert r.status_code == 403

    async def test_list_questions(self, client: AsyncClient, admin_token: str):
        r = await client.get(
            f"/api/v1/evaluation/exams/{EXAM_ID}/questions",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert "count" in body
        assert isinstance(body["data"], list)
        assert body["count"] >= 1

    async def test_delete_question(self, client: AsyncClient, admin_token: str):
        headers = {"Authorization": f"Bearer {admin_token}"}
        cr = await client.post(
            f"/api/v1/evaluation/exams/{EXAM_ID}/questions",
            headers=headers,
            json={"number": 599, "text": "Delete me", "question_type": "integer"},
        )
        assert cr.status_code == 201
        q_id = cr.json()["id"]
        dr = await client.delete(
            f"/api/v1/evaluation/exams/{EXAM_ID}/questions/{q_id}",
            headers=headers,
        )
        assert dr.status_code == 204

    async def test_get_nonexistent_question_returns_404(self, client: AsyncClient, admin_token: str):
        r = await client.get(
            f"/api/v1/evaluation/exams/{EXAM_ID}/questions/nonexistent",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 404


class TestAnswerKeys:
    async def _make_question(self, client, admin_token, number, qtype="integer"):
        payload = {"number": number, "text": f"Q{number}", "question_type": qtype}
        if qtype == "mcq":
            payload["options"] = ["A", "B", "C", "D"]
        r = await client.post(
            f"/api/v1/evaluation/exams/{EXAM_ID}/questions",
            headers={"Authorization": f"Bearer {admin_token}"},
            json=payload,
        )
        return r.json()["id"]

    async def test_set_answer_key(self, client: AsyncClient, admin_token: str):
        q_id = await self._make_question(client, admin_token, 601)
        r = await client.put(
            f"/api/v1/evaluation/questions/{q_id}/answer-key",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"correct_answer": "42"},
        )
        assert r.status_code == 200
        assert r.json()["correct_answer"] == "42"

    async def test_update_answer_key(self, client: AsyncClient, admin_token: str):
        q_id = await self._make_question(client, admin_token, 602, "mcq")
        headers = {"Authorization": f"Bearer {admin_token}"}
        await client.put(f"/api/v1/evaluation/questions/{q_id}/answer-key",
                         headers=headers, json={"correct_answer": "A"})
        r = await client.put(f"/api/v1/evaluation/questions/{q_id}/answer-key",
                              headers=headers, json={"correct_answer": "C"})
        assert r.status_code == 200
        assert r.json()["correct_answer"] == "C"

    async def test_get_answer_key(self, client: AsyncClient, admin_token: str):
        q_id = await self._make_question(client, admin_token, 603)
        headers = {"Authorization": f"Bearer {admin_token}"}
        await client.put(f"/api/v1/evaluation/questions/{q_id}/answer-key",
                         headers=headers, json={"correct_answer": "99"})
        r = await client.get(f"/api/v1/evaluation/questions/{q_id}/answer-key", headers=headers)
        assert r.status_code == 200
        assert r.json()["correct_answer"] == "99"

    async def test_student_cannot_set_answer_key(self, client: AsyncClient,
                                                  admin_token: str, token: str):
        q_id = await self._make_question(client, admin_token, 604)
        r = await client.put(
            f"/api/v1/evaluation/questions/{q_id}/answer-key",
            headers={"Authorization": f"Bearer {token}"},
            json={"correct_answer": "A"},
        )
        assert r.status_code == 403


class TestMarkingPolicy:
    async def test_create_policy(self, client: AsyncClient, admin_token: str):
        r = await client.post(
            f"/api/v1/evaluation/exams/{EXAM_ID}/marking-policy",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "marks_correct": 4.0,
                "marks_wrong": -1.0,
                "marks_unattempted": 0.0,
                "partial_credit_threshold": 0.5,
                "partial_credit_ratio": 0.5,
            },
        )
        assert r.status_code in (201, 409)

    async def test_get_policy(self, client: AsyncClient, admin_token: str):
        r = await client.get(
            f"/api/v1/evaluation/exams/{EXAM_ID}/marking-policy",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert "marks_correct" in body
        assert "marks_wrong" in body

    async def test_update_policy(self, client: AsyncClient, admin_token: str):
        r = await client.put(
            f"/api/v1/evaluation/exams/{EXAM_ID}/marking-policy",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "marks_correct": 3.0,
                "marks_wrong": -0.5,
                "marks_unattempted": 0.0,
                "partial_credit_threshold": 0.5,
                "partial_credit_ratio": 0.5,
            },
        )
        assert r.status_code == 200
        assert r.json()["marks_correct"] == 3.0

    async def test_positive_marks_wrong_returns_422(self, client: AsyncClient, admin_token: str):
        r = await client.put(
            f"/api/v1/evaluation/exams/{EXAM_ID}/marking-policy",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "marks_correct": 4.0,
                "marks_wrong": 1.0,
                "marks_unattempted": 0.0,
                "partial_credit_threshold": 0.5,
                "partial_credit_ratio": 0.5,
            },
        )
        assert r.status_code == 422

    async def test_student_cannot_create_policy(self, client: AsyncClient, token: str):
        r = await client.post(
            f"/api/v1/evaluation/exams/{EXAM_ID}/marking-policy",
            headers={"Authorization": f"Bearer {token}"},
            json={"marks_correct": 1, "marks_wrong": 0, "marks_unattempted": 0,
                  "partial_credit_threshold": 0.5, "partial_credit_ratio": 0.5},
        )
        assert r.status_code == 403
