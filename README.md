# Affordmed Campus Hiring Evaluation — Backend

## Repository Structure

```
├── vehicle_scheduling/
│   ├── scheduler.py          ← Vehicle Maintenance Scheduler (Knapsack DP)
│   └── requirements.txt
│
├── notification_service/
│   ├── app.js                ← Express app entry point
│   ├── package.json
│   ├── middleware/
│   │   ├── auth.js           ← Pre-auth middleware (evaluation mode)
│   │   └── logger.js         ← Logging middleware (Winston)
│   ├── routes/
│   │   ├── notifications.js  ← GET /api/notifications
│   │   ├── priority.js       ← GET /api/priority-inbox?n=10
│   │   └── sse.js            ← GET /api/stream (Server-Sent Events)
│   └── controllers/
│       ├── notificationController.js
│       ├── priorityController.js
│       └── sseController.js
│
└── notification_system_design.md  ← All 6 stages design doc
```

---

## Vehicle Maintenance Scheduler

### Problem
Knapsack: maximise total operational impact of vehicle maintenance tasks
within each depot's mechanic-hour budget.

### How to Run
```bash
cd vehicle_scheduling
pip install -r requirements.txt
python scheduler.py
```

Results printed to console and saved to `schedule_output.json`.

---

## Campus Notifications Microservice

### How to Run
```bash
cd notification_service
npm install
npm start
```

Service runs on `http://localhost:3000`

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/notifications` | All notifications |
| GET | `/api/priority-inbox?n=10` | Top N by priority score |
| GET | `/api/stream` | SSE real-time stream |
| GET | `/health` | Health check |

---

## Logging
- All code uses the Logging Middleware from Pre-Test Setup
- `middleware/logger.js` → replace with your actual middleware import

---

## Stages Covered in `notification_system_design.md`

| Stage | Topic |
|-------|-------|
| Stage 1 | REST API design, endpoints, schemas, SSE real-time mechanism |
| Stage 2 | PostgreSQL schema, SQL queries, scaling problems & solutions |
| Stage 3 | Query analysis, indexing strategy, placement query |
| Stage 4 | Caching strategies (Redis), tradeoffs, recommendations |
| Stage 5 | notify_all redesign, message queues, retry logic, pseudocode |
| Stage 6 | Priority inbox scoring formula, min-heap algorithm, API |
