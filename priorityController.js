/**
 * Priority Inbox Controller
 * Stage 6: Return top N notifications ranked by priority score.
 *
 * Priority Score = TYPE_WEIGHT + RECENCY_SCORE
 *
 *   TYPE_WEIGHT:
 *     Placement → 30  (highest operational impact)
 *     Result    → 20
 *     Event     → 10
 *
 *   RECENCY_SCORE (0 to 10):
 *     Normalised based on timestamp relative to oldest/newest in current batch.
 *     score = ((ts - min_ts) / (max_ts - min_ts)) * 10
 *     Newer = higher score.
 *
 * TOTAL = TYPE_WEIGHT + RECENCY_SCORE  (max = 40, min = 10)
 *
 * Maintaining top-N efficiently as new notifications arrive:
 *   → Use a min-heap of size N.
 *   → On new notification: compute score, push to heap.
 *   → If heap size > N, pop the minimum.
 *   → Heap always holds the top N highest-scored notifications.
 *   → O(log N) per insert — efficient for high-throughput streams.
 */

const { fetchFromAPI } = require("./notificationController");
const logger = require("../middleware/logger");

const TYPE_WEIGHTS = {
  Placement: 30,
  Result: 20,
  Event: 10,
};

/**
 * Compute priority score for a notification.
 * @param {Object} notification
 * @param {number} minTs  - oldest timestamp in batch (ms)
 * @param {number} maxTs  - newest timestamp in batch (ms)
 */
function computeScore(notification, minTs, maxTs) {
  const typeWeight = TYPE_WEIGHTS[notification.Type] ?? 5;

  const ts = new Date(notification.Timestamp).getTime();
  let recency = 0;
  if (maxTs !== minTs) {
    recency = ((ts - minTs) / (maxTs - minTs)) * 10;
  }

  return typeWeight + recency;
}

/**
 * GET /api/priority-inbox?n=10
 * Returns top N notifications by priority score.
 */
async function getPriorityInbox(req, res) {
  const n = Math.max(1, parseInt(req.query.n, 10) || 10);
  logger.info(`Priority inbox requested: top ${n} notifications`);

  try {
    const notifications = await fetchFromAPI();

    if (!notifications.length) {
      return res.status(200).json({ priorityInbox: [] });
    }

    // Compute timestamp bounds for recency normalisation
    const timestamps = notifications.map((n) =>
      new Date(n.Timestamp).getTime()
    );
    const minTs = Math.min(...timestamps);
    const maxTs = Math.max(...timestamps);

    // Score each notification
    const scored = notifications.map((notif) => ({
      ...notif,
      _score: computeScore(notif, minTs, maxTs),
    }));

    // Sort descending by score, take top N
    // For production with streaming: replace with a min-heap (see docstring above)
    scored.sort((a, b) => b._score - a._score);
    const topN = scored.slice(0, n);

    logger.info(
      `Returning top ${topN.length} notifications from ${notifications.length} total`
    );

    res.status(200).json({
      requested: n,
      returned: topN.length,
      priorityInbox: topN.map(({ _score, ...notif }) => ({
        ...notif,
        priorityScore: Math.round(_score * 100) / 100,
      })),
    });
  } catch (err) {
    logger.error(`Priority inbox error: ${err.message}`);
    res.status(500).json({ error: "Failed to compute priority inbox" });
  }
}

module.exports = { getPriorityInbox };
