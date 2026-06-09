# Notification System Design

---

## Stage 1

### Overview

Design a REST API for a campus notification platform that delivers real-time updates to students about Placements, Results, and Events.

---

### Core Actions

| Action | Method | Endpoint | Auth |
|--------|--------|----------|------|
| Get all notifications | GET | `/api/notifications` | Required |
| Mark notification read | PATCH | `/api/notifications/:id/read` | Required |
| Get unread count | GET | `/api/notifications/unread-count` | Required |
| Get priority inbox | GET | `/api/priority-inbox?n=10` | Required |
| Real-time stream | GET | `/api/stream` | Required |

---

### JSON Schemas

#### GET `/api/notifications` — Response
```json
{
  "notifications": [
    {
      "ID": "d146095a-0d86-4a34-9e69-3900a14576bc",
      "Type": "Result",
      "Message": "mid-sem",
      "Timestamp": "2026-04-22 17:51:30",
      "IsRead": false
    }
  ]
}
```

#### PATCH `/api/notifications/:id/read` — Response
```json
{
  "success": true,
  "message": "Notification marked as read"
}
```

#### GET `/api/priority-inbox?n=10` — Response
```json
{
  "requested": 10,
  "returned": 10,
  "priorityInbox": [
    {
      "ID": "b283218f-ea5a-4b7c-93a9-1f2f240d64b0",
      "Type": "Placement",
      "Message": "CSX Corporation hiring",
      "Timestamp": "2026-04-22 17:51:18",
      "priorityScore": 39.85
    }
  ]
}
```

---

### Request/Response Headers

```
Authorization: Bearer <token>
Content-Type: application/json
Accept: application/json
```

---

### Real-Time Notification Mechanism: Server-Sent Events (SSE)

**Choice: SSE over WebSockets**

Notifications are unidirectional (server → client). SSE is simpler, uses plain HTTP/1.1, supports auto-reconnect natively in browsers, and requires no special server upgrade. WebSockets would add unnecessary bidirectional complexity.

**Flow:**
1. Client opens `GET /api/stream` (long-lived HTTP connection)
2. Server sets `Content-Type: text/event-stream`
3. Server polls Affordmed API every 5 seconds
4. New notifications are pushed as SSE events:
   ```
   event: notification
   data: {"ID":"...","Type":"Placement","Message":"...","Timestamp":"..."}
   ```
5. Client receives events in real-time; reconnects automatically on disconnect

---

## Stage 2

### Persistent Storage: Why PostgreSQL?

**Recommended DB: PostgreSQL (Relational)**

Reasons:
- Notifications have a fixed, predictable schema (ID, Type, Message, Timestamp, IsRead, StudentID)
- Relational integrity: student and notification data are naturally linked via foreign keys
- Strong ACID guarantees prevent double-delivery or lost read-status updates
- Rich indexing support for the heavy query pattern: fetch unread notifications for a student ordered by time
- `notification_type` enum is natively supported in PostgreSQL

---

### DB Schema

```sql
-- Students table (referenced by notifications)
CREATE TABLE students (
  id         BIGSERIAL PRIMARY KEY,
  name       VARCHAR(255) NOT NULL,
  email      VARCHAR(255) UNIQUE NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Notification type enum
CREATE TYPE notification_type AS ENUM ('Event', 'Result', 'Placement');

-- Notifications table
CREATE TABLE notifications (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  student_id        BIGINT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
  notification_type notification_type NOT NULL,
  message           TEXT NOT NULL,
  is_read           BOOLEAN NOT NULL DEFAULT FALSE,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for the most common query: unread notifications for a student, newest first
CREATE INDEX idx_notifications_student_unread
  ON notifications(student_id, is_read, created_at DESC);
```

---

### SQL Queries (from Stage 1 API design)

**Fetch all unread notifications for a student (newest first):**
```sql
SELECT id, notification_type, message, is_read, created_at
FROM notifications
WHERE student_id = $1
  AND is_read = false
ORDER BY created_at DESC;
```

**Mark a notification as read:**
```sql
UPDATE notifications
SET is_read = true
WHERE id = $1
  AND student_id = $2;
```

**Unread count for a student:**
```sql
SELECT COUNT(*) AS unread_count
FROM notifications
WHERE student_id = $1
  AND is_read = false;
```

---

### Problems as Data Volume Grows (50,000 students, 5M+ notifications)

| Problem | Cause | Solution |
|---------|-------|----------|
| Slow reads | Full table scan without index | Composite index on `(student_id, is_read, created_at DESC)` |
| Huge table size | All notifications stored forever | Partition by month; archive old rows |
| Write bottleneck | 50K inserts simultaneously (Notify All) | Message queue (Kafka/RabbitMQ) + async workers |
| Index bloat | Index on `is_read` (low cardinarity) | Partial index: `WHERE is_read = false` |

---

## Stage 3

### Original Query Analysis

```sql
SELECT * FROM notifications
WHERE studentID = 1042 AND isRead = false
ORDER BY createdAt DESC;
```

**Is this query accurate?** Functionally yes, but has problems:

**Why is it slow?**
- `SELECT *` fetches all columns including potentially large `message` field — unnecessary data transfer
- Without an index on `(studentID, isRead, createdAt)`, PostgreSQL does a full sequential scan → O(n) per query
- At 5M rows this is extremely slow

**What to change:**
```sql
-- Select only needed columns
SELECT id, notification_type, message, created_at
FROM notifications
WHERE student_id = 1042
  AND is_read = false
ORDER BY created_at DESC;
```

**Add this index:**
```sql
CREATE INDEX idx_notifications_student_unread
  ON notifications(student_id, is_read, created_at DESC);
```

**Likely computation cost without index:** O(n) full scan  
**With composite index:** O(log n + k) where k = result rows — dramatically faster

---

### Advice: "Index every column to be safe"

**This is BAD advice. Do NOT do this.**

- Every index costs storage space (duplicate data on disk)
- Every index slows down `INSERT`, `UPDATE`, `DELETE` (index must be updated too)
- Low-cardinality columns like `is_read` (only true/false) provide very poor index selectivity
- PostgreSQL's query planner may even ignore such indexes if selectivity is too low
- Correct approach: index columns used in `WHERE`, `JOIN`, and `ORDER BY` clauses of actual queries

---

### Query: Students Who Got Placement Notification in Last 7 Days

```sql
SELECT DISTINCT s.id, s.name, s.email
FROM students s
JOIN notifications n ON s.id = n.student_id
WHERE n.notification_type = 'Placement'
  AND n.created_at >= NOW() - INTERVAL '7 days';
```

---

## Stage 4

### Problem: DB Getting Overwhelmed (Fetching Notifications on Every Page Load)

**Root Cause:** Synchronous DB query per page load per student = O(students_online) concurrent queries. At 50K students this kills the database.

---

### Solutions and Tradeoffs

#### Strategy 1: In-Memory Caching (Redis)

**Approach:** Cache the notification list per student in Redis with a TTL (e.g. 60 seconds).

```
Request → Check Redis → Hit: return cached → Miss: query DB, store in Redis
```

**Tradeoffs:**
| Pros | Cons |
|------|------|
| 10-100x faster reads (sub-millisecond) | Stale data up to TTL duration |
| Massive DB load reduction | Extra infrastructure (Redis) |
| Simple to implement | Cache invalidation complexity on new notification |

**Best for:** Read-heavy, tolerates slight staleness

---

#### Strategy 2: Invalidation-Based Caching

**Approach:** Cache notifications. Invalidate (delete) the cache entry for a student whenever they receive a new notification or mark one as read.

**Tradeoffs:**
| Pros | Cons |
|------|------|
| Always fresh data | Invalidation logic in multiple places (write paths) |
| No unnecessary DB hits | Initial load after invalidation hits DB |

---

#### Strategy 3: Pagination + Cursor-Based Loading

**Approach:** Instead of loading all notifications at once, load page-by-page (e.g. 20 at a time).

```sql
SELECT * FROM notifications
WHERE student_id = $1 AND is_read = false AND created_at < $cursor
ORDER BY created_at DESC
LIMIT 20;
```

**Tradeoffs:**
| Pros | Cons |
|------|------|
| Reduces data per query | UX requires scroll/load-more |
| Works without caching layer | Still one DB query per page |

---

#### Strategy 4: Read Replicas

**Approach:** Route all read queries to read replicas; writes go to primary.

**Tradeoffs:**
| Pros | Cons |
|------|------|
| Scales read throughput horizontally | Replication lag (ms-level staleness) |
| No code changes for queries | Cost of additional DB instances |

---

### Recommended Combination
**Redis cache (TTL 30-60s) + invalidation on write + pagination**  
This covers the common case (reading) cheaply, ensures freshness on writes, and limits payload size.

---

## Stage 5

### Shortcomings of the Original `notify_all` Implementation

```
function notify_all(student_ids: array, message: string):
    for student_id in student_ids:
        send_email(student_id, message)   # calls Email API
        save_to_db(student_id, message)   # DB insert
        push_to_app(student_id, message)  # real-time push
```

**Problems:**

1. **Sequential processing** — iterates one student at a time. For 50K students this is extremely slow (bottleneck at every step)
2. **No error handling / retry** — if `send_email` fails for student 5000, the loop stops or skips silently
3. **Tight coupling** — email, DB, and push all happen in the same synchronous call. If any step fails, partial state remains
4. **No atomicity** — `send_email` succeeded but `save_to_db` fails → email sent but no record exists
5. **Blocking** — the HR's request blocks until all 50K are processed (likely timeout)

---

### What happened: `send_email` failed for 200 students midway?

With the original code:
- Those 200 students got no email
- But `save_to_db` may have already run for them (partial state)
- No way to know which 200 failed without logs
- The loop likely continued or crashed — unpredictable

---

### Redesigned Implementation

**Architecture: Message Queue + Async Workers**

```
HR clicks "Notify All"
        ↓
API enqueues 50,000 jobs into message queue (Kafka / RabbitMQ)
        ↓
Workers consume jobs in parallel (configurable concurrency)
        ↓
Each job:
  1. save_to_db(student_id, message)   ← First (source of truth)
  2. send_email(student_id, message)   ← Retry on failure (up to 3x)
  3. push_to_app(student_id, message)  ← Best-effort
        ↓
Failed jobs → Dead Letter Queue → retry or alert
```

---

### Should DB save and email send happen together?

**No. They should be decoupled.**

- DB save is the **source of truth** — it must happen first and always succeed
- Email is a **side effect** — it can fail and be retried independently
- Coupling them means a failed email could roll back a successful DB insert → student has no notification at all
- Correct pattern: save to DB first, then trigger email asynchronously

---

### Revised Pseudocode

```
function notify_all(student_ids: array, message: string):
    for student_id in student_ids:
        enqueue_job(queue="notifications", payload={student_id, message})
    return {"status": "queued", "count": len(student_ids)}

# Worker (runs in parallel, N workers):
function process_notification_job(job):
    student_id = job.student_id
    message    = job.message

    # Step 1: Save to DB (with transaction)
    try:
        save_to_db(student_id, message)
    except DBError as e:
        log_error(e)
        requeue(job, delay=backoff)  # retry
        return

    # Step 2: Send email (retry up to 3 times)
    retries = 0
    while retries < 3:
        try:
            send_email(student_id, message)
            break
        except EmailError as e:
            retries += 1
            log_warn(f"Email failed attempt {retries}: {e}")
            if retries == 3:
                send_to_dead_letter_queue(job)

    # Step 3: Push to app (best-effort, don't block)
    try:
        push_to_app(student_id, message)
    except PushError as e:
        log_warn(f"Push failed (non-critical): {e}")
```

---

## Stage 6

### Priority Inbox: Top N Most Important Unread Notifications

**Requirement:** Show top N notifications (N configurable: 10, 15, 20...) ranked by importance.

---

### Priority Scoring Formula

```
Priority Score = TYPE_WEIGHT + RECENCY_SCORE

TYPE_WEIGHT:
  Placement  → 30   (highest: directly impacts student's career)
  Result     → 20   (academic outcomes)
  Event      → 10   (general campus events)

RECENCY_SCORE (0 to 10):
  Normalised timestamp relative to oldest/newest in batch:
  recency = ((ts - min_ts) / (max_ts - min_ts)) * 10

Total Range: 10 (oldest Event) to 40 (newest Placement)
```

**Why this formula?**
- Placement always outranks Result, which outranks Event (type dominates)
- Within the same type, newer notifications rank higher (recency as tiebreaker)
- Weights chosen to ensure type ordering is never overridden by recency alone

---

### API Endpoint

```
GET /api/priority-inbox?n=10
Authorization: Bearer <token>

Response:
{
  "requested": 10,
  "returned": 10,
  "priorityInbox": [
    {
      "ID": "b283218f-...",
      "Type": "Placement",
      "Message": "CSX Corporation hiring",
      "Timestamp": "2026-04-22 17:51:18",
      "priorityScore": 39.85
    },
    ...
  ]
}
```

---

### Maintaining Top N Efficiently as New Notifications Arrive

**Problem:** New notifications keep coming in. How to maintain top-10 without re-sorting all notifications every time?

**Solution: Min-Heap of size N**

```
Algorithm:
  Initialize: min-heap H of size N (ordered by priority score, min at top)

  For each new notification arriving:
    1. Compute its priority score
    2. If heap size < N:
         push to heap
    3. Else if score > heap.min():
         pop minimum from heap
         push new notification
    4. Else:
         discard (it wouldn't be in top N)

  Result: H always contains the top N highest-scored notifications
  Time per notification: O(log N)  — very efficient
  Space: O(N)
```

**Why not re-sort every time?**
- Re-sorting all notifications = O(M log M) where M grows unboundedly
- Min-heap = O(log N) per new notification, N stays fixed
- At 50K students × many notifications, heap approach is orders of magnitude faster

---

### Implementation (Node.js — Priority Inbox Controller)

See `controllers/priorityController.js` for the working implementation.

The current implementation uses `Array.sort()` on the batch from the API (suitable for this evaluation since we're not storing in DB). For production with a live stream, replace with the min-heap algorithm described above.

---

### Summary of Approach

| Concern | Solution |
|---------|----------|
| Ranking | TYPE_WEIGHT + RECENCY_SCORE formula |
| Top-N selection | Min-heap O(log N) per notification |
| New notifications arriving | Heap automatically evicts lowest-scored item |
| API | `GET /api/priority-inbox?n=<number>` |
| N is configurable | Query param `n` (default 10) |
