# APIBP023 — Exam Evaluation & Scheduling System

Course: API Design & Best Practices | Section: CS-401 | Instructor: TBD

## Team Details

| # | Name         | Roll No   | GitHub ID  | Email                |
|---|--------------|-----------|------------|----------------------|
| 1 | Baibhab Dey  | 22CS3001  | Baibhab23  | baibhabd17@gmail.com |

- Team ID: `APIBP023` (must equal the repository name and `team.json.team_id`)
- Chosen Approach: `A` — REST-First + GraphQL Layer

---

## Quick start

```bash
git clone https://github.com/<course-org>/APIBP023
cd APIBP023
docker compose up
# Server ready at http://localhost:8080 within 120 seconds
# REST docs:    http://localhost:8080/docs
# GraphQL IDE:  http://localhost:8080/graphql
```

### Demo credentials

| Account | Username | Password        |
|---------|----------|-----------------|
| Student | `demo`   | `demo-password` |
| Admin   | `admin`  | `admin-password`|

```bash
# Issue a token
curl -s -X POST http://localhost:8080/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{"username":"demo","password":"demo-password"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])"
```

---

## REST API examples

```bash
BASE=http://localhost:8080/api/v1
TOKEN=<paste token here>

# List API — filter by subject/price, paginate with cursor
curl "$BASE/exams?category=Mathematics&min_price=0&max_price=500&sort=fee&order=asc&limit=5"

# Map API — proximity search (lat, lon, radius km)
curl "$BASE/exam-centers/nearby?latitude=28.6139&longitude=77.2090&radius_km=50"

# Map API — bounding-box search
curl "$BASE/exam-centers/bbox?min_lat=28.4&min_lon=77.0&max_lat=28.8&max_lon=77.5"

# Calendar API — list slots in a time window
curl "$BASE/exam-slots?starts_at=2027-01-01T00:00:00Z&ends_at=2027-06-30T23:59:59Z"

# Calendar API — book a slot (auth required)
curl -X POST "$BASE/exam-slots/<SLOT_ID>/register" \
  -H "Authorization: Bearer $TOKEN"
```

## GraphQL IDE

Open <http://localhost:8080/graphql> — GraphiQL loads with schema introspected.

```graphql
query ListExams {
  exams(first: 5, category: "Mathematics") {
    edges { node { id title fee status } cursor }
    pageInfo { hasNextPage endCursor }
    totalCount
  }
}
```

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
- **Domain**: Exam scheduling — students, exam centres, exam slots, registrations
- **List API**: `GET /api/v1/exams` — status/category/price filters + cursor pagination
- **Map API**: `GET /api/v1/exam-centers/nearby` and `/bbox` — geospatial search
- **Calendar API**: `GET /api/v1/exam-slots` — time-window + 409 conflict prevention
