import asyncio
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
import queue
import httpx
from pathlib import Path

os.environ.setdefault("OMNIROUTE_API_KEY", "test-only")
os.environ.setdefault("CLIENT_API_KEYS", "mac-test-token,windows-test-token")

import app
from benchmark_cases import CASES
from challenge_cases import CHALLENGE_CASES
from expanded_cases import EXPANDED_CASES


class ClassificationCacheTests(unittest.TestCase):
    def test_cache_key_includes_recent_context(self):
        first = [
            {"role": "assistant", "content": "I updated the React panel."},
            {"role": "user", "content": "Fix it."},
        ]
        second = [
            {"role": "assistant", "content": "I explained the tax rule."},
            {"role": "user", "content": "Fix it."},
        ]

        self.assertNotEqual(
            app._classification_cache_key(first),
            app._classification_cache_key(second),
        )

    def test_cache_is_bounded_and_evicts_oldest_entry(self):
        cache = app.ClassificationCache(max_entries=2, ttl_seconds=300)
        cache.put("first", "coding", "simple")
        cache.put("second", "reasoning", "simple")
        cache.put("third", "conversation", "simple")

        self.assertIsNone(cache.get("first"))
        self.assertEqual(cache.get("second"), ("reasoning", "simple"))
        self.assertEqual(cache.get("third"), ("conversation", "simple"))


class ClassificationDeadlineTests(unittest.IsolatedAsyncioTestCase):
    async def test_local_classifier_is_opt_in_by_default(self):
        env = os.environ.copy()
        env.pop("LOCAL_CLASSIFIER_ENABLED", None)
        env["OMNIROUTE_API_KEY"] = "test-only"
        result = subprocess.run(
            [sys.executable, "-c", "import app; print(app.LOCAL_CLASSIFIER_ENABLED)"],
            cwd=Path(__file__).resolve().parents[1],
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(result.stdout.strip(), "False")

    async def test_total_deadline_includes_waiting_for_classifier_slot(self):
        old_semaphore = app.classifier_semaphore
        old_cache = app.classification_cache
        old_timeout = getattr(app, "CLASSIFY_TOTAL_TIMEOUT_S", None)
        app.classifier_semaphore = asyncio.Semaphore(0)
        app.classification_cache = app.ClassificationCache(8, 300)
        app.CLASSIFY_TOTAL_TIMEOUT_S = 0.02
        started = time.monotonic()
        try:
            task_type, complexity, _, reason = await asyncio.wait_for(
                app.classify([
                    {"role": "user", "content": "Could you help me understand mutexes?"},
                ]),
                timeout=0.2,
            )
        finally:
            app.classifier_semaphore = old_semaphore
            app.classification_cache = old_cache
            if old_timeout is None:
                delattr(app, "CLASSIFY_TOTAL_TIMEOUT_S")
            else:
                app.CLASSIFY_TOTAL_TIMEOUT_S = old_timeout

        self.assertEqual((task_type, complexity), ("reasoning", "simple"))
        self.assertTrue(reason.startswith("fallback_to_heuristic: total_timeout"))
        self.assertLess(time.monotonic() - started, 0.15)

    async def test_obvious_request_uses_fast_path_without_local_model(self):
        class NoLocalModelClient:
            async def post(self, *args, **kwargs):
                raise AssertionError("local model should not be called")

        old_client = app.client
        old_cache = app.classification_cache
        app.client = NoLocalModelClient()
        app.classification_cache = app.ClassificationCache(8, 300)
        try:
            task_type, complexity, latency_ms, reason = await app.classify([
                {"role": "user", "content": "Explain DNS in two sentences."},
            ])
        finally:
            app.client = old_client
            app.classification_cache = old_cache

        self.assertEqual((task_type, complexity), ("reasoning", "simple"))
        self.assertEqual(reason, "classified_fast_path")
        self.assertLess(latency_ms, 20)

    async def test_ambiguous_local_classifications_are_serialized(self):
        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {"message": {"content": '{"task_type":"reasoning","complexity":"simple"}'}}

        class TrackingClient:
            def __init__(self):
                self.active = 0
                self.max_active = 0

            async def post(self, *args, **kwargs):
                self.active += 1
                self.max_active = max(self.max_active, self.active)
                await asyncio.sleep(0.02)
                self.active -= 1
                return Response()

        old_client = app.client
        old_cache = app.classification_cache
        tracking_client = TrackingClient()
        app.client = tracking_client
        app.classification_cache = app.ClassificationCache(8, 300)
        try:
            await asyncio.gather(*(
                app.classify([{
                    "role": "user",
                    "content": f"Could you help me make sense of mutex scenario {index}?",
                }])
                for index in range(3)
            ))
        finally:
            app.client = old_client
            app.classification_cache = old_cache

        self.assertEqual(tracking_client.max_active, 1)

    async def test_disabled_local_classifier_uses_heuristic_without_inference(self):
        class NoLocalModelClient:
            async def post(self, *args, **kwargs):
                raise AssertionError("disabled local classifier must not run")

        old_enabled = app.LOCAL_CLASSIFIER_ENABLED
        old_client = app.client
        old_cache = app.classification_cache
        app.LOCAL_CLASSIFIER_ENABLED = False
        app.client = NoLocalModelClient()
        app.classification_cache = app.ClassificationCache(8, 300)
        try:
            task_type, complexity, latency_ms, reason = await app.classify([
                {"role": "user", "content": "Could you help me make sense of mutexes?"},
            ])
        finally:
            app.LOCAL_CLASSIFIER_ENABLED = old_enabled
            app.client = old_client
            app.classification_cache = old_cache

        self.assertEqual((task_type, complexity), ("reasoning", "simple"))
        self.assertEqual(reason, "classified_heuristic_primary")
        self.assertLess(latency_ms, 100)


class HeuristicQualityTests(unittest.TestCase):
    def test_semantic_challenge_corpus_has_no_critical_underroutes(self):
        correct = 0
        critical_underroutes = []
        wrong = []
        for case_id, expected_task, expected_complexity, messages in CHALLENGE_CASES:
            actual_task, actual_complexity = app.heuristic_classification(messages)
            if (actual_task, actual_complexity) == (expected_task, expected_complexity):
                correct += 1
            else:
                wrong.append((
                    case_id,
                    (expected_task, expected_complexity),
                    (actual_task, actual_complexity),
                ))
            if expected_complexity == "complex" and actual_complexity == "simple":
                critical_underroutes.append(case_id)

        self.assertEqual(critical_underroutes, [])
        self.assertGreaterEqual(correct / len(CHALLENGE_CASES), 0.95, wrong)

    def test_expanded_corpus_has_at_least_two_hundred_correct_cases(self):
        self.assertGreaterEqual(len(EXPANDED_CASES), 200)
        wrong = []
        for case_id, expected_task, expected_complexity, messages in EXPANDED_CASES:
            actual = app.heuristic_classification(messages)
            if actual != (expected_task, expected_complexity):
                wrong.append((case_id, (expected_task, expected_complexity), actual))
        self.assertEqual(wrong, [])

    def test_fallback_heuristic_scores_at_least_ninety_six_percent(self):
        results = []
        for case_id, expected_task, expected_complexity, messages in CASES:
            got_task, got_complexity = app.heuristic_classification(messages)
            results.append((
                case_id,
                (expected_task, expected_complexity),
                (got_task, got_complexity),
            ))

        wrong = [row for row in results if row[1] != row[2]]
        accuracy = (len(results) - len(wrong)) / len(results)
        self.assertGreaterEqual(accuracy, 0.96, wrong)


class DelegationPolicyTests(unittest.TestCase):
    def test_trivial_self_contained_work_avoids_delegation(self):
        decision = app.delegation_recommendation(
            [{"role": "user", "content": "Fix the typo in README.md."}],
            task_type="coding",
            complexity="simple",
        )

        self.assertEqual(decision["action"], "avoid")
        self.assertEqual(decision["recommended_children"], 0)
        self.assertFalse(decision["parallelizable"])

    def test_explicit_parallel_request_requires_delegation(self):
        decision = app.delegation_recommendation(
            [{"role": "user", "content": "Use three agents in parallel to audit the API, database, and deployment."}],
            task_type="agentic-tool-use",
            complexity="complex",
        )

        self.assertEqual(decision["action"], "require")
        self.assertEqual(decision["recommended_children"], 3)
        self.assertTrue(decision["parallelizable"])
        self.assertIn("explicit_parallel_request", decision["reasons"])

    def test_research_implementation_and_verification_requires_delegation(self):
        decision = app.delegation_recommendation(
            [{"role": "user", "content": "Research the best library, implement the migration, and independently verify it in production."}],
            task_type="agentic-tool-use",
            complexity="complex",
        )

        self.assertEqual(decision["action"], "require")
        self.assertGreaterEqual(decision["recommended_children"], 2)
        self.assertIn("research_implementation_verification", decision["reasons"])

    def test_tightly_coupled_complex_debugging_is_consider(self):
        decision = app.delegation_recommendation(
            [{"role": "user", "content": "Debug this intermittent state-machine race and fix its root cause."}],
            task_type="coding",
            complexity="complex",
        )

        self.assertEqual(decision["action"], "consider")
        self.assertEqual(decision["recommended_children"], 1)
        self.assertFalse(decision["parallelizable"])

    def test_explicit_no_delegation_overrides_other_signals(self):
        decision = app.delegation_recommendation(
            [{"role": "user", "content": "Do not delegate. Audit the API, database, and deployment yourself."}],
            task_type="agentic-tool-use",
            complexity="complex",
        )

        self.assertEqual(decision["action"], "avoid")
        self.assertEqual(decision["recommended_children"], 0)
        self.assertIn("explicit_no_delegation", decision["reasons"])


class DelegationRouteContractTests(unittest.IsolatedAsyncioTestCase):
    class Request:
        def __init__(self, authorization="Bearer mac-test-token", body=None):
            self.headers = {"authorization": authorization}
            self._body = body or {"messages": [{"role": "user", "content": "Hello"}]}

        async def json(self):
            return self._body

    async def test_route_requires_the_same_bearer_authentication(self):
        for authorization in ("", "Bearer wrong-key", "Basic mac-test-token"):
            with self.subTest(authorization=authorization):
                response = await app.route_decision(self.Request(authorization=authorization))
                self.assertEqual(response.status_code, 401)

    async def test_route_returns_the_versioned_contract(self):
        original_classify = app.classify

        async def classify(_messages):
            return "agentic-tool-use", "complex", 2, "test_classifier"

        app.classify = classify
        try:
            response = await app.route_decision(self.Request(body={
                "messages": [{
                    "role": "user",
                    "content": "Use three agents in parallel to audit the API, database, and deployment.",
                }],
            }))
        finally:
            app.classify = original_classify

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.body)
        self.assertEqual(
            set(payload),
            {"version", "task_type", "complexity", "classification_reason", "classify_latency_ms", "delegation"},
        )
        self.assertEqual(payload["version"], 1)
        self.assertEqual(payload["delegation"]["action"], "require")
        self.assertEqual(
            set(payload["delegation"]),
            {"action", "score", "recommended_children", "parallelizable", "reasons"},
        )
        self.assertGreaterEqual(payload["delegation"]["score"], 0.0)
        self.assertLessEqual(payload["delegation"]["score"], 1.0)


class DelegationMetadataTests(unittest.TestCase):
    def test_valid_hermes_headers_become_bounded_log_metadata(self):
        metadata = app._delegation_metadata_from_headers({
            "x-hermes-delegation-contract": "1",
            "x-hermes-delegation-action": "require",
            "x-hermes-delegation-score": "0.92",
            "x-hermes-delegation-children": "3",
        })

        self.assertEqual(metadata, {
            "contract": 1,
            "action": "require",
            "score": 0.92,
            "recommended_children": 3,
        })

    def test_invalid_or_unversioned_headers_are_ignored(self):
        cases = [
            {},
            {"x-hermes-delegation-contract": "2", "x-hermes-delegation-action": "require"},
            {
                "x-hermes-delegation-contract": "1",
                "x-hermes-delegation-action": "unknown",
                "x-hermes-delegation-score": "0.5",
                "x-hermes-delegation-children": "2",
            },
            {
                "x-hermes-delegation-contract": "1",
                "x-hermes-delegation-action": "require",
                "x-hermes-delegation-score": "9",
                "x-hermes-delegation-children": "99",
            },
        ]

        for headers in cases:
            with self.subTest(headers=headers):
                self.assertIsNone(app._delegation_metadata_from_headers(headers))


class DelegationPolicyCorpusTests(unittest.TestCase):
    CASES = [
        ("hello", "avoid"),
        ("Thanks, that is done.", "avoid"),
        ("Explain DNS in two sentences.", "avoid"),
        ("Fix the typo in README.md.", "avoid"),
        ("Check whether nginx is running.", "avoid"),
        ("Write one unit test for this helper.", "avoid"),
        ("Inspect this one configuration file.", "avoid"),
        ("Update one timeout value in config.yaml.", "avoid"),
        ("What do you think about this approach?", "avoid"),
        ("Do not delegate; audit the whole VPS yourself.", "avoid"),
        ("Debug this intermittent state-machine race and fix its root cause.", "consider"),
        ("Implement the authentication migration with rollback support.", "consider"),
        ("Refactor this state machine end-to-end.", "consider"),
        ("Analyze the architecture tradeoffs for a multi-tenant API.", "consider"),
        ("Fix this memory leak and add regression coverage.", "consider"),
        ("Migrate this service across a major incompatible version.", "consider"),
        ("Investigate the production timeout, implement a fix, and test it.", "consider"),
        ("Fix the contract mismatch between the frontend and backend.", "avoid"),
        ("Use three agents in parallel to audit the API, database, and deployment.", "require"),
        ("Delegate separate reviews of the API and database.", "require"),
        ("Parallelize the research across multiple agents.", "require"),
        ("Split this work across four subagents.", "require"),
        ("Research the best library, implement the migration, and independently verify it.", "require"),
        ("Audit the API, database, and deployment for reliability problems.", "require"),
        ("Audit the entire VPS for security and performance issues.", "require"),
        ("Make this work on macOS and Windows.", "require"),
        ("Apply the coordinated change across multiple repositories.", "require"),
        ("Review the production authorization change and independently verify it.", "require"),
        ("Run a security audit and get a second review before deployment.", "require"),
        ("Build the macOS and Windows clients and verify both.", "require"),
    ]

    def test_policy_matches_labeled_corpus(self):
        wrong = []
        counts = {"avoid": 0, "consider": 0, "require": 0}
        for prompt, expected in self.CASES:
            messages = [{"role": "user", "content": prompt}]
            task_type, complexity = app.heuristic_classification(messages)
            actual = app.delegation_recommendation(
                messages, task_type=task_type, complexity=complexity,
            )["action"]
            counts[actual] += 1
            if actual != expected:
                wrong.append((prompt, expected, actual, task_type, complexity))

        self.assertEqual(wrong, [])
        self.assertEqual(sum(counts.values()), len(self.CASES))


class DecisionLogQueueTests(unittest.TestCase):
    def test_decision_log_rotation_bounds_files_and_preserves_json(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = os.path.join(tmp_dir, "decisions.log")
            for index in range(12):
                app._append_decision_log(
                    {"request_id": index, "payload": "x" * 80},
                    path=log_path,
                    max_bytes=300,
                    backup_count=2,
                )

            files = sorted(Path(tmp_dir).glob("decisions.log*"))
            self.assertEqual([path.name for path in files], [
                "decisions.log", "decisions.log.1", "decisions.log.2",
            ])
            for path in files:
                self.assertLessEqual(path.stat().st_size, 300)
                for line in path.read_text(encoding="utf-8").splitlines():
                    json.loads(line)

    def test_full_log_queue_drops_entry_without_blocking_request(self):
        old_queue = app._log_queue
        old_dropped = app.runtime_metrics.get("decision_logs_dropped", 0)
        app._log_queue = queue.Queue(maxsize=1)
        app.runtime_metrics["decision_logs_dropped"] = 0
        try:
            app.log_decision({"request_id": "first"})
            app.log_decision({"request_id": "second"})
            self.assertEqual(app._log_queue.qsize(), 1)
            self.assertEqual(app.runtime_metrics["decision_logs_dropped"], 1)
        finally:
            app._log_queue = old_queue
            app.runtime_metrics["decision_logs_dropped"] = old_dropped


class PoolSafetyTests(unittest.TestCase):
    def test_retired_github_models_are_not_routing_candidates(self):
        candidates = {
            model
            for chain in app.FALLBACK_CHAINS.values()
            for model in chain
        }

        self.assertFalse(
            any(model.startswith("github/") for model in candidates),
            candidates,
        )

    def test_tool_history_rejects_pool_containing_tool_free_member(self):
        with tempfile.NamedTemporaryFile(suffix=".sqlite") as db_file:
            db = sqlite3.connect(db_file.name)
            db.execute("CREATE TABLE combos (name TEXT NOT NULL, data TEXT NOT NULL)")
            db.execute(
                "INSERT INTO combos(name, data) VALUES (?, ?)",
                (
                    "mixed-pool",
                    json.dumps({
                        "models": [
                            {"model": "safe/tool-model"},
                            {"model": "cloudflare-ai/@cf/openai/gpt-oss-20b"},
                        ]
                    }),
                ),
            )
            db.commit()
            db.close()

            members = app._combo_members("mixed-pool", db_file.name)
            skips = {}
            fitting = app._filter_by_policy(
                ["mixed-pool"], "conversation", "simple", 10, True, skips,
                combo_members=lambda _: members,
            )

        self.assertEqual(fitting, [])
        self.assertIn("tool-free-only member", skips["mixed-pool"])

    def test_fresh_tool_schema_rejects_pool_containing_tool_free_member(self):
        body = {
            "messages": [{"role": "user", "content": "What time is it?"}],
            "tools": [{
                "type": "function",
                "function": {"name": "clock", "parameters": {"type": "object"}},
            }],
        }
        skips = {}

        fitting = app._filter_by_policy(
            ["mixed-pool"], "conversation", "simple", 10,
            app._has_tool_context(body, body["messages"]), skips,
            combo_members=lambda _: {
                "safe/tool-model",
                "cloudflare-ai/@cf/openai/gpt-oss-20b",
            },
        )

        self.assertEqual(fitting, [])
        self.assertIn("tool-free-only member", skips["mixed-pool"])


class ContextBudgetTests(unittest.TestCase):
    def test_estimate_counts_tool_schemas_arguments_and_non_text_blocks(self):
        payload = "x" * 40_000
        bodies = {
            "tool_schema": {
                "messages": [{"role": "user", "content": "Hi"}],
                "tools": [{"type": "function", "function": {
                    "name": "large", "description": payload,
                    "parameters": {"type": "object"},
                }}],
            },
            "tool_arguments": {
                "messages": [{"role": "assistant", "content": None, "tool_calls": [{
                    "id": "call_1", "type": "function",
                    "function": {"name": "large", "arguments": payload},
                }]}],
            },
            "image_block": {
                "messages": [{"role": "user", "content": [{
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64," + payload},
                }]}],
            },
        }

        for name, body in bodies.items():
            with self.subTest(name=name):
                self.assertGreater(app._estimate_request_tokens(body), 8_000)

    def test_complete_request_size_escalates_simple_classification(self):
        payload = "x" * 36_000
        bodies = (
            {
                "messages": [{"role": "user", "content": "Hi"}],
                "tools": [{"type": "function", "function": {
                    "name": "large", "description": payload,
                    "parameters": {"type": "object"},
                }}],
            },
            {
                "messages": [{"role": "assistant", "content": None, "tool_calls": [{
                    "id": "call_1", "type": "function",
                    "function": {"name": "large", "arguments": payload},
                }]}],
            },
        )

        for body in bodies:
            with self.subTest(body_fields=tuple(body)):
                task_type, complexity, note = app._guard_request_size(
                    "conversation", "simple", app._estimate_request_tokens(body)
                )
                self.assertEqual((task_type, complexity), ("conversation", "complex"))
                self.assertIn("complete_request_forced_complex", note)


class RequestValidationTests(unittest.TestCase):
    def test_rejects_missing_or_empty_messages(self):
        for body in ({}, {"messages": []}, {"messages": "hello"}):
            with self.subTest(body=body):
                with self.assertRaisesRegex(ValueError, "messages"):
                    app._validated_messages(body)

    def test_rejects_message_without_valid_role_or_content(self):
        invalid = [
            {"messages": [{"role": "root", "content": "hello"}]},
            {"messages": [{"role": "user"}]},
            {"messages": ["hello"]},
        ]
        for body in invalid:
            with self.subTest(body=body):
                with self.assertRaises(ValueError):
                    app._validated_messages(body)


class AuthorizationTests(unittest.IsolatedAsyncioTestCase):
    class Request:
        def __init__(self, authorization=None):
            self.headers = {}
            if authorization is not None:
                self.headers["authorization"] = authorization

        async def json(self):
            return {"messages": [{"role": "user", "content": "Hello"}]}

    async def test_chat_completions_rejects_missing_or_invalid_bearer_key(self):
        for authorization in (None, "Bearer wrong-key", "Basic test-only", "Bearer"):
            with self.subTest(authorization=authorization):
                response = await app.chat_completions(self.Request(authorization))
                self.assertEqual(response.status_code, 401)

    async def test_chat_completions_accepts_each_configured_client_key(self):
        original_classify = app.classify

        async def stop_after_auth(_messages):
            raise RuntimeError("authorization accepted")

        app.classify = stop_after_auth
        try:
            for token in ("mac-test-token", "windows-test-token"):
                with self.subTest(token=token):
                    with self.assertRaisesRegex(RuntimeError, "authorization accepted"):
                        await app.chat_completions(self.Request(f"Bearer {token}"))
        finally:
            app.classify = original_classify

    async def test_upstream_omniroute_key_is_not_implicitly_a_client_key(self):
        response = await app.chat_completions(self.Request("Bearer test-only"))

        self.assertEqual(response.status_code, 401)
        self.assertNotIn("test-only", response.body.decode())
        self.assertNotIn("mac-test-token", response.body.decode())
        self.assertNotIn("windows-test-token", response.body.decode())

    def test_upstream_auth_uses_internal_key_not_device_key(self):
        headers = app._upstream_headers(
            {"messages": [{"role": "user", "content": "Hello"}]},
            False,
        )

        self.assertEqual(headers["Authorization"], "Bearer test-only")
        self.assertNotIn("mac-test-token", headers["Authorization"])

class ReadinessTests(unittest.IsolatedAsyncioTestCase):
    async def test_readiness_reports_each_failed_dependency(self):
        class Response:
            def __init__(self, status_code):
                self.status_code = status_code

        class Client:
            async def get(self, url, **kwargs):
                if "ollama" in url:
                    raise OSError("connection refused")
                return Response(200)

        report = await app._readiness_report(Client(), "/tmp/no-such-omniroute.sqlite")

        self.assertEqual(report["status"], "not_ready")
        self.assertFalse(report["checks"]["ollama"]["ok"])
        self.assertTrue(report["checks"]["omniroute"]["ok"])
        self.assertFalse(report["checks"]["database"]["ok"])

    async def test_readiness_rejects_omniroute_auth_failures(self):
        class Response:
            def __init__(self, status_code):
                self.status_code = status_code

        class Client:
            def __init__(self, omniroute_status):
                self.omniroute_status = omniroute_status

            async def get(self, url, **kwargs):
                return Response(self.omniroute_status if "omniroute" in url else 200)

        with tempfile.NamedTemporaryFile(suffix=".sqlite") as db_file:
            db = sqlite3.connect(db_file.name)
            db.execute("CREATE TABLE combos (name TEXT NOT NULL, data TEXT NOT NULL)")
            db.execute("INSERT INTO combos VALUES ('pool', '{}')")
            db.commit()
            db.close()
            for status_code in (401, 403):
                with self.subTest(status_code=status_code):
                    report = await app._readiness_report(Client(status_code), db_file.name)
                    self.assertEqual(report["status"], "not_ready")
                    self.assertFalse(report["checks"]["omniroute"]["ok"])

    async def test_readiness_skips_ollama_when_local_classifier_is_disabled(self):
        class Response:
            status_code = 200

        class Client:
            async def get(self, url, **kwargs):
                if "ollama" in url:
                    raise AssertionError("disabled dependency must not be probed")
                return Response()

        old_enabled = app.LOCAL_CLASSIFIER_ENABLED
        app.LOCAL_CLASSIFIER_ENABLED = False
        try:
            with tempfile.NamedTemporaryFile(suffix=".sqlite") as db_file:
                db = sqlite3.connect(db_file.name)
                db.execute("CREATE TABLE combos (name TEXT NOT NULL, data TEXT NOT NULL)")
                db.execute("INSERT INTO combos VALUES ('pool', '{}')")
                db.commit()
                db.close()
                report = await app._readiness_report(Client(), db_file.name)
        finally:
            app.LOCAL_CLASSIFIER_ENABLED = old_enabled

        self.assertEqual(report["status"], "ready")
        self.assertNotIn("ollama", report["checks"])


class RuntimeMetricsTests(unittest.IsolatedAsyncioTestCase):
    async def test_classification_path_counters_are_recorded(self):
        old_cache = app.classification_cache
        old_total = app.runtime_metrics.get("classifications_total", 0)
        old_fast = app.runtime_metrics.get("classifications_fast_path", 0)
        app.classification_cache = app.ClassificationCache(8, 300)
        app.runtime_metrics["classifications_total"] = 0
        app.runtime_metrics["classifications_fast_path"] = 0
        try:
            await app.classify([{"role": "user", "content": "What is the capital of Japan?"}])
            self.assertEqual(app.runtime_metrics["classifications_total"], 1)
            self.assertEqual(app.runtime_metrics["classifications_fast_path"], 1)
        finally:
            app.classification_cache = old_cache
            app.runtime_metrics["classifications_total"] = old_total
            app.runtime_metrics["classifications_fast_path"] = old_fast

    async def test_status_exposes_queue_cache_and_average_latency(self):
        response = await app.status()
        payload = json.loads(response.body)

        self.assertIn("metrics", payload)
        self.assertIn("decision_log_queue_depth", payload)
        self.assertIn("classification_cache_entries", payload)
        self.assertIn("classification_latency_ms_average", payload)


class ReasoningEffortPolicyTests(unittest.TestCase):
    def test_claude_family_effort_is_capped_at_medium(self):
        for model in (
            "claude/claude-sonnet-4-6",
            "antigravity/claude-sonnet-4-6",
            "antigravity/claude-opus-4-6-thinking",
        ):
            with self.subTest(model=model):
                body = app._prepare_forward_body(
                    {"messages": [], "reasoning_effort": "high"},
                    model,
                    "coding",
                    "complex",
                )
                self.assertEqual(body["reasoning_effort"], "medium")

    def test_pool_containing_claude_is_capped_at_medium(self):
        body = app._prepare_forward_body(
            {"messages": [], "reasoning_effort": "high"},
            "pool-reasoning-complex",
            "reasoning",
            "complex",
        )
        self.assertEqual(body["reasoning_effort"], "medium")

    def test_codex_complex_work_retains_high_effort(self):
        body = app._prepare_forward_body(
            {"messages": [], "reasoning_effort": "medium"},
            "codex/gpt-5.6-terra",
            "agentic-tool-use",
            "complex",
        )
        self.assertEqual(body["reasoning_effort"], "high")

    def test_effort_scales_with_classified_complexity(self):
        simple = app._prepare_forward_body(
            {"messages": [], "reasoning_effort": "medium"},
            "pool-coding-simple",
            "coding",
            "simple",
        )
        complex_body = app._prepare_forward_body(
            {"messages": [], "reasoning_effort": "medium"},
            "pool-coding-complex",
            "coding",
            "complex",
        )

        self.assertEqual(simple["reasoning_effort"], "low")
        self.assertEqual(complex_body["reasoning_effort"], "high")

    def test_complex_reasoning_uses_measured_medium_sweet_spot(self):
        body = app._prepare_forward_body(
            {"messages": [], "reasoning_effort": "medium"},
            "pool-reasoning-complex",
            "reasoning",
            "complex",
        )
        self.assertEqual(body["reasoning_effort"], "medium")

    def test_explicit_nondefault_effort_is_preserved(self):
        body = app._prepare_forward_body(
            {"messages": [], "reasoning_effort": "low"},
            "pool-reasoning-complex",
            "reasoning",
            "complex",
        )
        self.assertEqual(body["reasoning_effort"], "low")


class ForwardingFailureTests(unittest.IsolatedAsyncioTestCase):
    async def test_non_streaming_transport_failure_falls_back_to_next_candidate(self):
        class Request:
            headers = {"authorization": "Bearer mac-test-token"}

            async def json(self):
                return {"messages": [{"role": "user", "content": "Hello"}]}

        class Response:
            status_code = 200
            text = '{"id":"ok"}'
            headers = {}

            def json(self):
                return {"id": "ok"}

        class Client:
            def __init__(self):
                self.calls = 0

            async def post(self, *args, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    raise httpx.ConnectError("first candidate unavailable")
                return Response()

        async def classify(messages):
            return "conversation", "simple", 0, "test"

        fake_client = Client()
        old_client = app.client
        old_classify = app.classify
        old_candidate_chain = app._candidate_chain
        app.client = fake_client
        app.classify = classify
        app._candidate_chain = lambda *args, **kwargs: (["safe/one", "safe/two"], {})
        try:
            response = await app.chat_completions(Request())
        finally:
            app.client = old_client
            app.classify = old_classify
            app._candidate_chain = old_candidate_chain

        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.body), {"id": "ok"})
        self.assertEqual(fake_client.calls, 2)

    async def test_streaming_transport_failure_falls_back_to_next_candidate(self):
        class Request:
            headers = {"authorization": "Bearer mac-test-token"}

            async def json(self):
                return {
                    "messages": [{"role": "user", "content": "Hello"}],
                    "stream": True,
                }

        class Response:
            status_code = 200
            headers = {"content-type": "text/event-stream"}

            def __init__(self):
                self.closed = False

            async def aiter_bytes(self):
                yield b"data: done\n\n"

            async def aclose(self):
                self.closed = True

        class Client:
            def __init__(self):
                self.calls = 0
                self.response = Response()

            def build_request(self, *args, **kwargs):
                return kwargs["json"]["model"]

            async def send(self, request, stream=False):
                self.calls += 1
                if self.calls == 1:
                    raise httpx.ReadTimeout("first candidate timed out")
                return self.response

        async def classify(messages):
            return "conversation", "simple", 0, "test"

        fake_client = Client()
        old_client = app.client
        old_classify = app.classify
        old_candidate_chain = app._candidate_chain
        app.client = fake_client
        app.classify = classify
        app._candidate_chain = lambda *args, **kwargs: (["safe/one", "safe/two"], {})
        try:
            response = await app.chat_completions(Request())
            chunks = [chunk async for chunk in response.body_iterator]
        finally:
            app.client = old_client
            app.classify = old_classify
            app._candidate_chain = old_candidate_chain

        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(chunks), b"data: done\n\n")
        self.assertEqual(fake_client.calls, 2)
        self.assertTrue(fake_client.response.closed)

    async def test_streaming_protocol_failure_closes_response_and_falls_back(self):
        class Request:
            headers = {"authorization": "Bearer mac-test-token"}

            async def json(self):
                return {
                    "messages": [{"role": "user", "content": "Hello"}],
                    "stream": True,
                }

        class BrokenResponse:
            status_code = 400
            headers = {"content-type": "application/json"}

            def __init__(self):
                self.closed = False

            async def aread(self):
                raise httpx.RemoteProtocolError("truncated error response")

            async def aclose(self):
                self.closed = True

        class GoodResponse:
            status_code = 200
            headers = {"content-type": "text/event-stream"}

            async def aiter_bytes(self):
                yield b"data: recovered\n\n"

            async def aclose(self):
                return None

        class Client:
            def __init__(self):
                self.responses = [BrokenResponse(), GoodResponse()]
                self.calls = 0

            def build_request(self, *args, **kwargs):
                return kwargs["json"]["model"]

            async def send(self, request, stream=False):
                response = self.responses[self.calls]
                self.calls += 1
                return response

        async def classify(messages):
            return "conversation", "simple", 0, "test"

        fake_client = Client()
        old_client = app.client
        old_classify = app.classify
        old_candidate_chain = app._candidate_chain
        app.client = fake_client
        app.classify = classify
        app._candidate_chain = lambda *args, **kwargs: (["safe/one", "safe/two"], {})
        try:
            response = await app.chat_completions(Request())
            chunks = [chunk async for chunk in response.body_iterator]
        finally:
            app.client = old_client
            app.classify = old_classify
            app._candidate_chain = old_candidate_chain

        self.assertEqual(b"".join(chunks), b"data: recovered\n\n")
        self.assertEqual(fake_client.calls, 2)
        self.assertTrue(fake_client.responses[0].closed)


if __name__ == "__main__":
    unittest.main()
