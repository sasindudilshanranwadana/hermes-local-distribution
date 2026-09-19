"""Benchmark the deployed classification policy without upstream generation."""

import asyncio
import json
import statistics
import time

import app
from expanded_cases import EXPANDED_CASES


async def one(case):
    case_id, expected_task, expected_complexity, messages = case
    started = time.monotonic()
    task_type, complexity, reported_ms, reason = await app.classify(messages)
    return {
        "id": case_id,
        "correct": (task_type, complexity) == (expected_task, expected_complexity),
        "latency_ms": (time.monotonic() - started) * 1000,
        "reported_ms": reported_ms,
        "reason": reason,
    }


async def run(mode: str):
    app.classification_cache = app.ClassificationCache(2048, 300)
    if mode == "sequential":
        results = []
        wall_started = time.monotonic()
        for case in EXPANDED_CASES:
            results.append(await one(case))
    else:
        wall_started = time.monotonic()
        results = await asyncio.gather(*(one(case) for case in EXPANDED_CASES))
    latencies = sorted(item["latency_ms"] for item in results)
    p95_index = max(0, min(len(latencies) - 1, int(len(latencies) * 0.95) - 1))
    reasons = {}
    for item in results:
        reasons[item["reason"]] = reasons.get(item["reason"], 0) + 1
    return {
        "mode": mode,
        "cases": len(results),
        "accuracy_percent": round(100 * sum(item["correct"] for item in results) / len(results), 1),
        "wall_ms": round((time.monotonic() - wall_started) * 1000, 1),
        "p50_ms": round(statistics.median(latencies), 2),
        "p95_ms": round(latencies[p95_index], 2),
        "reasons": reasons,
        "wrong": [item["id"] for item in results if not item["correct"]],
    }


async def main():
    print(json.dumps(await run("sequential")))
    print(json.dumps(await run("burst")))


if __name__ == "__main__":
    asyncio.run(main())
