# Architecture Decision Record — APIBP23N

## 1. Business Problem & Consumers

Modern educational institutions administer hundreds of exam sessions across
multiple physical centres. Manual coordination leads to double-bookings,
students travelling to unavailable centres, and paper-based conflict
resolution. The **Exam Evaluation & Scheduling System** solves this by
providing a programmatic API through which:

- **Student-facing web/mobile apps** let candidates find nearby centres,
  view available time slots, and register — with hard guarantees that no
  two exams overlap in the same calendar window.
- **Institutional portals** (university admin dashboards) manage exam
  lifecycle, publish results, and query aggregated statistics.
- **Third-party integrators** (NEET/JEE counselling platforms) consume the
  public read endpoints to surface exam availability without direct database
  access.

---

## 2. Business Capabilities

1. **Exam discovery** — search the live exam catalogue by subject, price,
   and status with deterministic, page-stable cursor pagination.
2. **Centre proximity lookup** — locate the nearest exam centres to any
   GPS coordinate and filter within a geographic bounding box.
3. **Conflict-safe scheduling** — book an exam slot and receive an
   authoritative 409 (SLOT_CONFLICT) if the time window overlaps any
   existing registration.
4. **Result & grade management** — instructors update scores and computed
   grades after exams complete.
5. **Secure multi-role access** — students, instructors, and admins each
   access exactly the capabilities their role permits.

---

## 3. Resource Model

```
User (student | instructor | admin)
  │
  └── Registration ──── ExamSlot ──── Exam
                │                       │
                │                  ExamCenter
                └─────────────────────┘
                         (location)
```

- **Exam** — the canonical test definition (subject, duration, fee, status).
- **ExamCenter** — a physical venue with GPS coordinates (GeoJSON `[lon, lat]`).
- **ExamSlot** — a scheduled instance of an Exam at a Centre with a bounded
  seat count and an explicit `starts_at` / `ends_at` window.
- **Registration** — a student's confirmed intent to sit a specific slot,
  with an optional post-exam `score` and `grade`.

---

## 4. Approach Decision

**We chose Approach A (REST-First + GraphQL Layer).**

### Rationale

The domain is naturally resource-oriented: exams, centres, slots, and
registrations map cleanly to nouns. HTTP semantics (POST for booking, DELETE
for cancellation, 409 for conflict) express business intent without
translation cost. Starting REST-first let us validate the data model and
error catalogue before layering GraphQL on top.

### Impedance mismatches and resolutions

| Challenge | REST handling | GraphQL handling |
|---|---|---|
| Pagination | Opaque base-64 cursor token in `next_cursor` | Connection spec (`edges`, `pageInfo`, `hasNextPage`, `endCursor`) |
| Errors | HTTP status codes + `{"code": "…", "message": "…"}` body | `errors[].extensions.code` + `RegistrationResult` union type |
| Auth | `Authorization: Bearer <jwt>` header | Same header forwarded via HTTP; `authenticate` mutation for IDE use |
| Rate limiting | `RateLimit-*` headers + 429 body | Same headers on HTTP response; `RATE_LIMITED` in error extensions |

The GraphQL resolvers call the same async SQLAlchemy functions used by the
REST routers, so business logic lives in one place and both surfaces stay
consistent.

---

## 5. Domain Pattern Mapping

| Pattern | Domain entity | Key parameters |
|---|---|---|
| **List** | `Exam` | `status`, `category` (subject), `min_price` / `max_price` (fee), `sort`, `order`, `limit`, `after` |
| **Map** | `ExamCenter` | `/nearby` — `latitude`, `longitude`, `radius_km`; `/bbox` — `min_lat`, `min_lon`, `max_lat`, `max_lon` |
| **Calendar** | `ExamSlot` + `Registration` | `starts_at`, `ends_at` (ISO 8601 UTC); booking raises 409 `SLOT_CONFLICT` on overlap |

All coordinates follow the GeoJSON convention: position `[longitude, latitude]`.

---

## 6. Composite Payload Comparison

Scenario: fetch the detail of **exam-001** together with its slots and the
centre for each slot — a composite view a student app would render.

### REST (3 round-trips)

```
GET /api/v1/exams/exam-001          →  ~380 bytes
GET /api/v1/exam-slots?exam_id=…    →  ~1 100 bytes (2 slots)
GET /api/v1/exam-centers/ctr-001    →  ~310 bytes
GET /api/v1/exam-centers/ctr-002    →  ~310 bytes
                              Total:   ~2 100 bytes, 4 requests
```

### GraphQL (1 round-trip)

```graphql
{
  exam(examId: "exam-001") { id title fee status }
  examSlots(examId: "exam-001") {
    id startsAt endsAt availableSeats
  }
  examCenters { id name city coordinates { longitude latitude } }
}
```

Response: ~780 bytes, **1 request**.

GraphQL wins on bytes and round-trips for composite views; REST wins on
caching granularity because each resource can be individually cached by
CDN or browser.

---

## 7. Error Catalogue

| Code | HTTP | GraphQL `extensions.code` | Cause |
|---|---|---|---|
| `INVALID_CREDENTIALS` | 401 | INVALID_CREDENTIALS | Wrong username or password |
| `TOKEN_EXPIRED` | 401 | TOKEN_EXPIRED | JWT past its expiry |
| `TOKEN_INVALID` | 401 | TOKEN_INVALID | Malformed, missing, or unknown JWT |
| `FORBIDDEN` | 403 | FORBIDDEN | Valid token but insufficient role |
| `EXAM_NOT_FOUND` | 404 | EXAM_NOT_FOUND | No exam with the given ID |
| `CENTER_NOT_FOUND` | 404 | CENTER_NOT_FOUND | No centre with the given ID |
| `SLOT_NOT_FOUND` | 404 | SLOT_NOT_FOUND | No slot with the given ID |
| `REGISTRATION_NOT_FOUND` | 404 | REGISTRATION_NOT_FOUND | No active registration found |
| `SLOT_FULL` | 409 | SLOT_FULL | Zero `available_seats` in the slot |
| `SLOT_CONFLICT` | 409 | SLOT_CONFLICT | Booking overlaps an existing registration |
| `ALREADY_REGISTERED` | 409 | ALREADY_REGISTERED | Student already holds an active booking for this exact slot |
| `EXAM_CANCELLED` | 422 | EXAM_CANCELLED | Attempt to register for a slot whose parent exam is cancelled |
| `INVALID_DATE_RANGE` | 422 | INVALID_DATE_RANGE | `starts_at` ≥ `ends_at` in a time-window query |
| `INVALID_COORDINATES` | 422 | INVALID_COORDINATES | Degenerate bounding box (min ≥ max) |
| `MISSING_FIELDS` | 422 | MISSING_FIELDS | Required fields absent in a creation request |
| `RATE_LIMITED` | 429 | RATE_LIMITED | Client exceeded 100 requests/minute |

---

## 8. Design Decisions

### 8.1 SQLite + aiosqlite

SQLite was chosen for zero-infrastructure docker compose (`docker compose up`
→ working service, no separate DB container). For production the
`DATABASE_URL` environment variable can be swapped for PostgreSQL without
code changes (SQLAlchemy dialect swap).

### 8.2 Cursor-based pagination over offset

Offset pagination drifts when records are inserted between pages, causing
duplicate or skipped items. A base-64 cursor encoding `(created_at, id)` is
stable regardless of concurrent writes. The same opaque token format is
reused across REST (`next_cursor` / `after`) and GraphQL (`endCursor` / `after`).

### 8.3 DataLoader for N+1 prevention

Strawberry resolvers use the `DataLoader` pattern: when a list of exams is
fetched and each requests its `slots`, the `slots_for_exam` loader batches
all slot IDs into a single `WHERE exam_id IN (…)` query rather than one
query per exam. This prevents O(N) database round-trips on deep GraphQL
queries.

---

## 9. Future Evolution

1. **API v2 with `subject` removal** — the `subject` field on `Exam` is
   already marked `@deprecated` in the GraphQL schema; v2 can drop it cleanly.
   REST would introduce `/api/v2/exams` with the renamed field as a
   non-breaking versioned path.
2. **Real-time seat availability via WebSocket** — a `subscriptions` root
   in GraphQL (or Server-Sent Events on REST) could push seat-count updates
   to booking UIs without polling.
3. **Multi-tenant isolation** — the current model has a single shared
   namespace. Adding an `institution_id` foreign key and row-level security
   in PostgreSQL would serve multiple universities from one deployment.

---

## 10. Business Value

1. **Reduced operational overhead** — automated conflict detection eliminates
   the manual cross-checking that previously required exam-office staff to
   verify calendars by hand.
2. **Better candidate experience** — geospatial search lets students find
   the nearest available centre and book in seconds; structured error codes
   give client apps meaningful feedback rather than generic failures.
3. **Dual-interface flexibility** — REST suits third-party integrations and
   CDN caching; GraphQL suits the internal student portal which fetches
   composite data in a single round-trip, reducing perceived latency on
   mobile networks.
