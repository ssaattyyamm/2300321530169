

const express = require("express");
const app = express();



const logger = require("./middleware/logger");

app.use(express.json());
app.use(logger.httpLogger); 


const notificationRoutes = require("./routes/notifications");
const priorityRoutes = require("./routes/priority");
const sseRoutes = require("./routes/sse");

app.use("/api/notifications", notificationRoutes);
app.use("/api/priority-inbox", priorityRoutes);
app.use("/api/stream", sseRoutes);


app.get("/health", (req, res) => {
  logger.info("Health check called");
  res.json({ status: "ok", service: "campus-notifications" });
});


app.use((req, res) => {
  logger.warn(`404 Not Found: ${req.method} ${req.path}`);
  res.status(404).json({ error: "Route not found" });
});


app.use((err, req, res, next) => {
  logger.error(`Unhandled error: ${err.message}`);
  res.status(500).json({ error: "Internal server error" });
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  logger.info(`Campus Notifications Service running on port ${PORT}`);
});

module.exports = app;

