"""Measure semantic routing quality on independently authored challenge cases."""

import asyncio
import json
import statistics
import time
from collections import Counter, defaultdict

import app
from challenge_cases import CHALLENGE_CASES


async def main() -> int:
    app.classification_cache = app.ClassificationCache(2048, 300)
    results = []
    started = time.monotonic()

    for case_id, expected_task, expected_complexity, messages in CHALLENGE_CASES:
        case_started = time.monotonic()
        task_type, complexity, _, reason = await app.classify(messages)
        results.append({
            "id": case_id,
            "expected": [expected_task, expected_complexity],
            "actual": [task_type, complexity],
            "task_correct": task_type == expected_task,
            "complexity_correct": complexity == expected_complexity,
            "correct": (task_type, complexity) == (expected_task, expected_complexity),
            "critical_underroute": expected_complexity == "complex" and complexity == "simple",
            "latency_ms": (time.monotonic() - case_started) * 1000,
            "reason": reason,
        })

    by_lane = defaultdict(lambda: [0, 0])
    for item in results:
        lane = "/".join(item["expected"])
        by_lane[lane][1] += 1
        by_lane[lane][0] += int(item["correct"])

    lane_accuracy = {
        lane: round(correct * 100 / total, 1)
        for lane, (correct, total) in sorted(by_lane.items())
    }
    latencies = sorted(item["latency_ms"] for item in results)
    p95_index = max(0, min(len(latencies) - 1, int(len(latencies) * 0.95) - 1))
    wrong = [item for item in results if not item["correct"]]
    report = {
        "cases": len(results),
        "exact_accuracy_percent": round(100 * (len(results) - len(wrong)) / len(results), 1),
        "task_accuracy_percent": round(100 * sum(x["task_correct"] for x in results) / len(results), 1),
        "complexity_accuracy_percent": round(100 * sum(x["complexity_correct"] for x in results) / len(results), 1),
        "balanced_lane_accuracy_percent": round(statistics.mean(lane_accuracy.values()), 1),
        "critical_underroutes": sum(x["critical_underroute"] for x in results),
        "latency_ms_p50": round(statistics.median(latencies), 3),
        "latency_ms_p95": round(latencies[p95_index], 3),
        "wall_ms": round((time.monotonic() - started) * 1000, 1),
        "reasons": dict(sorted(Counter(x["reason"] for x in results).items())),
        "lane_accuracy_percent": lane_accuracy,
        "wrong": wrong,
    }
    passed = report["exact_accuracy_percent"] >= 95.0 and report["critical_underroutes"] == 0
    report["quality_gate"] = "pass" if passed else "fail"
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
