import asyncio
import hashlib
import hmac
import json
import os
import re
import sqlite3
import time
import uuid
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

OMNIROUTE_BASE = os.getenv("OMNIROUTE_BASE", "http://omniroute:20129/v1").rstrip("/")
OMNIROUTE_API_KEY = os.environ["OMNIROUTE_API_KEY"]
CLIENT_API_KEYS = tuple(dict.fromkeys(
    key.strip() for key in os.getenv("CLIENT_API_KEYS", "").split(",") if key.strip()
))
OMNIROUTE_DB_PATH = os.getenv("OMNIROUTE_DB_PATH", "/omniroute-data/storage.sqlite")
OMNIROUTE_API_KEY_NAME = os.getenv("OMNIROUTE_API_KEY_NAME", "Hermes")
OLLAMA_BASE = os.getenv("OLLAMA_BASE", "http://ollama:11434")

# Keep routing's control plane independent from external provider quota.
CLASSIFIER_MODEL = os.getenv("CLASSIFIER_MODEL", "qwen2.5:1.5b")
LOCAL_CLASSIFIER_ENABLED = os.getenv("LOCAL_CLASSIFIER_ENABLED", "false").strip().lower() in {
    "1", "true", "yes", "on",
}

TASK_TYPES = ("coding", "conversation", "reasoning", "agentic-tool-use")
COMPLEXITIES = ("simple", "complex")
CLASSIFICATION_SCHEMA = {
    "type": "object",
    "properties": {
        "task_type": {"type": "string", "enum": list(TASK_TYPES)},
        "complexity": {"type": "string", "enum": list(COMPLEXITIES)},
    },
    "required": ["task_type", "complexity"],
}

# Decision matrix: (task_type, complexity) -> primary target.
#
# 2026-09-06: each lane now points at an OmniRoute round-robin *combo* rather
# than a single hardcoded provider/model. The combos own provider selection
# (rotating legs, skipping rate-limited/degraded providers automatically), so
# this file stays responsible only for classification. Measured before the
# change: 399 of the last 400 requests went to codex/gpt-5.6-terra, leaving
# every other connected provider idle.
#
# This also reverts a bad 2026-09-04 edit. That change removed
# groq/openai/gpt-oss-120b alongside nvidia's copy, believing both had been
# end-of-lifed upstream. Only nvidia's was actually dead (its credentials were
# exhausted); groq's still returns 200. That false conclusion left no free
# tool-capable model and collapsed every lane onto the paid backbone.
#
# groq/openai/gpt-oss-120b is nonetheless kept OUT of the tool-critical simple
# lanes: measured 2026-09-06 it emitted a tool call on only 2 of 6 identical
# prompts, while the same model served by cloudflare-ai scored 6/6. The pools
# use groq/openai/gpt-oss-20b (5/6) instead. See combo definitions in
# OmniRoute for the exact legs.
DECISION_MATRIX: dict[tuple[str, str], str] = {
    ("coding", "simple"): "pool-coding-simple",
    ("coding", "complex"): "pool-coding-complex",
    ("conversation", "simple"): "pool-chat",
    ("conversation", "complex"): "pool-chat",
    ("reasoning", "simple"): "pool-reasoning-simple",
    ("reasoning", "complex"): "pool-reasoning-complex",
    ("agentic-tool-use", "simple"): "pool-agentic-simple",
    ("agentic-tool-use", "complex"): "pool-agentic-complex",
}

# Classification-specific failover. The portable distribution uses only
# generated capability pools; it never assumes that another user owns a
# particular provider, subscription, or model.
FALLBACK_CHAINS: dict[tuple[str, str], list[str]] = {
    ("coding", "simple"): [
        "pool-coding-simple",
        "pool-coding-complex",
        "pool-reasoning-complex",
    ],
    ("coding", "complex"): [
        "pool-coding-complex",
        "pool-reasoning-complex",
    ],
    ("conversation", "simple"): [
        "pool-chat",
        "pool-reasoning-simple",
    ],
    ("conversation", "complex"): [
        "pool-chat",
        "pool-reasoning-complex",
    ],
    ("reasoning", "simple"): [
        "pool-reasoning-simple",
        "pool-reasoning-complex",
    ],
    ("reasoning", "complex"): [
        "pool-reasoning-complex",
    ],
    ("agentic-tool-use", "simple"): [
        "pool-agentic-simple",
        "pool-agentic-complex",
        "pool-coding-complex",
    ],
    ("agentic-tool-use", "complex"): [
        "pool-agentic-complex",
        "pool-coding-complex",
        "pool-reasoning-complex",
    ],
}

# These providers passed plain chat but failed a genuine tool-result round
# trip. They are restricted to fresh simple conversations, and their outgoing
# request has tool schemas removed so they cannot initiate root-capable work.
TOOL_FREE_ONLY_MODELS = {
    value.strip()
    for value in os.getenv("TOOL_FREE_ONLY_MODELS", "").split(",")
    if value.strip()
}

# Fail toward the cheapest, most available path - never toward a task_type
# whose fallback chain might land on a metered/complex model.
DEFAULT_TASK_TYPE = "conversation"
DEFAULT_COMPLEXITY = "simple"


def _client_is_authorized(authorization: str) -> bool:
    """Accept only explicitly configured client credentials.

    The upstream OmniRoute key is intentionally not a fallback: sharing that
    credential with clients would let a lost laptop access OmniRoute directly
    and would prevent independent device revocation.
    """
    provided = authorization.encode("utf-8")
    matched = False
    for key in CLIENT_API_KEYS:
        matched |= hmac.compare_digest(provided, f"Bearer {key}".encode("utf-8"))
    return matched

# Verified-real (not catalog-trusted) safe prompt-size ceilings, in tokens.
# OmniRoute's own /v1/models catalog advertises 128,000 for
# github/gpt-4o-2024-11-20, but the real Copilot-proxy-enforced limit is far
# smaller: confirmed 2026-08-30 by a genuine 400 - "prompt token count of
# 69501 exceeds the limit of 64000" - when a fallback-cascade landed here
# with an oversized prompt. That 400 then propagated to Hermes, which cached
# 64,000 as the context ceiling for our shared "auto" identity for the rest
# of the session (see CONTEXT-CEILING-COLLAPSE.md). github/gpt-4o-mini has no
# error of its own on record, but shares the same Copilot Free account/plan
# as -2024-11-20, so it's treated as the same real cap rather than assumed
# safe on no evidence. Only add an entry here once a real limit is observed
# or otherwise verified - never seed this from a catalog number, since that's
# exactly what was wrong before.
def _load_limit_map(name: str) -> dict[str, int]:
    raw = os.getenv(name, "{}").strip()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{name} must contain valid JSON") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"{name} must contain a JSON object")
    result: dict[str, int] = {}
    for model, limit in payload.items():
        if isinstance(model, str) and isinstance(limit, int) and limit > 0:
            result[model] = limit
    return result


CAPPED_MODEL_LIMITS: dict[str, int] = _load_limit_map("CAPPED_MODEL_LIMITS_JSON")
# Operational prompt budgets for free/developer tiers. These are deliberately
# conservative usage policies, not claims about each model's technical context
# window. Oversized turns remain on the established paid/subscription routes.
MODEL_POLICY_PROMPT_LIMITS: dict[str, int] = _load_limit_map(
    "MODEL_POLICY_PROMPT_LIMITS_JSON"
)
# Safety margin subtracted from a capped model's limit before comparing
# against our own rough prompt-size estimate - our estimate is chars/4, not a
# real tokenizer, so leave enough room that an undercount doesn't still route
# an oversized prompt into the cap.
CAPPED_MODEL_SAFETY_MARGIN = 4_000

# Response codes worth falling back on: upstream/gateway failures, not
# request-shape errors (a 400 will fail identically on every model) - EXCEPT
# a context-length-exceeded-shaped 400, which is model-specific (the next
# candidate may have a larger real window) and is checked separately via
# _is_context_length_exceeded_body().
FALLBACK_STATUS_CODES = {429, 500, 502, 503, 504}

# Mirrors the shape of message Hermes's own model_metadata.py looks for
# (parse_context_limit_from_error) - kept intentionally narrow (just the
# patterns we've actually observed) rather than copying Hermes's broad
# generic-number regex, to avoid false-positive retries on unrelated 400s.
_CONTEXT_LENGTH_EXCEEDED_PATTERNS = (
    re.compile(r"prompt token count of \d+ exceeds the limit of \d+", re.I),
    re.compile(r"context_length_exceeded", re.I),
    re.compile(r"maximum context length is \d+", re.I),
)


def _is_context_length_exceeded_body(status_code: int, body_text: str) -> bool:
    """True if a 400 response is shaped like a real context/prompt-size
    rejection from the provider, not a generic bad-request error. Used as
    defense-in-depth: the proactive CAPPED_MODEL_LIMITS filter should prevent
    this in the known case, but this catches an undiscovered small cap on any
    other leg, or a bad size estimate, without hardcoding a second model
    table."""
    if status_code != 400:
        return False
    return any(p.search(body_text) for p in _CONTEXT_LENGTH_EXCEEDED_PATTERNS)


def _estimate_prompt_tokens(messages: list[dict]) -> int:
    """Rough chars/4 estimate of the full outgoing prompt size. Not a real
    tokenizer - only needs to be good enough, with CAPPED_MODEL_SAFETY_MARGIN,
    to decide whether a capped leg is worth trying."""
    total_chars = 0
    for m in messages:
        total_chars += len(_flatten_text(m.get("content")))
    return total_chars // 4


def _estimate_request_tokens(body: dict) -> int:
    """Conservatively estimate every input-bearing part of the request.

    Serializing the complete JSON includes tool schemas, assistant tool-call
    arguments, metadata, and non-text blocks that the old text-only estimate
    ignored. Non-text content also receives a fixed modality allowance because
    a short image URL can expand to many provider-side input tokens.
    """
    serialized_bytes = len(
        json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    modality_allowance = 0
    for message in body.get("messages", []):
        if not isinstance(message, dict) or not isinstance(message.get("content"), list):
            continue
        modality_allowance += 1024 * sum(
            1
            for block in message["content"]
            if isinstance(block, dict) and block.get("type") != "text"
        )
    return (serialized_bytes + 3) // 4 + modality_allowance


def _has_tool_history(messages: list[dict]) -> bool:
    """True after a conversation has actually entered a tool-use loop.

    Hermes sends tool schemas on nearly every request, so the mere presence of
    the top-level ``tools`` field cannot distinguish plain chat from tool work.
    """
    return any(
        message.get("role") == "tool"
        or (message.get("role") == "assistant" and bool(message.get("tool_calls")))
        for message in messages
    )


def _has_tool_context(body: dict, messages: list[dict]) -> bool:
    """True when a request exposes tools or is already in a tool-use loop."""
    return any(field in body for field in ("tools", "tool_choice", "parallel_tool_calls")) or _has_tool_history(messages)


def _validated_messages(body: Any) -> list[dict]:
    """Validate the minimum OpenAI chat shape before classification."""
    if not isinstance(body, dict):
        raise ValueError("request body must be a JSON object")
    messages = body.get("messages")
    if not isinstance(messages, list) or not messages:
        raise ValueError("messages must be a non-empty array")
    allowed_roles = {"system", "user", "assistant", "tool"}
    for index, message in enumerate(messages):
        if not isinstance(message, dict):
            raise ValueError(f"messages[{index}] must be an object")
        if message.get("role") not in allowed_roles:
            raise ValueError(f"messages[{index}].role is invalid")
        if "content" not in message and not (
            message.get("role") == "assistant" and message.get("tool_calls")
        ):
            raise ValueError(f"messages[{index}].content is required")
        content = message.get("content")
        if content is not None and not isinstance(content, (str, list)):
            raise ValueError(f"messages[{index}].content must be text or content blocks")
    return messages


# Reasoning effort follows the work's classified difficulty. This prevents
# trivial prompts from consuming long reasoning traces while allowing complex
# coding, analysis, and tool workflows to use the capability already paid for.
#
# Verified 2026-09-06:
#  - `reasoning_effort` in the request body OVERRIDES an effort suffix baked
#    into a model name (claude-sonnet-4-6-low + effort=high produced high-tier
#    reasoning: 44 tokens vs 27 for a genuine low).
#  - Every pool leg accepts the field without error, including the gpt-oss
#    models on groq/cloudflare, which honour it despite exposing no
#    -low/-high variants (completion 31->130 and 43->127 from low to high).
#    github/gpt-4o-mini ignores it harmlessly, being a non-reasoning model.
#  - medium/high on a reasoning model only completes over a STREAMING
#    response. Non-streaming, OmniRoute aborts with "Direct response did not
#    start within 60000ms" while the model is still in its reasoning phase.
#    Hermes always streams, so this is safe in production - but keep it in
#    mind when reproducing by hand with curl.
POOL_EFFORT: dict[str, str] = {
    "pool-coding-complex": "medium",
    "pool-agentic-complex": "medium",
    "pool-reasoning-complex": "medium",
    # open-weight, free tier -> high is free, so use it
    "pool-coding-simple": "high",
    "pool-agentic-simple": "high",
    "pool-reasoning-simple": "high",
    # trivial conversational turns need no reasoning budget at all
    "pool-chat": "low",
}

# Every concrete (non-pool) target left in FALLBACK_CHAINS is a paid backend -
# codex/gpt-5.6-terra, claude/claude-sonnet-4-6, github/gpt-4o-mini - reached
# only when the pool layer itself is unavailable. They inherit the same paid
# cap. Add an explicit POOL_EFFORT entry for any open-weight model that later
# becomes a direct fallback leg, or it will be needlessly capped here.
PAID_MODEL_EFFORT_CAP = "medium"

ROUTE_EFFORT: dict[tuple[str, str], str] = {
    ("conversation", "simple"): "low",
    ("conversation", "complex"): "medium",
    ("coding", "simple"): "low",
    ("coding", "complex"): "high",
    ("reasoning", "simple"): "medium",
    ("reasoning", "complex"): "medium",
    ("agentic-tool-use", "simple"): "medium",
    ("agentic-tool-use", "complex"): "high",
}

# Efforts we treat as "caller had no real opinion" and are free to replace.
# Hermes sets reasoning_effort: medium globally in config.yaml, so medium is
# a default rather than a considered choice. An explicit "none"/"low"/"high"
# is left alone: the auxiliary lanes in Hermes's config (title_generation,
# background_review, web_extract, approval) deliberately pin low/none, and
# silently upgrading those to high would burn quota on trivial background
# work - the exact waste this router exists to avoid.
EFFORT_TREATED_AS_UNSET = {None, "", "medium", "auto"}
CLAUDE_MAX_EFFORT = "medium"
CLAUDE_ALLOWED_EFFORTS = {"none", "minimal", "low", CLAUDE_MAX_EFFORT}
MEDIUM_EFFORT_CAP_TARGETS = {"pool-reasoning-complex"}


def _effort_is_unset(value: Any) -> bool:
    return (value.lower() if isinstance(value, str) else value) in EFFORT_TREATED_AS_UNSET


def _is_claude_family(model: str) -> bool:
    return any(part.startswith("claude-") for part in model.lower().split("/"))


def _requires_medium_effort_cap(model: str) -> bool:
    return _is_claude_family(model) or model in MEDIUM_EFFORT_CAP_TARGETS


def _cap_effort_for_model(model: str, effort: Any) -> Any:
    if (
        _requires_medium_effort_cap(model)
        and isinstance(effort, str)
        and effort.lower() not in CLAUDE_ALLOWED_EFFORTS
    ):
        return CLAUDE_MAX_EFFORT
    return effort


def _selected_effort(body: dict, model: str, task_type: str | None, complexity: str | None) -> Any:
    if not _effort_is_unset(body.get("reasoning_effort")):
        return body.get("reasoning_effort")
    route_effort = ROUTE_EFFORT.get((task_type, complexity))
    if route_effort:
        return route_effort
    return POOL_EFFORT.get(model, PAID_MODEL_EFFORT_CAP if not _is_combo_target(model) else None)


def _prepare_forward_body(
    body: dict, model: str, task_type: str | None = None, complexity: str | None = None,
) -> dict:
    """Build a per-attempt body without mutating the caller's request.

    Effort is chosen from the classification when available and otherwise
    falls back to the target-specific compatibility policy.
    """
    forward_body = dict(body)
    forward_body["model"] = model
    if model in TOOL_FREE_ONLY_MODELS:
        forward_body.pop("tools", None)
        forward_body.pop("tool_choice", None)
        forward_body.pop("parallel_tool_calls", None)
    effort = _cap_effort_for_model(
        model,
        _selected_effort(body, model, task_type, complexity),
    )
    if effort and (
        _effort_is_unset(forward_body.get("reasoning_effort"))
        or _requires_medium_effort_cap(model)
    ):
        forward_body["reasoning_effort"] = effort
    return forward_body


def _upstream_headers(forward_body: dict, force_no_cache: bool) -> dict[str, str]:
    """Build OmniRoute headers with conservative semantic-cache isolation.

    OmniRoute v3.8.50's semantic cache key covers messages and generation
    parameters but not tool schemas/tool_choice. Reusing a cached response in
    a tool-capable turn could therefore replay a response produced for a
    different tool surface. Keep caching for genuinely tool-free chat, while
    explicitly bypassing it for tool-bearing requests and tool-result loops.
    """
    headers = {
        "Authorization": f"Bearer {OMNIROUTE_API_KEY}",
        "Content-Type": "application/json",
    }
    if force_no_cache or bool(forward_body.get("tools")):
        headers["X-OmniRoute-No-Cache"] = "true"
    return headers


# This service owns failover. Three attempts cap retry amplification while
# retaining two independent alternatives.
MAX_FORWARD_ATTEMPTS = 3

MAX_CONTEXT_TURNS = 4
MAX_CONTEXT_CHARS = 2500
MAX_LATEST_USER_CHARS = 3000
# Classification is local through Ollama. Both the classifier and Mem0 embedder
# are kept resident, so a unique prompt should no longer pay model-load time.
# Fail over to the deterministic heuristic quickly if local inference stalls;
# a routing decision must never add a 30-second tax to an ordinary turn.
CLASSIFY_TIMEOUT_S = 10.0
# Hard wall-clock budget for the complete classification operation, including
# time spent waiting for a local inference slot. Without this bound a burst can
# queue for many multiples of CLASSIFY_TIMEOUT_S before inference even starts.
CLASSIFY_TOTAL_TIMEOUT_S = 8.0
FORWARD_TIMEOUT_S = 300.0
LOCAL_COOLDOWN_DEFAULT_S = 60.0
QUOTA_EXHAUSTED_THRESHOLD_PERCENT = 0.5
API_KEY_CAP_SOFT_STOP_RATIO = 0.95

LOG_PATH = "/app/logs/decisions.log"
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
DECISION_LOG_MAX_BYTES = 10 * 1024 * 1024
DECISION_LOG_BACKUP_COUNT = 3

# Decision logging used to write synchronously on every request, blocking the
# single uvicorn worker's event loop for the fsync. Under concurrent load
# that stall compounds with classifier_semaphore contention and can delay
# unrelated in-flight connections - move the actual write off the request
# path onto a dedicated background thread with a bounded queue and bounded
# on-disk retention.
import queue as _queue
import threading as _threading

DECISION_LOG_QUEUE_MAX_ENTRIES = 4096
_log_queue: "_queue.Queue[dict]" = _queue.Queue(maxsize=DECISION_LOG_QUEUE_MAX_ENTRIES)
runtime_metrics: dict[str, int] = {
    "decision_logs_dropped": 0,
    "decision_logs_written": 0,
    "invalid_requests": 0,
    "classifications_total": 0,
    "classifications_cache_hit": 0,
    "classifications_fast_path": 0,
    "classifications_heuristic_primary": 0,
    "classifications_local_model": 0,
    "classifications_fallback": 0,
    "classification_latency_ms_total": 0,
    "delegation_routes_total": 0,
    "delegation_routes_avoid": 0,
    "delegation_routes_consider": 0,
    "delegation_routes_require": 0,
}


def _append_decision_log(
    entry: dict,
    path: str = LOG_PATH,
    max_bytes: int = DECISION_LOG_MAX_BYTES,
    backup_count: int = DECISION_LOG_BACKUP_COUNT,
) -> None:
    """Append one JSON line and rotate before the configured size ceiling."""
    line = json.dumps(entry) + "\n"
    line_bytes = len(line.encode("utf-8"))
    if os.path.exists(path) and os.path.getsize(path) + line_bytes > max_bytes:
        if backup_count > 0:
            oldest = f"{path}.{backup_count}"
            if os.path.exists(oldest):
                os.remove(oldest)
            for index in range(backup_count - 1, 0, -1):
                source = f"{path}.{index}"
                if os.path.exists(source):
                    os.replace(source, f"{path}.{index + 1}")
            os.replace(path, f"{path}.1")
        else:
            os.remove(path)
    with open(path, "a", encoding="utf-8") as log_file:
        log_file.write(line)


def _log_writer_loop() -> None:
    while True:
        entry = _log_queue.get()
        _append_decision_log(entry)
        runtime_metrics["decision_logs_written"] += 1


_threading.Thread(target=_log_writer_loop, daemon=True, name="decision-log-writer").start()

SYSTEM_PROMPT = """Classify the latest user request for model routing.
Return only the requested JSON object.

task_type:
- coding: deliverable is code/config/document editing or a specific bug fix.
  This includes small in-place edits described in prose (fix a typo, add a
  docstring, rename a variable) - the deliverable is still an edit, not an
  explanation, even though no code block was pasted.
- agentic-tool-use: deliverable is an executed outcome: deploy, install, inspect,
  browse, run commands, or change external state. A request to look something
  up in the live environment (list files, check if a service is running) is
  agentic-tool-use, not reasoning, because it requires an action, not recall.
- reasoning: deliverable is an answer, analysis, comparison, plan, or judgment,
  where nothing is edited or executed - the user wants an explanation.
- conversation: greeting, thanks, acknowledgement, or vague follow-up with no
  task attached (e.g. "thanks, that works!", "sounds good", "what's up").

complexity:
- complex: debugging; multi-step, multi-file, production, architecture, security,
  prior-context-dependent, or costly-to-get-wrong work.
- simple: greeting, lookup, one small self-contained action, or short explanation.

Examples:
- "fix the typo in this string" -> coding|simple (an edit, not an explanation)
- "add a docstring to this function" -> coding|simple
- "thanks, that works great!" -> conversation|simple (acknowledgement, no task)
- "list files in the current directory" -> agentic-tool-use|simple (an action)
- "explain how TCP handshakes work" -> reasoning|simple (recall/explanation only)

Prefer complex when uncertain. A request to execute several steps is
agentic-tool-use|complex; a named source/config edit is coding|complex."""

app = FastAPI()
client = httpx.AsyncClient(timeout=FORWARD_TIMEOUT_S)
local_provider_cooldowns: dict[str, float] = {}
# Three-way CPU contention reduced measured accuracy and caused 45-second
# timeouts. Obvious prompts now avoid Ollama; serialize the ambiguous remainder.
CLASSIFIER_CONCURRENCY = 1
classifier_semaphore = asyncio.Semaphore(CLASSIFIER_CONCURRENCY)
CLASSIFICATION_CACHE_TTL_S = 300.0
CLASSIFICATION_CACHE_MAX_ENTRIES = 2048


class ClassificationCache:
    """Small TTL/LRU cache for classification results.

    The previous process-global dictionary never evicted expired entries and
    keyed only on the latest user text. That both leaked memory and reused a
    context-dependent label (for example, "fix it") across unrelated turns.
    """

    def __init__(self, max_entries: int, ttl_seconds: float) -> None:
        self.max_entries = max_entries
        self.ttl_seconds = ttl_seconds
        self._entries: OrderedDict[str, tuple[float, str, str]] = OrderedDict()

    def get(self, key: str) -> tuple[str, str] | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        expires_at, task_type, complexity = entry
        if expires_at <= time.monotonic():
            self._entries.pop(key, None)
            return None
        self._entries.move_to_end(key)
        return task_type, complexity

    def put(self, key: str, task_type: str, complexity: str) -> None:
        self._entries[key] = (
            time.monotonic() + self.ttl_seconds,
            task_type,
            complexity,
        )
        self._entries.move_to_end(key)
        while len(self._entries) > self.max_entries:
            self._entries.popitem(last=False)

    def __len__(self) -> int:
        return len(self._entries)


classification_cache = ClassificationCache(
    max_entries=CLASSIFICATION_CACHE_MAX_ENTRIES,
    ttl_seconds=CLASSIFICATION_CACHE_TTL_S,
)


def _flatten_text(content: Any) -> str:
    """Chat content can be a string or a list of content blocks; reduce to plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return " ".join(parts)
    return ""


def build_classification_messages(messages: list[dict]) -> tuple[list[dict], str]:
    """Pull the last few user/assistant text turns (no tool calls/system bulk) plus
    the latest user message, trimmed to a sane size for a cheap classify call."""
    text_turns = [
        m for m in messages
        if m.get("role") in ("user", "assistant") and _flatten_text(m.get("content"))
    ]
    latest_user = ""
    latest_user_index = -1
    for idx in range(len(text_turns) - 1, -1, -1):
        m = text_turns[idx]
        if m.get("role") == "user":
            latest_user = _flatten_text(m.get("content"))
            latest_user_index = idx
            break

    # The latest user request is rendered separately below. Do not duplicate
    # it in the context block: Hermes may attach substantial memory/tool
    # metadata to that turn, and the duplicate previously made a tiny routing
    # decision consume twice the input and occasionally hit the timeout.
    prior_turns = text_turns[:latest_user_index] if latest_user_index >= 0 else text_turns
    recent = prior_turns[-MAX_CONTEXT_TURNS:]
    lines = []
    used = 0
    for m in recent:
        text = _flatten_text(m.get("content")).strip()
        if not text:
            continue
        snippet = text[:700]
        line = f"{m['role']}: {snippet}"
        if used + len(line) > MAX_CONTEXT_CHARS:
            break
        lines.append(line)
        used += len(line)

    context_block = "\n".join(lines) if lines else "(no prior context)"
    latest_for_classifier = latest_user
    if len(latest_for_classifier) > MAX_LATEST_USER_CHARS:
        latest_for_classifier = (
            latest_for_classifier[:2000]
            + "\n...[classifier-only truncation]...\n"
            + latest_for_classifier[-1000:]
        )
    user_prompt = (
        f"[Recent conversation]\n{context_block}"
        f"\n\n[Latest user message]\n{latest_for_classifier}"
    )
    return (
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        latest_user,
    )


def _classification_cache_key(messages: list[dict]) -> str:
    """Hash the exact bounded classifier input, including recent context."""
    classify_messages, _ = build_classification_messages(messages)
    payload = json.dumps(classify_messages, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def parse_classification(raw: str) -> tuple[str, str, bool]:
    """Parse the classifier's "<task_type>|<complexity>" reply. Returns
    (task_type, complexity, was_valid) - was_valid=False means a default was
    substituted for an unparseable or out-of-vocabulary reply."""
    raw = raw.strip().lower()
    try:
        structured = json.loads(raw)
        task_type = str(structured.get("task_type", "")).strip()
        complexity = str(structured.get("complexity", "")).strip()
        if task_type in TASK_TYPES and complexity in COMPLEXITIES:
            return task_type, complexity, True
    except (json.JSONDecodeError, AttributeError):
        pass
    parts = raw.split("|")
    if len(parts) != 2:
        return DEFAULT_TASK_TYPE, DEFAULT_COMPLEXITY, False
    task_type, complexity = parts[0].strip(), parts[1].strip()
    if task_type not in TASK_TYPES or complexity not in COMPLEXITIES:
        return DEFAULT_TASK_TYPE, DEFAULT_COMPLEXITY, False
    return task_type, complexity, True


def heuristic_classification(messages: list[dict]) -> tuple[str, str]:
    """Fast intent-aware classifier used on the production primary path.

    The original implementation treated the presence of words such as ``fix``,
    ``install`` or ``code`` as the intent.  That makes acknowledgements
    ("thanks for fixing the bug") and advice requests ("should I install it?")
    look like executable work.  Prefer sentence intent and explicit execution
    boundaries first, then use keywords only as supporting evidence.
    """
    text_turns = [
        _flatten_text(m.get("content")) for m in messages
        if m.get("role") in ("user", "assistant") and _flatten_text(m.get("content"))
    ]
    latest = next(
        (_flatten_text(m.get("content")) for m in reversed(messages) if m.get("role") == "user"),
        "",
    ).lower()
    recent_context = " ".join(text_turns[-3:]).lower()
    intent_text = re.sub(r"^(?:please help with this:|task:)\s*", "", latest)
    def has_signal(text: str, signals: tuple[str, ...]) -> bool:
        return any(
            signal in text if " " in signal or any(ch in signal for ch in ".-_/:")
            else re.search(rf"\b{re.escape(signal)}\b", text) is not None
            for signal in signals
        )

    acknowledgement = bool(re.search(
        r"^(thanks|thank you|great\b|perfect\b|sounds good\b|got it\b|no worries\b|"
        r"(?:okay|ok)\b.*\b(?:finished|done|complete))",
        intent_text,
    ))
    acknowledgement_request = bool(re.search(
        r"\b(?:now|but|please|could you|can you)\b.*\b"
        r"(?:fix|change|run|check|install|deploy|edit|write|create|remove|delete)\b",
        intent_text,
    )) or "?" in latest
    casual_conversation = bool(re.search(
        r"\b(?:how are you|talk it through|talk for a while|need reassurance|"
        r"just need .*conversation|please listen|stay with me|unpack .*feeling|"
        r"continue that conversation|feel overwhelmed|feel burned out|friend died|"
        r"family situation|emotionally exhausting)\b",
        intent_text,
    ))
    explicit_no_action = bool(re.search(
        r"\b(?:do not|don't|without)\s+(?:edit|run|execute|install|deploy|"
        r"modify|touch|apply|save|write)|\bdo not change (?:anything|the (?:server|system|"
        r"file|code|config|configuration))|\bwithout changing|"
        r"\b(?:analysis only|just advise|advice only|"
        r"do not solve it|not a new plan)\b",
        intent_text,
    ))
    answer_intent = bool(re.search(
        r"^(?:please\s+)?(?:explain|what\b|what's\b|why\b|how\b|which\b|"
        r"should\b|tell me\b|summarize|compare|analyze|assess|evaluate|recommend|"
        r"prove|disprove|determine|challenge|threat-model|design and compare)\b",
        intent_text,
    )) or explicit_no_action

    agent_signals = (
        "deploy", "restart", "run", "execute", "check", "inspect", "verify",
        "install", "configure", "set up", "connect", "remove", "delete", "create", "send",
        "look up", "find", "search", "browse", "list", "show", "download", "call",
        "audit", "research", "export", "restore", "inventory", "clean up",
        "trace", "benchmark",
    )
    code_edit_signals = (
        "fix", "implement", "refactor", "rename", "add", "change", "correct",
        "replace", "write", "patch", "update", "upgrade", "redesign", "profile",
        "eliminate", "make", "edit",
    )
    code_artifacts = (
        "code", "script", "docker-compose", "config.yaml", "config file", "source file",
        "function", "class", "bug", "docstring", "migration", "react", "api schema",
        "settings.py", "regular expression", "regex", "json", "unit test", "annotation",
        "module", "endpoint", "worker", "schema", "application", "memory leak", "comment",
        "authentication", "authorization", "webhook", "api", "path", "typo", "string",
        "race condition", "panel",
    )
    direct_agent_action = has_signal(latest, agent_signals)
    direct_code_edit = has_signal(latest, code_edit_signals) and has_signal(recent_context, code_artifacts)

    # Operational verbs dominate when the requested outcome needs live tools or
    # external state.  A bare "fix it" in coding context remains coding.
    operational_context = has_signal(latest, (
        "server", "vps", "container", "service", "staging", "production requests",
        "readiness endpoint", "error log", "installed", "current disk", "repository",
        "github", "/tmp/", "release notes", "exposed ports", "database", "backup",
    ))
    execution_sequence = sum(1 for signal in agent_signals if has_signal(latest, (signal,))) >= 2

    if acknowledgement and not acknowledgement_request:
        task_type = "conversation"
    elif casual_conversation and not direct_code_edit:
        task_type = "conversation"
    elif answer_intent:
        task_type = "reasoning"
    elif direct_agent_action and (operational_context or execution_sequence):
        task_type = "agentic-tool-use"
    elif direct_code_edit:
        task_type = "coding"
    elif direct_agent_action:
        task_type = "agentic-tool-use"
    elif "?" in latest:
        task_type = "reasoning"
    else:
        task_type = "conversation"

    complex_signals = (
        "debug", "investigate", "production", "architecture", "security", "multi-step",
        "end-to-end", "root cause", "every",
        "fallback", "quota", "rate limit", "deploy", "configure", "implement", "refactor",
        "across", "tradeoff", "failure recovery", "audit", "distributed", "clock skew",
        "network partition", "multi-tenant", "root-capable", "root tools", "untrusted web",
        "mitigation", "consistency",
        "migration", "rollback", "entire", "whole", "bottleneck", "multiple files",
        "concurrent", "major version", "incompatible", "old consumers", "during rollout",
        "memory leak", "authorization bypass", "regression coverage", "zero-downtime",
        "zero downtime", "dual writes", "backfill", "multi-region", "regulatory",
        "prove or disprove", "correlated", "detailed", "risks", "tail latency",
        "quota exhaustion", "privacy", "data-retention", "external model providers",
        "correlate", "browser tests", "compare their licenses", "from outside",
        "isolated container", "row counts", "first production requests", "safe to remove",
        "timelines", "most likely cause", "defend your conclusion", "outage",
        "emotionally", "overwhelmed", "anxious", "burned out", "grief", "friend died",
        "family situation", "reassurance", "talk it through", "unpack that feeling",
    )
    context_dependent = len(text_turns) > 1 and any(
        token in latest.split() for token in ("it", "that", "those", "them", "again")
    )
    action_count = sum(1 for signal in agent_signals if has_signal(latest, (signal,)))
    code_action_count = sum(1 for signal in code_edit_signals if has_signal(latest, (signal,)))
    complexity = "complex" if (
        len(latest) > 500
        or context_dependent
        or has_signal(latest, complex_signals)
        or action_count >= 3
        or code_action_count >= 3
    ) else "simple"
    if acknowledgement and not acknowledgement_request:
        complexity = "simple"
    return task_type, complexity


def _fast_path_classification(messages: list[dict]) -> tuple[str, str] | None:
    """Classify only syntactically obvious requests without spending an
    Ollama inference. Ambiguous and context-dependent turns still use the
    learned classifier."""
    latest = next(
        (_flatten_text(m.get("content")).strip().lower() for m in reversed(messages)
         if m.get("role") == "user"),
        "",
    )
    prior_text_turns = [
        m for m in messages[:-1]
        if m.get("role") in {"user", "assistant"} and _flatten_text(m.get("content"))
    ]
    if prior_text_turns and re.search(r"\b(it|that|those|them|again)\b", latest):
        return None
    obvious_patterns = (
        r"^(hi|hello|hey|good (morning|afternoon|evening)|thanks|thank you|sounds good)\b",
        r"\b(typo|docstring|variable|function|source file|config\.ya?ml|docker-compose|react frontend|api schema)\b",
        r"^(list (the )?files|check whether|look up|run (the )?(unit )?test|inspect the current|deploy\b|browse\b|run an? end-to-end|deeply inspect)\b",
        r"^(explain|what is|what's the difference|compare|analyze|assess|threat-model)\b",
    )
    if any(re.search(pattern, latest) for pattern in obvious_patterns):
        return heuristic_classification(messages)
    return None


def _tightest_simple_budget(task_type: str) -> int | None:
    """Smallest MODEL_POLICY_PROMPT_LIMITS ceiling among that task_type's
    simple-lane candidates, or None if none of them carry a policy budget
    (e.g. a lane with no remaining free-tier legs)."""
    primary = DECISION_MATRIX.get((task_type, "simple"))
    chain = FALLBACK_CHAINS.get((task_type, "simple"), [])
    candidates = ([primary] if primary else []) + list(chain)
    limits = [MODEL_POLICY_PROMPT_LIMITS[m] for m in candidates if m in MODEL_POLICY_PROMPT_LIMITS]
    return min(limits) if limits else None


def _guard_request_size(
    task_type: str, complexity: str, prompt_tokens: int,
) -> tuple[str, str, str]:
    """Escalate a simple classification when the complete request is too large
    for the task's most constrained simple-tier target."""
    if complexity == "simple":
        budget = _tightest_simple_budget(task_type)
        if budget is not None and prompt_tokens > budget:
            return task_type, "complex", "; complete_request_forced_complex"
    return task_type, complexity, ""


def _size_guarded_heuristic(messages: list[dict]) -> tuple[str, str, str]:
    """heuristic_classification(), with a size override: the heuristic has no
    notion of prompt size, so on its own it can hand back "simple" for a
    prompt that's already too big for every simple-lane candidate. Since this
    path only runs when local classification itself is degraded (timeout or
    unparseable reply), it's exactly the moment an oversized prompt is most
    likely to get misrouted - force "complex" for this task_type instead,
    which routes to lanes with real headroom. Independent, earlier-catching
    counterpart to _candidate_chain()'s post-hoc simple-to-complex escalation."""
    task_type, complexity = heuristic_classification(messages)
    note = ""
    if complexity == "simple":
        budget = _tightest_simple_budget(task_type)
        if budget is not None and _estimate_prompt_tokens(messages) > budget:
            complexity = "complex"
            note = "; oversized_prompt_forced_complex"
    return task_type, complexity, note


async def classify(messages: list[dict]) -> tuple[str, str, int, str]:
    runtime_metrics["classifications_total"] += 1
    classify_messages, latest_user = build_classification_messages(messages)
    started = time.monotonic()
    cache_key = _classification_cache_key(messages) if latest_user.strip() else ""
    cached = classification_cache.get(cache_key) if cache_key else None
    if cached:
        runtime_metrics["classifications_cache_hit"] += 1
        return cached[0], cached[1], 0, "classified_cache_hit"
    fast_path = _fast_path_classification(messages)
    if fast_path is not None:
        if cache_key:
            classification_cache.put(cache_key, fast_path[0], fast_path[1])
        latency_ms = int((time.monotonic() - started) * 1000)
        runtime_metrics["classifications_fast_path"] += 1
        runtime_metrics["classification_latency_ms_total"] += latency_ms
        return fast_path[0], fast_path[1], latency_ms, "classified_fast_path"
    if not LOCAL_CLASSIFIER_ENABLED:
        task_type, complexity, _ = _size_guarded_heuristic(messages)
        if cache_key:
            classification_cache.put(cache_key, task_type, complexity)
        latency_ms = int((time.monotonic() - started) * 1000)
        runtime_metrics["classifications_heuristic_primary"] += 1
        runtime_metrics["classification_latency_ms_total"] += latency_ms
        return task_type, complexity, latency_ms, "classified_heuristic_primary"
    try:
        async with asyncio.timeout(CLASSIFY_TOTAL_TIMEOUT_S):
            async with classifier_semaphore:
                cached = classification_cache.get(cache_key) if cache_key else None
                if cached:
                    runtime_metrics["classifications_cache_hit"] += 1
                    return cached[0], cached[1], int((time.monotonic() - started) * 1000), "classified_cache_hit"
                try:
                    resp = await client.post(
                        f"{OLLAMA_BASE}/api/chat",
                        json={
                            "model": CLASSIFIER_MODEL,
                            "messages": classify_messages,
                            "stream": False,
                            "format": CLASSIFICATION_SCHEMA,
                            "keep_alive": "10m",
                            "options": {"temperature": 0, "num_predict": 40, "num_ctx": 4096},
                        },
                        timeout=min(CLASSIFY_TIMEOUT_S, CLASSIFY_TOTAL_TIMEOUT_S),
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    raw = data["message"]["content"]
                    task_type, complexity, was_valid = parse_classification(raw)
                    if was_valid:
                        reason = "classified"
                    else:
                        task_type, complexity, guard_note = _size_guarded_heuristic(messages)
                        reason = f"fallback_to_heuristic: unparseable_reply({raw!r}){guard_note}"
                except Exception as e:
                    task_type, complexity, guard_note = _size_guarded_heuristic(messages)
                    reason = f"fallback_to_heuristic: {type(e).__name__}: {e}{guard_note}"
    except TimeoutError:
        task_type, complexity, guard_note = _size_guarded_heuristic(messages)
        reason = f"fallback_to_heuristic: total_timeout{guard_note}"
    if cache_key:
        classification_cache.put(cache_key, task_type, complexity)
    latency_ms = int((time.monotonic() - started) * 1000)
    if reason.startswith("fallback_to_heuristic"):
        runtime_metrics["classifications_fallback"] += 1
    else:
        runtime_metrics["classifications_local_model"] += 1
    runtime_metrics["classification_latency_ms_total"] += latency_ms
    return task_type, complexity, latency_ms, reason


def delegation_recommendation(
    messages: list[dict], *, task_type: str, complexity: str,
) -> dict[str, Any]:
    """Return a deterministic, token-free delegation recommendation.

    The policy deliberately requires strong evidence before forcing a child:
    delegation has startup/context cost, so complex but tightly coupled work is
    left to model judgment. Explicit user intent always wins.
    """
    latest = next(
        (_flatten_text(message.get("content")).strip().lower()
         for message in reversed(messages) if message.get("role") == "user"),
        "",
    )

    def contains(pattern: str) -> bool:
        return re.search(pattern, latest, flags=re.IGNORECASE) is not None

    if contains(
        r"\b(?:do not|don't|dont|never)\s+(?:delegate|use (?:sub-?agents?|other agents?))\b|"
        r"\b(?:no|without)\s+(?:delegation|sub-?agents?)\b|\bwork (?:on it )?yourself\b"
    ):
        return {
            "action": "avoid", "score": 0.0, "recommended_children": 0,
            "parallelizable": False, "reasons": ["explicit_no_delegation"],
        }

    explicit_parallel = contains(
        r"\b(?:delegate|parallel(?:ize|ise)?|in parallel|multiple agents?|"
        r"several agents?|sub-?agents?|split (?:this|the work|it) (?:up|across))\b"
    )
    if explicit_parallel:
        requested = re.search(r"\b(2|3|4|5|6|7|8|9|10|two|three|four|five)\s+(?:agents?|sub-?agents?|workers?)\b", latest)
        words = {"two": 2, "three": 3, "four": 4, "five": 5}
        child_count = 3
        if requested:
            raw = requested.group(1)
            child_count = words.get(raw, int(raw) if raw.isdigit() else 3)
        return {
            "action": "require", "score": 1.0,
            "recommended_children": max(2, min(10, child_count)),
            "parallelizable": True, "reasons": ["explicit_parallel_request"],
        }

    research = contains(r"\b(?:research|investigate|evaluate|compare)\b")
    implementation = contains(r"\b(?:implement|build|create|migrate|fix|patch|deploy)\b")
    independent_verification = contains(
        r"\b(?:independent(?:ly)?\s+(?:verif|review|test)|second (?:review|opinion))"
    )
    if research and implementation and independent_verification:
        return {
            "action": "require", "score": 0.92, "recommended_children": 3,
            "parallelizable": True,
            "reasons": ["research_implementation_verification"],
        }

    cross_boundary = contains(
        r"\b(?:cross-platform|multiple repositories|multiple repos|multi-repo|"
        r"mac(?:os)? and windows|windows and mac(?:os)?)\b"
    )
    broad_audit = contains(
        r"\b(?:audit|inspect|review|assess)\b.*\b(?:entire|whole|across|api|database|deployment)\b"
    ) and (
        latest.count(",") >= 2
        or contains(r"\b(?:multiple|every|all)\s+(?:systems?|subsystems?|services?|components?)\b")
        or contains(r"\b(?:entire|whole)\s+(?:vps|system|stack|platform)\b")
    )
    production_assurance = (
        contains(r"\b(?:security|production|authorization|authentication)\b")
        and contains(r"\b(?:independent(?:ly)?|second (?:review|opinion)|verify|audit)\b")
    )
    if cross_boundary or broad_audit or production_assurance:
        reasons = []
        if cross_boundary:
            reasons.append("cross_boundary_work")
        if broad_audit:
            reasons.append("broad_multi_subsystem_audit")
        if production_assurance:
            reasons.append("independent_production_assurance")
        return {
            "action": "require", "score": 0.86,
            "recommended_children": min(4, max(2, len(reasons) + 1)),
            "parallelizable": True, "reasons": reasons,
        }

    conversational_complexity = task_type == "conversation" and contains(
        r"\b(?:feel|feeling|emotion|grief|anxious|overwhelmed|burned out|"
        r"talk it through|reassurance|family situation|friend died)\b"
    )
    if complexity == "simple" or conversational_complexity:
        return {
            "action": "avoid", "score": 0.1, "recommended_children": 0,
            "parallelizable": False, "reasons": ["trivial_or_self_contained"],
        }

    return {
        "action": "consider", "score": 0.55, "recommended_children": 1,
        "parallelizable": False, "reasons": ["complex_but_split_uncertain"],
    }


@app.post("/v1/route")
async def route_decision(request: Request):
    """Classify a turn and return a versioned delegation recommendation."""
    auth_header = request.headers.get("authorization", "")
    if not _client_is_authorized(auth_header):
        return JSONResponse(
            {"error": {"message": "Invalid or missing bearer token", "type": "authentication_error"}},
            status_code=401,
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        body = await request.json()
        messages = _validated_messages(body)
    except (ValueError, json.JSONDecodeError) as exc:
        runtime_metrics["invalid_requests"] += 1
        return JSONResponse(
            {"error": {"message": str(exc), "type": "invalid_request_error"}},
            status_code=400,
        )

    task_type, complexity, latency_ms, reason = await classify(messages)
    recommendation = delegation_recommendation(
        messages, task_type=task_type, complexity=complexity,
    )
    runtime_metrics["delegation_routes_total"] += 1
    runtime_metrics[f"delegation_routes_{recommendation['action']}"] += 1
    return JSONResponse({
        "version": 1,
        "task_type": task_type,
        "complexity": complexity,
        "classification_reason": reason,
        "classify_latency_ms": latency_ms,
        "delegation": recommendation,
    })


@app.get("/healthz")
async def healthz():
    return JSONResponse({"status": "ok"})


async def _readiness_report(http_client: Any, db_path: str) -> dict[str, Any]:
    checks: dict[str, dict[str, Any]] = {}
    probes = {"omniroute": f"{OMNIROUTE_BASE}/models"}
    if LOCAL_CLASSIFIER_ENABLED:
        probes["ollama"] = f"{OLLAMA_BASE}/api/tags"
    for name, url in probes.items():
        try:
            kwargs: dict[str, Any] = {"timeout": 2.0}
            if name == "omniroute":
                kwargs["headers"] = {"Authorization": f"Bearer {OMNIROUTE_API_KEY}"}
            response = await http_client.get(url, **kwargs)
            ok = 200 <= response.status_code < 400
            checks[name] = {"ok": ok, "status_code": response.status_code}
        except Exception as exc:
            checks[name] = {"ok": False, "error": type(exc).__name__}
    try:
        db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=1)
        db.execute("SELECT 1 FROM combos LIMIT 1").fetchone()
        db.close()
        checks["database"] = {"ok": True}
    except sqlite3.Error as exc:
        checks["database"] = {"ok": False, "error": type(exc).__name__}
    ready = all(check["ok"] for check in checks.values())
    return {"status": "ready" if ready else "not_ready", "checks": checks}


@app.get("/readyz")
async def readyz():
    report = await _readiness_report(client, OMNIROUTE_DB_PATH)
    return JSONResponse(report, status_code=200 if report["status"] == "ready" else 503)


@app.get("/status")
async def status():
    total = runtime_metrics["classifications_total"]
    average_latency = (
        runtime_metrics["classification_latency_ms_total"] / total if total else 0.0
    )
    return JSONResponse({
        "metrics": dict(runtime_metrics),
        "decision_log_queue_depth": _log_queue.qsize(),
        "decision_log_queue_capacity": DECISION_LOG_QUEUE_MAX_ENTRIES,
        "classification_cache_entries": len(classification_cache),
        "classification_cache_capacity": CLASSIFICATION_CACHE_MAX_ENTRIES,
        "classification_latency_ms_average": round(average_latency, 2),
    })


def log_decision(entry: dict) -> None:
    try:
        _log_queue.put_nowait(entry)
    except _queue.Full:
        runtime_metrics["decision_logs_dropped"] += 1


def _provider_for_model(model: str) -> str:
    return model.split("/", 1)[0]


def _is_combo_target(model: str) -> bool:
    """True for an OmniRoute combo/pool name rather than a concrete
    "provider/model". Combos carry no provider prefix, so any per-provider
    lookup keyed on _provider_for_model() is meaningless for them."""
    return "/" not in model


def _combo_members(combo_name: str, db_path: str = OMNIROUTE_DB_PATH) -> set[str] | None:
    """Return concrete model IDs for a combo, or None when membership cannot
    be established. Callers handling tool safety treat unknown membership as
    unsafe instead of assuming an opaque pool is compatible."""
    try:
        db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=1)
        row = db.execute("SELECT data FROM combos WHERE name = ? LIMIT 1", (combo_name,)).fetchone()
        db.close()
        if row is None:
            return None
        data = json.loads(row[0])
        models = data.get("models", [])
        members = {
            str(item.get("model"))
            for item in models
            if isinstance(item, dict) and item.get("model")
        }
        return members or None
    except (sqlite3.Error, json.JSONDecodeError, TypeError):
        return None


def _parse_timestamp_ms(value: Any) -> int:
    if value in (None, ""):
        return 0
    try:
        numeric = float(value)
        return int(numeric if numeric > 10_000_000_000 else numeric * 1000)
    except (TypeError, ValueError):
        pass
    try:
        return int(datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp() * 1000)
    except ValueError:
        return 0


def _active_window_start_ms(interval: str, reset_time: str, now_ms: int) -> str:
    """Calculate the current fixed UTC token-limit window."""
    now = datetime.fromtimestamp(now_ms / 1000, tz=timezone.utc)
    try:
        hour, minute = (int(v) for v in (reset_time or "00:00").split(":", 1))
    except (TypeError, ValueError):
        hour, minute = 0, 0
    if interval == "daily":
        start = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if now < start:
            start -= timedelta(days=1)
    elif interval == "weekly":
        start = (now - timedelta(days=now.weekday())).replace(
            hour=hour, minute=minute, second=0, microsecond=0
        )
        if now < start:
            start -= timedelta(days=7)
    else:
        start = now.replace(day=1, hour=hour, minute=minute, second=0, microsecond=0)
        if now < start:
            previous_month_end = start - timedelta(days=1)
            start = previous_month_end.replace(day=1, hour=hour, minute=minute, second=0, microsecond=0)
    return str(int(start.timestamp() * 1000))


def _quota_relevant_to_model(provider: str, model: str, window_key: str) -> bool:
    key = window_key.lower()
    if provider == "antigravity":
        family = "gemini" if "/gemini" in model else "claude" if "/claude" in model else ""
        return not family or family in key or key.startswith("chat_")
    if provider == "github":
        return key in {"chat", "completions", "premium_interactions"}
    return True


def _model_availability(models: list[str]) -> tuple[dict[str, bool], dict[str, str]]:
    """Inspect connection, cooldown, upstream quota, and API-key cap state."""
    now_ms = int(time.time() * 1000)
    availability = {model: True for model in models}
    reasons: dict[str, str] = {}
    try:
        db = sqlite3.connect(f"file:{OMNIROUTE_DB_PATH}?mode=ro", uri=True, timeout=1)
        db.row_factory = sqlite3.Row
        connections = db.execute(
            "SELECT id, provider, is_active, test_status, rate_limited_until FROM provider_connections"
        ).fetchall()
        by_provider: dict[str, list[sqlite3.Row]] = {}
        for row in connections:
            by_provider.setdefault(str(row["provider"]), []).append(row)

        key_row = db.execute("SELECT id FROM api_keys WHERE name = ? LIMIT 1", (OMNIROUTE_API_KEY_NAME,)).fetchone()
        exhausted_caps: set[str] = set()
        if key_row:
            limits = db.execute(
                """SELECT l.scope_type, l.scope_value, l.token_limit,
                          l.reset_interval, l.reset_time, c.window_start,
                          COALESCE(c.tokens_used, 0) AS tokens_used
                   FROM api_key_token_limits l
                   LEFT JOIN api_key_token_counters c ON c.limit_id = l.id
                   WHERE l.api_key_id = ? AND l.enabled = 1""",
                (key_row["id"],),
            ).fetchall()
            for limit in limits:
                expected_window = _active_window_start_ms(
                    str(limit["reset_interval"]), str(limit["reset_time"]), now_ms
                )
                used = int(limit["tokens_used"]) if str(limit["window_start"] or "") == expected_window else 0
                if used >= int(limit["token_limit"]) * API_KEY_CAP_SOFT_STOP_RATIO:
                    exhausted_caps.add(str(limit["scope_value"]) if limit["scope_type"] == "provider" else "*")

        snapshots = db.execute(
            """SELECT provider, connection_id, window_key, remaining_percentage,
                      is_exhausted, next_reset_at
               FROM (
                 SELECT q.*, ROW_NUMBER() OVER (
                   PARTITION BY provider, connection_id, window_key
                   ORDER BY created_at DESC, id DESC
                 ) AS rn
                 FROM quota_snapshots q
               ) WHERE rn = 1"""
        ).fetchall()
        db.close()

        for model in models:
            # Combo/pool targets (a bare name with no "provider/" prefix) are
            # not bound to a single provider_connections row, so the per-
            # provider health checks below cannot resolve them and would skip
            # every pool with "no active non-cooling connection". OmniRoute
            # already rotates a combo's legs and drops rate-limited or
            # degraded ones itself, so availability here is its job, not ours.
            if _is_combo_target(model):
                continue
            provider = _provider_for_model(model)
            if provider in exhausted_caps or "*" in exhausted_caps:
                availability[model] = False
                reasons[model] = "Hermes API-key token limit exhausted"
                continue
            if local_provider_cooldowns.get(provider, 0) > time.monotonic():
                availability[model] = False
                reasons[model] = "preclassifier local cooldown"
                continue
            rows = [r for r in by_provider.get(provider, []) if int(r["is_active"] or 0) == 1]
            usable = [
                r for r in rows
                if str(r["test_status"] or "").lower() not in {"invalid", "expired", "revoked", "auth_error"}
                and _parse_timestamp_ms(r["rate_limited_until"]) <= now_ms
            ]
            if not usable:
                availability[model] = False
                reasons[model] = "no active non-cooling connection"
                continue
            usable_ids = {str(r["id"]) for r in usable}
            relevant = [
                s for s in snapshots
                if s["provider"] == provider
                and str(s["connection_id"]) in usable_ids
                and _quota_relevant_to_model(provider, model, str(s["window_key"]))
                and _parse_timestamp_ms(s["next_reset_at"]) > now_ms
            ]
            if relevant and any(
                int(s["is_exhausted"] or 0) == 1
                or (s["remaining_percentage"] is not None and float(s["remaining_percentage"]) <= QUOTA_EXHAUSTED_THRESHOLD_PERCENT)
                for s in relevant
            ):
                availability[model] = False
                reasons[model] = "upstream quota snapshot exhausted"
    except Exception as exc:
        # Observability must fail open, not become an inference outage.
        for model in models:
            reasons.setdefault(model, f"quota inspection unavailable: {type(exc).__name__}")
    return availability, reasons


def _remember_rate_limit(model: str, response: httpx.Response) -> None:
    if response.status_code != 429:
        return
    try:
        delay = max(LOCAL_COOLDOWN_DEFAULT_S, float(response.headers.get("retry-after", "")))
    except ValueError:
        delay = LOCAL_COOLDOWN_DEFAULT_S
    if _is_combo_target(model):
        # A combo name is not a provider, so cooling it here would only park a
        # dead key in local_provider_cooldowns (the availability pass skips
        # combos entirely). A 429 surfacing from a pool means every leg was
        # rate-limited; OmniRoute already tracks that per leg, and this
        # request still moves on to the next candidate in the chain.
        return
    local_provider_cooldowns[_provider_for_model(model)] = time.monotonic() + min(delay, 3600.0)


async def _close_exception_response(exc: Exception) -> None:
    """Close a partially-created response attached to a transport failure."""
    response = getattr(exc, "response", None)
    if response is not None:
        await response.aclose()


@app.get("/v1/models")
async def list_models():
    now = int(time.time())
    return JSONResponse({
        "object": "list",
        "data": [
            {"id": "auto", "object": "model", "created": now, "owned_by": "preclassifier"},
        ],
    })


@app.get("/v1/models/{model_id}")
async def get_model(model_id: str):
    return JSONResponse({"id": model_id, "object": "model", "created": int(time.time()), "owned_by": "preclassifier"})


def _filter_by_policy(
    ordered: list[str], task_type: str, complexity: str, prompt_tokens: int,
    tool_history: bool, policy_skips: dict[str, str],
    combo_members: Callable[[str], set[str] | None] = _combo_members,
) -> list[str]:
    """Drop candidates that fail size/tool-safety policy, recording why in
    policy_skips (shared dict, so an escalation call can accumulate skip
    reasons from both the original and the escalated chain)."""
    fitting = []
    for model in ordered:
        technical_limit = CAPPED_MODEL_LIMITS.get(model)
        if technical_limit is not None and prompt_tokens > technical_limit - CAPPED_MODEL_SAFETY_MARGIN:
            policy_skips[model] = f"estimated prompt exceeds verified safe limit ({prompt_tokens} tokens)"
            continue
        policy_limit = MODEL_POLICY_PROMPT_LIMITS.get(model)
        if policy_limit is not None and prompt_tokens > policy_limit:
            policy_skips[model] = f"estimated prompt exceeds free-tier policy budget ({prompt_tokens}>{policy_limit})"
            continue
        if model in TOOL_FREE_ONLY_MODELS:
            if task_type != "conversation" or complexity != "simple":
                policy_skips[model] = "model restricted to simple tool-free conversation"
                continue
            if tool_history:
                policy_skips[model] = "existing tool history requires a tool-safe model"
                continue
        if tool_history and _is_combo_target(model):
            members = combo_members(model)
            if members is None:
                policy_skips[model] = "pool membership unavailable for tool-safety check"
                continue
            unsafe_members = members & TOOL_FREE_ONLY_MODELS
            if unsafe_members:
                policy_skips[model] = "pool contains tool-free-only member"
                continue
        fitting.append(model)
    return fitting


def _candidate_chain(
    task_type: str, complexity: str, prompt_tokens: int, tool_history: bool = False
) -> tuple[list[str], dict[str, str]]:
    """Primary pick first, then the rest of that classification's fallback chain
    (primary de-duplicated, order preserved).

    Drops any candidate in CAPPED_MODEL_LIMITS whose real limit the current
    prompt wouldn't fit (with CAPPED_MODEL_SAFETY_MARGIN headroom) - see the
    CAPPED_MODEL_LIMITS comment for why this exists. A capped leg that's
    primary for its (task_type, complexity) is never actually primary in
    practice (DECISION_MATRIX never picks a github/* model), so this filter
    only ever removes fallback legs, never the first choice.

    If every *|simple candidate is filtered out by size/tool-safety policy
    (not cooldown/quota - those are only checked afterward, against whatever
    survives this filter), the prompt itself doesn't fit any simple-tier
    model. Escalate to this task_type's complex chain instead of returning
    empty - see the 2026-09-04 incident where an oversized prompt classified
    reasoning|simple had zero viable candidates and hit a bare 429.
    """
    primary = DECISION_MATRIX[(task_type, complexity)]
    chain = FALLBACK_CHAINS[(task_type, complexity)]
    ordered = [primary] + [m for m in chain if m != primary]
    policy_skips: dict[str, str] = {}
    fitting = _filter_by_policy(ordered, task_type, complexity, prompt_tokens, tool_history, policy_skips)

    escalated = False
    if not fitting and complexity == "simple":
        complex_primary = DECISION_MATRIX[(task_type, "complex")]
        complex_chain = FALLBACK_CHAINS[(task_type, "complex")]
        complex_ordered = [complex_primary] + [m for m in complex_chain if m != complex_primary]
        fitting = _filter_by_policy(complex_ordered, task_type, "complex", prompt_tokens, tool_history, policy_skips)
        escalated = bool(fitting)

    availability, reasons = _model_availability(fitting)
    available = [model for model in fitting if availability.get(model, True)]
    unavailable = {
        model: reasons[model] for model in fitting if not availability.get(model, True)
    }
    result_skips = {**policy_skips, **unavailable}
    if escalated:
        result_skips["_note"] = "escalated to complex chain: prompt exceeds every simple-tier budget"
    return available[:MAX_FORWARD_ATTEMPTS], result_skips


def _delegation_metadata_from_headers(headers: Any) -> dict[str, Any] | None:
    """Validate the bounded Hermes delegation fields before durable logging."""
    if headers.get("x-hermes-delegation-contract", "") != "1":
        return None
    action = headers.get("x-hermes-delegation-action", "")
    if action not in {"avoid", "consider", "require"}:
        return None
    try:
        score = float(headers.get("x-hermes-delegation-score", ""))
        children = int(headers.get("x-hermes-delegation-children", ""))
    except (TypeError, ValueError):
        return None
    if not 0 <= score <= 1 or not 0 <= children <= 10:
        return None
    return {
        "contract": 1,
        "action": action,
        "score": round(score, 2),
        "recommended_children": children,
    }


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    request_id = str(uuid.uuid4())
    auth_header = request.headers.get("authorization", "")
    if not _client_is_authorized(auth_header):
        return JSONResponse(
            {"error": {"message": "Invalid or missing bearer token", "type": "authentication_error"}},
            status_code=401,
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        body = await request.json()
        messages = _validated_messages(body)
    except (ValueError, json.JSONDecodeError) as exc:
        runtime_metrics["invalid_requests"] += 1
        return JSONResponse(
            {"error": {"message": str(exc), "type": "invalid_request_error"}},
            status_code=400,
        )
    req_start = time.monotonic()
    delegation_metadata = _delegation_metadata_from_headers(request.headers)

    task_type, complexity, classify_latency_ms, reason = await classify(messages)
    prompt_tokens_estimate = _estimate_request_tokens(body)
    task_type, complexity, size_note = _guard_request_size(
        task_type, complexity, prompt_tokens_estimate
    )
    reason += size_note
    has_tool_context = _has_tool_context(body, messages)
    candidates, skipped = _candidate_chain(
        task_type, complexity, prompt_tokens_estimate, tool_history=has_tool_context
    )

    stream = bool(body.get("stream"))
    force_no_cache = (
        request.headers.get("x-omniroute-no-cache", "").strip().lower() == "true"
        or has_tool_context
    )

    def do_log(model: str, attempts: int, total_latency_ms: int, response_code: int) -> None:
        log_decision({
            "time": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + f".{int(time.time()*1000)%1000:03d}Z",
            "request_id": request_id,
            "task_type": task_type,
            "complexity": complexity,
            "selected_model": model,
            "attempts": attempts,
            "classify_latency_ms": classify_latency_ms,
            "total_latency_ms": total_latency_ms,
            "reason": reason,
            "response_code": response_code,
            "candidates": candidates,
            "skipped": skipped,
            "reasoning_effort": _selected_effort(body, model, task_type, complexity),
            "delegation": delegation_metadata,
        })

    if not candidates:
        do_log("none", 0, int((time.monotonic() - req_start) * 1000), 429)
        return JSONResponse(
            {"error": {"message": "No provider currently has usable quota/cooldown state", "type": "provider_capacity"}},
            status_code=429,
        )

    if stream:
        # Streaming can't be retried once bytes have gone out, so only retry
        # the pre-stream connect/first-response phase across candidates.
        # A 400 is never in FALLBACK_STATUS_CODES (it fails identically on
        # every model in general), except a context-length-exceeded-shaped
        # one, which is model-specific - so a 400's body has to be read (it's
        # always a small error payload, safe to buffer) before deciding.
        last_status = 599
        for attempt, model in enumerate(candidates, start=1):
            prebuffered_body = b""
            upstream_resp = None
            forward_body = _prepare_forward_body(body, model, task_type, complexity)
            upstream_req = client.build_request(
                "POST", f"{OMNIROUTE_BASE}/chat/completions",
                headers=_upstream_headers(forward_body, force_no_cache),
                json=forward_body,
            )
            is_last = attempt == len(candidates)
            try:
                upstream_resp = await client.send(upstream_req, stream=True)
                last_status = upstream_resp.status_code
                _remember_rate_limit(model, upstream_resp)
                if last_status == 400 and not is_last:
                    prebuffered_body = await upstream_resp.aread()
                    if _is_context_length_exceeded_body(last_status, prebuffered_body.decode("utf-8", "replace")):
                        await upstream_resp.aclose()
                        continue
                    chosen_model, attempts_used = model, attempt
                    break
                if last_status not in FALLBACK_STATUS_CODES or is_last:
                    chosen_model, attempts_used = model, attempt
                    break
                await upstream_resp.aclose()
            except httpx.TransportError as exc:
                if upstream_resp is not None:
                    await upstream_resp.aclose()
                await _close_exception_response(exc)
                if not is_last:
                    continue
                do_log(model, attempt, int((time.monotonic() - req_start) * 1000), 502)
                return JSONResponse(
                    {"error": {"message": "All upstream candidates failed to connect", "type": "upstream_transport_error"}},
                    status_code=502,
                )

        async def gen():
            try:
                if prebuffered_body:
                    yield prebuffered_body
                else:
                    async for chunk in upstream_resp.aiter_bytes():
                        yield chunk
            finally:
                await upstream_resp.aclose()
                do_log(chosen_model, attempts_used, int((time.monotonic() - req_start) * 1000), last_status)

        return StreamingResponse(gen(), status_code=upstream_resp.status_code,
                                  media_type=upstream_resp.headers.get("content-type", "text/event-stream"))

    resp = None
    for attempt, model in enumerate(candidates, start=1):
        forward_body = _prepare_forward_body(body, model, task_type, complexity)
        try:
            resp = await client.post(
                f"{OMNIROUTE_BASE}/chat/completions",
                headers=_upstream_headers(forward_body, force_no_cache),
                json=forward_body,
            )
        except httpx.TransportError as exc:
            await _close_exception_response(exc)
            if attempt < len(candidates):
                continue
            do_log(model, attempt, int((time.monotonic() - req_start) * 1000), 502)
            return JSONResponse(
                {"error": {"message": "All upstream candidates failed to connect", "type": "upstream_transport_error"}},
                status_code=502,
            )
        _remember_rate_limit(model, resp)
        is_last = attempt == len(candidates)
        if resp.status_code == 400 and not is_last and _is_context_length_exceeded_body(resp.status_code, resp.text):
            continue
        if resp.status_code not in FALLBACK_STATUS_CODES or is_last:
            chosen_model, attempts_used = model, attempt
            break

    do_log(chosen_model, attempts_used, int((time.monotonic() - req_start) * 1000), resp.status_code)
    return JSONResponse(resp.json(), status_code=resp.status_code)
