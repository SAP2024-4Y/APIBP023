# APIBP023 — Exam Evaluation & Scheduling System

Course: S1-26_SESAPZG504 — API Design & Best Practices | Section: CS-401 | Instructor: Vinaya Sathyanarayana

## Team Details

| # | Name        | Roll No      | GitHub ID  | Email                                    |
|---|-------------|--------------|------------|------------------------------------------|
| 1 | Baibhab Dey | 2024sl70019  | Baibhab23  | 2024sl70019@wilp.bits-pilani.ac.in       |


- Team ID: `APIBP023`
- Chosen Approach: `A` — REST-First + GraphQL Layer

---

## Quick start

```bash
git clone https://github.com/<course-org>/APIBP023
cd APIBP023
docker compose up
# Server ready at http://localhost:8080 within ~30 s
# REST docs:  http://localhost:8080/docs
# GraphQL:    http://localhost:8080/graphql
```

### Demo credentials

| Account    | Username | Password        |
|------------|----------|-----------------|
| Student    | `demo`   | `demo-password` |
| Admin      | `admin`  | `admin-password`|

---

## Testing with Bruno

[Bruno](https://www.usebruno.com/) is an open-source API client (no cloud sync required).
Import the collection below by creating a `bruno/` folder in the repo root and saving each
`.bru` file, or paste the requests manually into a new Bruno collection pointed at
`http://localhost:8080`.

Set a Bruno environment variable `base_url = http://localhost:8080` and `token = <paste after auth>`.

---

### Auth

#### POST — Get token

```
POST {{base_url}}/api/v1/auth/token
Content-Type: application/json

{
  "username": "demo",
  "password": "demo-password"
}
```

> Copy the returned `token` value into your Bruno environment as `token`.

---

### Exams (List API)

#### GET — List exams (filtered + paginated)

```
GET {{base_url}}/api/v1/exams?category=Mathematics&min_price=0&max_price=500&sort=fee&order=asc&limit=5
```

Returns a cursor-paginated response. Use the `end_cursor` value from `pageInfo` as the `after`
query param to fetch the next page.

#### GET — Next page

```
GET {{base_url}}/api/v1/exams?after=<end_cursor>&limit=5
```

---

### Exam Centers (Map API)

#### GET — Nearby centers (proximity search)

```
GET {{base_url}}/api/v1/exam-centers/nearby?latitude=28.6139&longitude=77.2090&radius_km=50
```

#### GET — Centers in bounding box

```
GET {{base_url}}/api/v1/exam-centers/bbox?min_lat=28.4&min_lon=77.0&max_lat=28.8&max_lon=77.5
```

---

### Exam Slots (Calendar API)

#### GET — List slots in a time window

```
GET {{base_url}}/api/v1/exam-slots?starts_at=2027-01-01T00:00:00Z&ends_at=2027-06-30T23:59:59Z
```

#### GET — Single slot

```
GET {{base_url}}/api/v1/exam-slots/<slot_id>
```

#### POST — Register for a slot

```
POST {{base_url}}/api/v1/exam-slots/<slot_id>/register
Authorization: Bearer {{token}}
```

Returns `409 SLOT_CONFLICT` if the student already has a registration that overlaps the slot's
time window.

#### DELETE — Cancel registration

```
DELETE {{base_url}}/api/v1/exam-slots/<slot_id>/register
Authorization: Bearer {{token}}
```

---

### Evaluation — Questions & Answer Keys (Admin/Instructor)

#### POST — Add a question to an exam

```
POST {{base_url}}/api/v1/evaluation/exams/<exam_id>/questions
Authorization: Bearer {{token}}
Content-Type: application/json

{
  "number": 1,
  "text": "What is the value of π to two decimal places?",
  "question_type": "mcq",
  "options": ["3.12", "3.14", "3.16", "3.18"]
}
```

`question_type` must be one of `mcq`, `integer`, or `descriptive`.  
`options` is required for `mcq`.

#### GET — List questions for an exam

```
GET {{base_url}}/api/v1/evaluation/exams/<exam_id>/questions
Authorization: Bearer {{token}}
```

#### GET — Single question

```
GET {{base_url}}/api/v1/evaluation/exams/<exam_id>/questions/<question_id>
Authorization: Bearer {{token}}
```

#### DELETE — Remove a question

```
DELETE {{base_url}}/api/v1/evaluation/exams/<exam_id>/questions/<question_id>
Authorization: Bearer {{token}}
```

#### PUT — Set / update the answer key for a question

```
PUT {{base_url}}/api/v1/evaluation/questions/<question_id>/answer-key
Authorization: Bearer {{token}}
Content-Type: application/json

{
  "correct_answer": "B",
  "explanation": "π ≈ 3.14"
}
```

For `descriptive` questions, `correct_answer` must be a JSON array of keywords:
`["photosynthesis", "chlorophyll", "sunlight"]`

#### GET — Retrieve answer key

```
GET {{base_url}}/api/v1/evaluation/questions/<question_id>/answer-key
Authorization: Bearer {{token}}
```

---

### Evaluation — Marking Policy (Admin/Instructor)

#### POST — Create marking policy

```
POST {{base_url}}/api/v1/evaluation/exams/<exam_id>/marking-policy
Authorization: Bearer {{token}}
Content-Type: application/json

{
  "marks_correct": 4.0,
  "marks_wrong": -1.0,
  "marks_unattempted": 0.0,
  "partial_credit_threshold": 0.5,
  "partial_credit_ratio": 0.5
}
```

`marks_wrong` must be ≤ 0. `partial_credit_threshold` and `partial_credit_ratio` are in [0, 1]
and apply only to `descriptive` questions.

#### GET — Retrieve policy

```
GET {{base_url}}/api/v1/evaluation/exams/<exam_id>/marking-policy
Authorization: Bearer {{token}}
```

#### PUT — Update policy

```
PUT {{base_url}}/api/v1/evaluation/exams/<exam_id>/marking-policy
Authorization: Bearer {{token}}
Content-Type: application/json

{
  "marks_correct": 3.0,
  "marks_wrong": -0.5,
  "marks_unattempted": 0.0,
  "partial_credit_threshold": 0.6,
  "partial_credit_ratio": 0.4
}
```

---

### Submissions — Answer Scripts (Student)

#### POST — Submit / replace an answer script

```
POST {{base_url}}/api/v1/submissions/<registration_id>
Authorization: Bearer {{token}}
Content-Type: application/json

{
  "answers": [
    { "question_id": "<q1_id>", "answer": "B" },
    { "question_id": "<q2_id>", "answer": "42" },
    { "question_id": "<q3_id>", "answer": null }
  ]
}
```

`answer: null` means the student left the question unattempted.  
Re-submitting before evaluation atomically replaces the previous script.  
Returns `409 ALREADY_EVALUATED` if the script was already scored.

#### GET — Submission status

```
GET {{base_url}}/api/v1/submissions/<registration_id>
Authorization: Bearer {{token}}
```

Returns `evaluated`, `evaluated_at`, and `answer_count`.

#### GET — Per-question answers

```
GET {{base_url}}/api/v1/submissions/<registration_id>/answers
Authorization: Bearer {{token}}
```

---

### Evaluation — Score a Script (Admin/Instructor)

#### POST — Evaluate an answer script

```
POST {{base_url}}/api/v1/evaluation/scripts/<script_id>/evaluate
Authorization: Bearer {{token}}
```

Runs the scoring engine against the stored answers and answer keys, persists
`score`, `grade`, and `status = completed` on the registration, and marks the
script as `evaluated`. Returns the full per-question breakdown.

Returns `409 ALREADY_EVALUATED` if called a second time.

---

### Results

#### GET — Student: own results

```
GET {{base_url}}/api/v1/results/me
Authorization: Bearer {{token}}
```

Lists all registrations with `status = completed` for the current student,
including `score` and `grade`.

#### GET — Detailed result for one registration

```
GET {{base_url}}/api/v1/results/registrations/<registration_id>
Authorization: Bearer {{token}}
```

Returns the per-question breakdown: student's answer, correct answer, and question text.
The registration owner or any admin/instructor can call this endpoint.  
Returns `404 NOT_EVALUATED` if the script hasn't been scored yet.

#### GET — Exam leaderboard (Admin/Instructor only)

```
GET {{base_url}}/api/v1/results/exams/<exam_id>
Authorization: Bearer {{token}}
```

Returns all completed registrations for the exam, ranked by score descending.
Students receive `403 FORBIDDEN`.

---

### GraphQL

Open <http://localhost:8080/graphql> for the in-browser schema explorer.

#### List exams

```graphql
query ListExams {
  exams(first: 5, category: "Mathematics") {
    edges {
      node { id title fee status }
      cursor
    }
    pageInfo { hasNextPage endCursor }
    totalCount
  }
}
```

#### My registrations (authenticated)

```graphql
query MyRegistrations {
  myRegistrations {
    id
    slot { startsAt endsAt }
    status
    score
    grade
  }
}
```

Pass `Authorization: Bearer <token>` in the request headers tab in Bruno.

---

## Running tests locally

```bash
# Inside Docker
docker compose exec api pytest tests/ -v

# Locally (Python 3.12+)
pip install -r requirements.txt
pytest tests/ -v
```

---

## Architecture

See [docs/ADR.md](docs/ADR.md) for the Architecture Decision Record.

- **Approach A**: REST-first, GraphQL layer on top
- **Domain**: Exam scheduling, answer submission, automated evaluation, result reporting
- **List API**: `GET /api/v1/exams` — status/category/price filters + cursor pagination
- **Map API**: `GET /api/v1/exam-centers/nearby` and `/bbox` — geospatial search
- **Calendar API**: `GET /api/v1/exam-slots` — time-window + 409 conflict prevention
- **Evaluation API**: questions, answer keys, marking policies, scoring engine
- **Submissions API**: atomic answer-script upload with post-evaluation lock
- **Results API**: per-student results and instructor leaderboard
