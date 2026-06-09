

const { fetchFromAPI } = require("./notificationController");
const logger = require("../middleware/logger");

const TYPE_WEIGHTS = {
  Placement: 30,
  Result: 20,
  Event: 10,
};


function computeScore(notification, minTs, maxTs) {
  const typeWeight = TYPE_WEIGHTS[notification.Type] ?? 5;

  const ts = new Date(notification.Timestamp).getTime();
  let recency = 0;
  if (maxTs !== minTs) {
    recency = ((ts - minTs) / (maxTs - minTs)) * 10;
  }

  return typeWeight + recency;
}


async function getPriorityInbox(req, res) {
  const n = Math.max(1, parseInt(req.query.n, 10) || 10);
  logger.info(`Priority inbox requested: top ${n} notifications`);

  try {
    const notifications = await fetchFromAPI();

    if (!notifications.length) {
      return res.status(200).json({ priorityInbox: [] });
    }

    
    const timestamps = notifications.map((n) =>
      new Date(n.Timestamp).getTime()
    );
    const minTs = Math.min(...timestamps);
    const maxTs = Math.max(...timestamps);

    
    const scored = notifications.map((notif) => ({
      ...notif,
      _score: computeScore(notif, minTs, maxTs),
    }));

    
    
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

