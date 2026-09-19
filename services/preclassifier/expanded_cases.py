"""Deterministic, semantics-preserving variants of the labeled routing corpus."""

from copy import deepcopy

from benchmark_cases import CASES


def _rewrite_latest_user(messages: list[dict], prefix: str = "", suffix: str = "") -> list[dict]:
    rewritten = deepcopy(messages)
    for message in reversed(rewritten):
        if message.get("role") == "user" and isinstance(message.get("content"), str):
            message["content"] = f"{prefix}{message['content']}{suffix}"
            return rewritten
    raise ValueError("case has no text user message")


def expand_cases(cases: list[tuple]) -> list[tuple]:
    expanded = []
    for case_id, task_type, complexity, messages in cases:
        variants = {
            "original": deepcopy(messages),
            "polite": _rewrite_latest_user(messages, "Please help with this: "),
            "task": _rewrite_latest_user(messages, "Task: "),
            "clear": _rewrite_latest_user(messages, suffix=" Please respond clearly."),
            "system": [
                {"role": "system", "content": "Be concise and follow the user's request."},
                *deepcopy(messages),
            ],
        }
        # A prior assistant turn can legitimately make a conversational reply
        # complex, so only assert multi-turn invariance for task-bearing lanes.
        if (task_type, complexity) != ("conversation", "simple"):
            variants["context"] = [
                {"role": "assistant", "content": "Ready."},
                *deepcopy(messages),
            ]
        for variant_name, variant_messages in variants.items():
            expanded.append(
                (
                    f"{case_id}__{variant_name}",
                    task_type,
                    complexity,
                    variant_messages,
                )
            )
    return expanded


EXPANDED_CASES = expand_cases(CASES)
