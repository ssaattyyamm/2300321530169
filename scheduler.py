"""
Vehicle Maintenance Scheduler - Knapsack Problem Solution
Affordmed Campus Hiring Evaluation

Fetches depot and vehicle task data from APIs,
then uses dynamic programming to maximize impact within mechanic-hour budget.
"""

import requests
import json
import sys
from typing import List, Dict, Tuple

# ─── Logging Middleware Integration ───────────────────────────────────────────
# Using the logging middleware created in pre-test setup
# Assume LOGGER is imported from your logging middleware
# from logging_middleware import logger
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("VehicleScheduler")

# ─── API Configuration ────────────────────────────────────────────────────────
BASE_URL = "http://4.224.186.213/evaluation-service"
DEPOT_API = f"{BASE_URL}/depots"
VEHICLES_API = f"{BASE_URL}/vehicles"

HEADERS = {
    "Content-Type": "application/json",
    # Add auth token here if required
    # "Authorization": "Bearer <token>"
}


# ─── API Fetchers ─────────────────────────────────────────────────────────────

def fetch_depots() -> List[Dict]:
    """Fetch all depot data including available mechanic-hours."""
    logger.info("Fetching depot data from API...")
    try:
        response = requests.get(DEPOT_API, headers=HEADERS, timeout=10)
        response.raise_for_status()
        data = response.json()
        depots = data.get("depots", [])
        logger.info(f"Fetched {len(depots)} depots successfully.")
        return depots
    except requests.RequestException as e:
        logger.error(f"Failed to fetch depots: {e}")
        sys.exit(1)


def fetch_vehicles() -> List[Dict]:
    """Fetch all vehicle task data (TaskID, Duration, Impact)."""
    logger.info("Fetching vehicle task data from API...")
    try:
        response = requests.get(VEHICLES_API, headers=HEADERS, timeout=10)
        response.raise_for_status()
        data = response.json()
        vehicles = data.get("vehicles", [])
        logger.info(f"Fetched {len(vehicles)} vehicle tasks successfully.")
        return vehicles
    except requests.RequestException as e:
        logger.error(f"Failed to fetch vehicles: {e}")
        sys.exit(1)


# ─── Knapsack Solver ──────────────────────────────────────────────────────────

def knapsack_dp(tasks: List[Dict], capacity: int) -> Tuple[int, List[Dict]]:
    """
    0/1 Knapsack using Dynamic Programming.

    Args:
        tasks    : list of {"TaskID": str, "Duration": int, "Impact": int}
        capacity : total mechanic-hours available (budget)

    Returns:
        (max_impact, selected_tasks)

    Time  : O(n * capacity)
    Space : O(n * capacity)  — can be optimised to O(capacity) if memory is tight
    """
    n = len(tasks)
    # dp[i][w] = max impact using first i tasks with w hours available
    dp = [[0] * (capacity + 1) for _ in range(n + 1)]

    for i in range(1, n + 1):
        task = tasks[i - 1]
        duration = task["Duration"]
        impact = task["Impact"]
        for w in range(capacity + 1):
            # Don't take task i
            dp[i][w] = dp[i - 1][w]
            # Take task i (if it fits)
            if duration <= w:
                dp[i][w] = max(dp[i][w], dp[i - 1][w - duration] + impact)

    # Back-track to find selected tasks
    selected = []
    w = capacity
    for i in range(n, 0, -1):
        if dp[i][w] != dp[i - 1][w]:
            selected.append(tasks[i - 1])
            w -= tasks[i - 1]["Duration"]

    selected.reverse()
    return dp[n][capacity], selected


# ─── Per-Depot Scheduling ─────────────────────────────────────────────────────

def schedule_depot(depot: Dict, all_tasks: List[Dict]) -> Dict:
    """
    Schedule maintenance for a single depot.

    NOTE: The Vehicles API returns a flat list of tasks (not per-depot).
    All tasks are considered for each depot independently with that depot's budget.
    Adjust this function if the API later returns depot-specific task lists.
    """
    depot_id = depot["ID"]
    capacity = depot["MechanicHours"]

    logger.info(
        f"[Depot {depot_id}] Scheduling {len(all_tasks)} tasks "
        f"with {capacity} mechanic-hours budget..."
    )

    max_impact, selected = knapsack_dp(all_tasks, capacity)

    total_duration = sum(t["Duration"] for t in selected)
    logger.info(
        f"[Depot {depot_id}] Selected {len(selected)} tasks | "
        f"Total Duration: {total_duration}h / {capacity}h | "
        f"Total Impact: {max_impact}"
    )

    return {
        "DepotID": depot_id,
        "MechanicHoursBudget": capacity,
        "SelectedTaskCount": len(selected),
        "TotalDuration": total_duration,
        "TotalImpact": max_impact,
        "SelectedTasks": selected,
    }


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    logger.info("=== Vehicle Maintenance Scheduler Started ===")

    depots = fetch_depots()
    all_tasks = fetch_vehicles()

    results = []
    for depot in depots:
        result = schedule_depot(depot, all_tasks)
        results.append(result)

    # ── Print Results ──────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("VEHICLE MAINTENANCE SCHEDULE — OPTIMAL TASK SELECTION")
    print("=" * 70)

    for r in results:
        print(f"\n📍 Depot {r['DepotID']}")
        print(f"   Budget       : {r['MechanicHoursBudget']} mechanic-hours")
        print(f"   Hours Used   : {r['TotalDuration']} h")
        print(f"   Total Impact : {r['TotalImpact']}")
        print(f"   Tasks Selected ({r['SelectedTaskCount']}):")
        for t in r["SelectedTasks"]:
            print(
                f"     - TaskID: {t['TaskID']}  "
                f"Duration: {t['Duration']}h  "
                f"Impact: {t['Impact']}"
            )

    print("\n" + "=" * 70)

    # Save to JSON for submission
    output_path = "schedule_output.json"
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    logger.info(f"Results saved to {output_path}")

    logger.info("=== Vehicle Maintenance Scheduler Finished ===")


if __name__ == "__main__":
    main()
