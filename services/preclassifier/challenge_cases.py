"""Independent routing challenge set focused on semantic boundary cases.

Unlike ``expanded_cases.py``, these prompts are not rewrites of the original
38 examples.  They intentionally contain misleading keywords, negation,
context-dependent follow-ups, and mixed action/edit requests.  All examples
are synthetic and contain no production conversation data.
"""

CHALLENGE_CASES = [
    # Conversation: technical words do not automatically make an active task.
    ("chat_technical_thanks", "conversation", "simple", [
        {"role": "user", "content": "Thanks for fixing that production bug. Everything looks good now."},
    ]),
    ("chat_ack_install", "conversation", "simple", [
        {"role": "user", "content": "Okay, the install is finished. Nice work."},
    ]),
    ("chat_ack_code", "conversation", "simple", [
        {"role": "user", "content": "Great, that code change is exactly what I wanted."},
    ]),
    ("chat_no_task", "conversation", "simple", [
        {"role": "user", "content": "Got it. We can revisit the database migration another day."},
    ]),
    ("chat_casual", "conversation", "simple", [
        {"role": "user", "content": "How are you doing today?"},
    ]),
    ("chat_reassurance", "conversation", "simple", [
        {"role": "user", "content": "No worries about the failed test; thank you for trying."},
    ]),
    ("chat_close", "conversation", "simple", [
        {"role": "user", "content": "Perfect. That is all I needed."},
    ]),
    ("chat_pause", "conversation", "simple", [
        {"role": "user", "content": "Let's stop here for now."},
    ]),

    # Complex conversation: nuanced personal support, not analysis or execution.
    ("chat_complex_support", "conversation", "complex", [
        {"role": "user", "content": "I feel overwhelmed after this long outage and need to talk it through with someone."},
    ]),
    ("chat_complex_conflict", "conversation", "complex", [
        {"role": "user", "content": "I'm anxious about a difficult conversation with my cofounder; please help me work through how I feel."},
    ]),
    ("chat_complex_burnout", "conversation", "complex", [
        {"role": "user", "content": "I've been working all day for weeks and feel burned out. Can we talk for a while?"},
    ]),
    ("chat_complex_grief", "conversation", "complex", [
        {"role": "user", "content": "A close friend died and I do not know what to say; I just need a thoughtful conversation."},
    ]),
    ("chat_complex_context", "conversation", "complex", [
        {"role": "user", "content": "This project has become emotionally exhausting."},
        {"role": "assistant", "content": "That sounds like a lot to carry."},
        {"role": "user", "content": "It is. Stay with me and help me unpack that feeling."},
    ]),
    ("chat_complex_decision_emotion", "conversation", "complex", [
        {"role": "user", "content": "I already made the decision, but I am second-guessing myself and need reassurance, not a new plan."},
    ]),
    ("chat_complex_relationship", "conversation", "complex", [
        {"role": "user", "content": "Please listen while I explain a complicated family situation; do not solve it yet."},
    ]),
    ("chat_complex_followup", "conversation", "complex", [
        {"role": "assistant", "content": "We discussed the pressure you are under."},
        {"role": "user", "content": "Can we continue that conversation? It still feels heavy."},
    ]),

    # Coding: distinguish a bounded edit from multi-file or production work.
    ("code_simple_constant", "coding", "simple", [
        {"role": "user", "content": "Change TIMEOUT_SECONDS from 20 to 30 in settings.py."},
    ]),
    ("code_simple_guard", "coding", "simple", [
        {"role": "user", "content": "Add a None check before this function returns user.name."},
    ]),
    ("code_simple_regex", "coding", "simple", [
        {"role": "user", "content": "Correct this regular expression so it accepts a trailing slash."},
    ]),
    ("code_simple_comment", "coding", "simple", [
        {"role": "user", "content": "Replace the outdated comment above parse_url; do not change behavior."},
    ]),
    ("code_simple_json", "coding", "simple", [
        {"role": "user", "content": "Add the missing enabled field to this small JSON example."},
    ]),
    ("code_simple_test", "coding", "simple", [
        {"role": "user", "content": "Write one unit test for parse_date rejecting an empty string."},
    ]),
    ("code_simple_shell", "coding", "simple", [
        {"role": "user", "content": "Make this shell script quote the filename variable."},
    ]),
    ("code_simple_type", "coding", "simple", [
        {"role": "user", "content": "Add a return type annotation to get_user without refactoring it."},
    ]),
    ("code_complex_auth", "coding", "complex", [
        {"role": "user", "content": "Replace session authentication across the API and worker, migrate existing sessions, and add rollback tests."},
    ]),
    ("code_complex_incident", "coding", "complex", [
        {"role": "user", "content": "Find and fix the intermittent duplicate-payment bug under concurrent retries in production."},
    ]),
    ("code_complex_upgrade", "coding", "complex", [
        {"role": "user", "content": "Upgrade the React application to the next major version and adapt every incompatible plugin and test."},
    ]),
    ("code_complex_schema", "coding", "complex", [
        {"role": "user", "content": "Redesign the event schema used by three services while preserving old consumers during rollout."},
    ]),
    ("code_complex_perf", "coding", "complex", [
        {"role": "user", "content": "Profile and eliminate the memory leak spanning the websocket server, queue worker, and cache."},
    ]),
    ("code_complex_security", "coding", "complex", [
        {"role": "user", "content": "Patch the authorization bypass, add regression coverage, and update every affected endpoint."},
    ]),
    ("code_complex_context", "coding", "complex", [
        {"role": "assistant", "content": "The schema change fixed the API but broke the background worker."},
        {"role": "user", "content": "Fix it without reverting the API behavior and verify both paths."},
    ]),
    ("code_complex_migration", "coding", "complex", [
        {"role": "user", "content": "Implement a zero-downtime database migration with dual writes, backfill, monitoring, and rollback."},
    ]),

    # Reasoning: advice and explanation must not be mistaken for execution/editing.
    ("reason_simple_fix_explain", "reasoning", "simple", [
        {"role": "user", "content": "Explain how to fix a typo in a config file, but do not edit anything."},
    ]),
    ("reason_simple_install_advice", "reasoning", "simple", [
        {"role": "user", "content": "Should I install Redis for this tiny application? Just advise me; do not run commands."},
    ]),
    ("reason_simple_code_meaning", "reasoning", "simple", [
        {"role": "user", "content": "What does this Python function do?"},
    ]),
    ("reason_simple_command", "reasoning", "simple", [
        {"role": "user", "content": "What does the docker compose restart command mean?"},
    ]),
    ("reason_simple_concept", "reasoning", "simple", [
        {"role": "user", "content": "Why does DNS caching reduce latency?"},
    ]),
    ("reason_simple_choice", "reasoning", "simple", [
        {"role": "user", "content": "Which is simpler for a small script, JSON or YAML?"},
    ]),
    ("reason_simple_error", "reasoning", "simple", [
        {"role": "user", "content": "Tell me what HTTP status 404 indicates."},
    ]),
    ("reason_simple_summary", "reasoning", "simple", [
        {"role": "user", "content": "Summarize the difference between a process and a thread in three sentences."},
    ]),
    ("reason_complex_architecture", "reasoning", "complex", [
        {"role": "user", "content": "Design and compare three multi-region database strategies, including consistency, recovery, and regulatory tradeoffs; provide analysis only."},
    ]),
    ("reason_complex_security", "reasoning", "complex", [
        {"role": "user", "content": "Threat-model an agent with root tools and untrusted web content, then prioritize layered defenses without changing the server."},
    ]),
    ("reason_complex_incident", "reasoning", "complex", [
        {"role": "user", "content": "Given these timelines and metrics, determine the most likely cause of the outage and defend your conclusion; analysis only."},
    ]),
    ("reason_complex_algorithm", "reasoning", "complex", [
        {"role": "user", "content": "Prove or disprove that this retry algorithm remains live under correlated packet loss and clock drift."},
    ]),
    ("reason_complex_plan", "reasoning", "complex", [
        {"role": "user", "content": "Create a detailed migration plan with risks and rollback criteria, but do not execute or edit anything."},
    ]),
    ("reason_complex_cost", "reasoning", "complex", [
        {"role": "user", "content": "Evaluate model-routing policies using quality, token cost, tail latency, quota exhaustion, and failure recovery."},
    ]),
    ("reason_complex_context", "reasoning", "complex", [
        {"role": "assistant", "content": "Option A is consistent but expensive; option B is eventually consistent."},
        {"role": "user", "content": "Challenge that conclusion using the failure assumptions we discussed."},
    ]),
    ("reason_complex_privacy", "reasoning", "complex", [
        {"role": "user", "content": "Assess privacy and data-retention consequences of sending memory retrievals to several external model providers."},
    ]),

    # Agentic: the requested result requires tools or external state.
    ("agent_simple_disk", "agentic-tool-use", "simple", [
        {"role": "user", "content": "Check the current disk usage on this server and report it."},
    ]),
    ("agent_simple_log", "agentic-tool-use", "simple", [
        {"role": "user", "content": "Show me the last ten lines of the nginx error log."},
    ]),
    ("agent_simple_version", "agentic-tool-use", "simple", [
        {"role": "user", "content": "Find the installed Docker version on this VPS."},
    ]),
    ("agent_simple_health", "agentic-tool-use", "simple", [
        {"role": "user", "content": "Call the local readiness endpoint and tell me its status."},
    ]),
    ("agent_simple_container", "agentic-tool-use", "simple", [
        {"role": "user", "content": "List currently running containers."},
    ]),
    ("agent_simple_search", "agentic-tool-use", "simple", [
        {"role": "user", "content": "Search the repository for references to CLASSIFIER_MODEL."},
    ]),
    ("agent_simple_restart", "agentic-tool-use", "simple", [
        {"role": "user", "content": "Restart the staging worker and confirm it becomes healthy."},
    ]),
    ("agent_simple_download", "agentic-tool-use", "simple", [
        {"role": "user", "content": "Download the latest release notes and save them to /tmp/release-notes.txt."},
    ]),
    ("agent_complex_audit", "agentic-tool-use", "complex", [
        {"role": "user", "content": "Audit the whole VPS, correlate service logs and metrics, fix confirmed faults, then rerun all health checks."},
    ]),
    ("agent_complex_release", "agentic-tool-use", "complex", [
        {"role": "user", "content": "Build the release, migrate the database, deploy every service, run browser tests, and roll back if verification fails."},
    ]),
    ("agent_complex_research", "agentic-tool-use", "complex", [
        {"role": "user", "content": "Research maintained GitHub routing tools, compare their licenses and resource costs, install the best candidate, and benchmark it."},
    ]),
    ("agent_complex_security", "agentic-tool-use", "complex", [
        {"role": "user", "content": "Inspect exposed ports and authentication settings, patch safe findings, preserve access, and verify from outside."},
    ]),
    ("agent_complex_data", "agentic-tool-use", "complex", [
        {"role": "user", "content": "Export the database, validate the backup, restore it into an isolated container, and compare row counts."},
    ]),
    ("agent_complex_context", "agentic-tool-use", "complex", [
        {"role": "assistant", "content": "The deployment succeeded but one health probe is intermittently failing."},
        {"role": "user", "content": "Investigate it, repair the cause, and verify the rollout end to end."},
    ]),
    ("agent_complex_integrate", "agentic-tool-use", "complex", [
        {"role": "user", "content": "Connect the new provider, test authentication and streaming, update routing, and monitor the first production requests."},
    ]),
    ("agent_complex_cleanup", "agentic-tool-use", "complex", [
        {"role": "user", "content": "Inventory unused containers and volumes, prove what is safe to remove, clean them up, and verify disk recovery."},
    ]),
]
