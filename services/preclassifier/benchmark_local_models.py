"""Benchmark local Ollama models against the labeled routing corpus."""

import argparse
import asyncio
import json
import statistics
import time

import httpx

import app
from benchmark_cases import CASES
from challenge_cases import CHALLENGE_CASES


async def run_model(
    client: httpx.AsyncClient,
    base_url: str,
    model: str,
    concurrency: int,
    cases: list[tuple],
) -> dict:
    semaphore = asyncio.Semaphore(concurrency)

    async def classify_case(case):
        case_id, expected_task, expected_complexity, messages = case
        classify_messages, _ = app.build_classification_messages(messages)
        queued_at = time.monotonic()
        try:
            async with semaphore:
                started = time.monotonic()
                response = await client.post(
                    f"{base_url}/api/chat",
                    json={
                        "model": model,
                        "messages": classify_messages,
                        "stream": False,
                        "format": app.CLASSIFICATION_SCHEMA,
                        "keep_alive": "15m",
                        "options": {"temperature": 0, "num_predict": 40, "num_ctx": 4096},
                    },
                    timeout=45,
                )
                response.raise_for_status()
            data = response.json()
            task_type, complexity, valid = app.parse_classification(data["message"]["content"])
            return {
                "id": case_id,
                "correct": valid and (task_type, complexity) == (expected_task, expected_complexity),
                "valid": valid,
                "expected": f"{expected_task}|{expected_complexity}",
                "actual": f"{task_type}|{complexity}",
                "latency_ms": round((time.monotonic() - started) * 1000, 1),
                "queue_ms": round((started - queued_at) * 1000, 1),
                "prompt_tokens": int(data.get("prompt_eval_count", 0)),
                "completion_tokens": int(data.get("eval_count", 0)),
                "load_ms": round(int(data.get("load_duration", 0)) / 1_000_000, 1),
            }
        except Exception as exc:
            return {
                "id": case_id,
                "correct": False,
                "valid": False,
                "expected": f"{expected_task}|{expected_complexity}",
                "actual": f"error:{type(exc).__name__}",
                "latency_ms": round((time.monotonic() - queued_at) * 1000, 1),
                "queue_ms": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "load_ms": 0,
            }

    wall_started = time.monotonic()
    results = await asyncio.gather(*(classify_case(case) for case in cases))
    latencies = sorted(result["latency_ms"] for result in results)
    p95_index = max(0, min(len(latencies) - 1, int(len(latencies) * 0.95) - 1))
    wrong = [result for result in results if not result["correct"]]
    return {
        "model": model,
        "concurrency": concurrency,
        "cases": len(results),
        "accuracy_percent": round(100 * (len(results) - len(wrong)) / len(results), 1),
        "valid_percent": round(100 * sum(result["valid"] for result in results) / len(results), 1),
        "wall_seconds": round(time.monotonic() - wall_started, 2),
        "latency_ms_p50": round(statistics.median(latencies), 1),
        "latency_ms_p95": latencies[p95_index],
        "queue_ms_p50": round(statistics.median(result["queue_ms"] for result in results), 1),
        "prompt_tokens_total": sum(result["prompt_tokens"] for result in results),
        "completion_tokens_total": sum(result["completion_tokens"] for result in results),
        "wrong": wrong,
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://ollama:11434")
    parser.add_argument("--models", nargs="+", required=True)
    parser.add_argument("--concurrency", nargs="+", type=int, default=[1, 3])
    parser.add_argument("--dataset", choices=("base", "challenge"), default="base")
    args = parser.parse_args()
    cases = CASES if args.dataset == "base" else CHALLENGE_CASES
    async with httpx.AsyncClient() as client:
        for model in args.models:
            for concurrency in args.concurrency:
                result = await run_model(client, args.base_url, model, concurrency, cases)
                result["dataset"] = args.dataset
                print(json.dumps(result), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
