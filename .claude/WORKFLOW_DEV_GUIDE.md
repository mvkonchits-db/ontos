# Ontos Workflow Development Guide

**Purpose:** Augments USER_RULES.md with Ontos-specific guardrails for the workflow issues (#77-#84). Designed for a non-SE contributor guiding an AI coding assistant.

---

## Your Role in This Process

You (Mikhail) provide direction, review, and approval. The AI writes all code. Your job is to:

1. **Pick which issue to work on** (see Issue Order below)
2. **Review the plan** before any code is written
3. **Review the code** after each change (the AI will explain what changed and why)
4. **Run manual UI checks** when the AI asks (click through the feature in the browser)
5. **Approve commits and PRs**

You do NOT need to: write code, debug stack traces, or understand implementation details unless you want to.

---

## Issue Execution Order

Issues have dependencies. Follow this order:

```
Phase 1 — Standalone fixes (no dependencies)
  #82  Fix tag step handlers         ← smallest, good warmup
  #83  Fix script step handlers      ← standalone fix
  #84  Document deferred items       ← docs only, no code risk

Phase 2 — New triggers (builds on existing patterns)
  #78  Status transition gating      ← backend + frontend + YAML
  #79  Publish/unpublish triggers    ← same pattern as #78

Phase 3 — Notification overhaul (larger scope)
  #80  Message templating            ← prerequisite for #81
  #81  Notification channels + email ← depends on #80
```

Each issue = 1 branch + 1 PR. We work on `feat/issue_77_workflow_system` but create individual commits per issue with conventional commit messages.

---

## Per-Issue Workflow

### 1. Load Context

Before starting each issue, the AI will:
- Re-read the GitHub issue acceptance criteria (`gh issue view <N>`)
- Read the specific files that will be modified
- Present a checklist mapping acceptance criteria to code changes

### 2. Plan (Mandatory)

The AI presents a plan with:
- **Files to modify** (exact paths)
- **What changes** in each file (1-2 sentences)
- **Acceptance criteria mapping** (which criterion each change satisfies)
- **Risk assessment** (what could break)

**You review and say "go" or ask questions.**

### 3. Implement

The AI writes code in small, reviewable chunks:
- One logical change at a time (not the whole issue at once)
- After each chunk: explains what changed and shows the diff summary
- Pauses for your "continue" before moving to the next chunk

### 4. Test

**Backend tests (AI runs these):**
```bash
cd src && hatch -e dev run pytest backend/src/tests/unit/<test_file>.py -v
```

**Frontend type checks (AI runs these):**
```bash
cd src/frontend && yarn type-check
```

**Manual UI verification (you do this when asked):**
The AI will tell you exactly what to click and what to look for.
Example: "Go to Settings > Workflows, click the trigger dropdown, confirm 'Before Status Change' appears."

### 5. Commit

One commit per issue. Format:
```
feat(workflows): <short description>

<body explaining what and why>

Closes #<issue_number>
```

Scope is always `workflows` for these issues. The AI drafts the message, you approve.

### 6. Verify Acceptance Criteria

Before committing, the AI walks through each acceptance criterion checkbox:
- [x] Criterion — How it's satisfied (file:line or test name)
- [ ] Criterion — NOT YET DONE (blocks commit)

All boxes must be checked before commit.

---

## Testing Strategy

### Current State (Baseline)

The workflow system has **zero test coverage** today:
- No `test_workflow_executor.py` (the execution engine)
- No `test_workflow_triggers.py` (the trigger registry)
- No `test_workflows_manager.py` (workflow CRUD/orchestration)
- E2E tests (`cuj-8`, `approvals.spec.ts`) check button visibility but never verify
  that workflows actually block transitions, create notifications, or persist tags.

Each issue we implement will **include tests for the user stories it addresses**.

### Test Layers

| Layer | Tool | Who Runs It | What It Proves |
|-------|------|-------------|----------------|
| Backend unit | pytest via `hatch -e dev run test-unit` | AI | Business logic works (triggers fire, steps execute, DB state changes) |
| Backend integration | pytest via `hatch -e dev run test-integration` | AI | API endpoints return correct responses for workflow scenarios |
| Frontend type safety | `yarn type-check` | AI (when npm available) | No type regressions from our changes |
| Frontend E2E | `yarn test:e2e` (Playwright) | AI (when servers running) | User journeys work end-to-end through the UI |
| Manual UI smoke | Browser | You (when AI asks) | Visual correctness, things automation can't catch |

### User Story → Test Mapping

Each issue ships with tests proving its user stories work. The AI creates these
tests as part of the implementation, not as an afterthought.

**Issue #82 — Tag step fixes (User stories 11, 12)**
```
Backend unit:
  test_assign_tag_persists_to_database()          ← US11: tag actually in DB after step
  test_assign_tag_falls_back_when_fqn_not_found() ← US11: graceful degradation
  test_remove_tag_persists_to_database()          ← US12: tag gone from DB after step
  test_remove_tag_falls_back_when_fqn_not_found() ← US12: graceful degradation
  test_assign_tag_updates_context_for_downstream() ← both: in-memory still works
  test_step_result_includes_persisted_boolean()    ← acceptance criteria
```

**Issue #83 — Script step fixes (User stories 13, 14)**
```
Backend unit:
  test_python_script_can_use_safe_builtins()       ← US13: len(), str(), sorted() work
  test_python_script_has_entity_data_in_globals()   ← US13: entity accessible
  test_python_script_times_out_with_clear_error()   ← US13: timeout behavior
  test_python_script_cannot_import_os()             ← security: sandbox enforced
  test_sql_executes_via_statement_execution_api()   ← US14: SQL runs on warehouse
  test_sql_supports_variable_substitution()         ← US14: ${entity_name} in SQL
  test_sql_returns_clear_error_when_no_warehouse()  ← US14: graceful error
```

**Issue #78 — Status transition gating (User stories 1, 2, 15, 20)**
```
Backend unit:
  test_before_status_change_blocks_transition()     ← US1,2: workflow can block
  test_before_status_change_allows_when_passed()    ← US1,2: workflow can allow
  test_transition_raises_valueerror_when_blocked()   ← US20: clear error message
  test_default_approval_workflow_matches_active()    ← US15: YAML fix verified

Backend integration:
  test_api_transition_blocked_returns_error()        ← US20: error in API response

E2E (Playwright):
  test_blocked_transition_shows_error_in_ui()        ← US20: user sees why it failed
```

**Issue #79 — Publish/unpublish triggers (User stories 3, 19)**
```
Backend unit:
  test_on_publish_fires_after_publication()          ← US3: trigger fires
  test_on_unpublish_fires_after_unpublication()      ← US3: trigger fires
  test_default_publish_notification_workflow_loads()  ← US19: YAML is valid
  test_subscriber_notified_on_publish()              ← US19: notification created

E2E (Playwright):
  test_publish_product_triggers_notification()       ← US3,19: visible in UI
```

**Issue #80 — Message templating (User stories 8, 9, 10)**
```
Backend unit:
  test_substitute_entity_name()                      ← US8: ${entity_name} works
  test_substitute_entity_field()                     ← US10: ${entity.field} works
  test_substitute_step_results()                     ← US10: ${step_results.x.y} works
  test_substitute_handles_missing_var_gracefully()   ← robustness
  test_notification_handler_applies_substitution()   ← US8: actual handler uses it
  test_templates_api_returns_available_templates()   ← US9: API endpoint works
  test_custom_message_overrides_template()           ← US10: custom_message path

E2E (Playwright):
  test_designer_shows_variable_hints()               ← US18: hints visible in UI
```

**Issue #81 — Notification channels + email (User stories 4, 5, 6, 7)**
```
Backend unit:
  test_global_default_channels_from_settings()       ← US4: defaults respected
  test_per_step_channels_override_defaults()         ← US5: override works
  test_email_service_from_settings_returns_none()    ← US6: graceful when not configured
  test_email_service_sends_via_smtp()                ← US7: email actually sent (mocked)
  test_notification_dispatches_to_all_channels()     ← US4: multi-channel delivery
  test_email_failure_does_not_fail_step()            ← acceptance: graceful degradation

E2E (Playwright):
  test_designer_shows_channel_checkboxes()           ← US17: checkboxes in UI
```

**Issue #84 — Documentation (no user stories, no tests)**

### Negative Tests (What Should NOT Happen)

The Databricks PR review checklist requires negative test cases alongside happy paths.
For each issue, the AI includes at least one "this should fail gracefully" test:

| Issue | Negative Test | What It Proves |
|-------|--------------|----------------|
| #82 | Tag FQN not found → step still passes, logs warning | Won't crash on misconfigured workflow |
| #83 | Python `import os` → blocked, clear error | Sandbox can't be escaped |
| #83 | SQL with no warehouse configured → clear error, not crash | Missing config is handled |
| #78 | Blocking workflow fails → transition rejected, original status preserved | DB state is consistent |
| #79 | `on_publish` with no matching workflow → no-op, no error | Missing workflows don't crash |
| #80 | `${nonexistent_var}` in template → left as-is or empty, not crash | Bad templates are safe |
| #81 | Email server unreachable → step succeeds, logs warning | Email failure is non-fatal |

### Backend Test Conventions

Tests live in `src/backend/src/tests/unit/`. The existing infrastructure uses:
- **pytest** with fixtures from `conftest.py`
- **In-memory SQLite** for DB tests (session-scoped, transaction rollback per test)
- **MagicMock** for WorkspaceClient and external services
- **TestClient** for integration tests (FastAPI)

New test files we'll create:
- `test_workflow_executor.py` — Step handler behavior (tag, script, notification, validation)
- `test_workflow_triggers.py` — Trigger matching, firing, blocking vs non-blocking
- Tests added to existing `test_data_products_manager.py` for transition gating

Naming: `test_<what_happens>()` — describes the **behavior**, not the method.
Example: `test_blocked_transition_preserves_original_status()` not `test_transition_status_calls_before_status_change()`

### Frontend E2E Conventions

Playwright specs in `src/frontend/src/tests/`. Existing patterns:
- `beforeAll`: load demo data via `loadDemoData(request)`
- `afterAll`: clear demo data via `clearDemoData(request)`
- Base URL: `http://localhost:3000`, timeout: 90s
- Helper: `dismissCopilot(page)` before interactions

New E2E tests go in `workflow-system.spec.ts` covering:
- Trigger type dropdown shows new options (#78, #79)
- Blocked transition shows error message (#78)
- Channel checkboxes appear in notification step editor (#81)
- Template variable hints in custom message textarea (#80)

E2E tests require both servers running (backend :8000, frontend :3000).

### When to Skip Tests

- Issue #84 (documentation only) — no tests needed
- Pure type/enum additions with no logic — type-check is sufficient
- When npm registry is blocked — E2E and frontend tests deferred, backend tests still run

---

## Smoke Test After Each Issue (Non-Negotiable)

After each issue is committed, verify the app still starts and doesn't regress:

**Backend smoke (AI runs):**
```bash
cd src && hatch -e dev run test-unit 2>&1 | tail -5
# Must show: "X passed, 0 failed"
```

**If dev servers are running — quick regression check (you do):**
1. Reload the browser (Ctrl+R / Cmd+R)
2. Navigate to Settings > Workflows — page loads without errors
3. Open any existing workflow — designer loads without errors
4. Go back to Home — no blank screens or console errors

This takes 30 seconds and catches the #1 risk in a shared codebase: your change
broke something unrelated because of a shared import or model change.

If regression is found, we fix it *before* moving to the next issue. Not after.

---

## Error Handling: Only at Boundaries

The PRD issues touch code that talks to external systems (Databricks SQL warehouse,
SMTP servers, TagsManager DB). The rule from the Databricks PR checklist:

> "All network requests can fail, so they need error handling."

**For our issues, this means:**
- `EmailService.send()` (#81) — must catch SMTP/HTTP errors, log warning, not crash step
- `statement_execution.execute_statement()` (#83) — must catch SDK errors, return clear failure
- `TagsManager.add_tag_to_entity()` (#82) — must catch DB errors, fall back to context-only

**What it does NOT mean:**
- Don't add try/catch around in-memory operations (enum lookups, dict access)
- Don't add validation for impossible states (e.g., "what if TriggerType is None" — it's a Pydantic enum)
- Don't add retry logic — that's explicitly deferred in the PRD (issue #84 documents this)

---

## PR Readiness Checklist (Before Creating PR)

Adapted from the Databricks [Pre-review PR checklist](https://databricks.atlassian.net/wiki/spaces/UN/pages/2585395613). We follow the subset that applies to a Labs project:

- [ ] **Single purpose** — PR description explains the workflow system, all commits are workflow-related
- [ ] **"Why" is clear** — PR body links to PRD (#77) and lists which issues are closed
- [ ] **"What" is scannable** — Each commit message maps to one issue, reviewer can understand without reading code
- [ ] **Tests exist for new logic** — Every backend behavior change has at least one test
- [ ] **No debug artifacts** — No `print()`, `console.log()`, commented-out code, TODO without issue number
- [ ] **Manual test evidence** — PR description includes what was manually verified (screenshots if UI changed)
- [ ] **Self-review pass** — AI re-reads all diffs before presenting PR, flags anything that looks wrong
- [ ] **No unrelated changes** — Nothing outside workflow scope snuck in

---

## YAML Validation (Issues #78, #79)

The default workflows YAML (`default_workflows.yaml`) is loaded at startup by
`WorkflowsManager.load_from_yaml()`. A bad YAML change can prevent the app from starting.

**After any YAML change:**
1. AI reads the YAML loading code to understand what fields are required
2. AI validates the YAML structure matches the Pydantic model expectations
3. Backend tests include a `test_default_workflows_yaml_loads_without_error()` that
   calls `load_from_yaml()` and asserts no exceptions — this catches typos, missing
   fields, and status mismatches before they break startup

This is especially important for #78 (fixing `to_status: "published"` → `"active"`)
where a typo means the workflow never fires and there's no visible error.

---

## Code Change Guardrails

### Before Modifying Any File

1. AI reads the full file (or relevant section) first
2. AI identifies existing patterns in that file and follows them
3. AI never refactors surrounding code — only adds/changes what the issue requires

### Backend Patterns to Follow

- **New enum values:** Add to existing Pydantic enums, never create parallel enums
- **New step handlers:** Follow `BaseStepHandler` abstract class pattern in `workflow_executor.py`
- **New trigger methods:** Follow `before_create()` pattern in `workflow_triggers.py`
- **Manager wiring:** Follow `self_service_routes.py` `before_create` pattern for blocking triggers
- **DB models:** Follow existing SQLAlchemy patterns in `db_models/`
- **Settings:** Use `SettingsManager.get_setting()` / `set_setting()` for new config keys

### Frontend Patterns to Follow

- **New types:** Add to existing type files in `src/frontend/src/types/`
- **Label maps:** Add to `src/frontend/src/lib/workflow-labels.ts`
- **Designer changes:** Modify existing components in `src/frontend/src/components/workflows/`
- **Never create new view files** for these issues — all changes are to existing components

### What NOT to Do

- Do not add new npm packages (VPN registry block active — see MEMORY.md)
- Do not modify files outside the workflow feature unless the issue explicitly requires it
- Do not refactor existing code "while we're in there"
- Do not add error handling for scenarios not in the acceptance criteria
- Do not create utility files for one-off operations
- Do not touch auth, permissions, or startup code

---

## File Reference (Quick Lookup)

These are the files you'll hear about most:

| Shorthand | Full Path | What It Is |
|-----------|-----------|------------|
| **executor** | `src/backend/src/common/workflow_executor.py` | Step handlers + execution engine |
| **triggers** | `src/backend/src/common/workflow_triggers.py` | Trigger registry + convenience methods |
| **models** | `src/backend/src/models/process_workflows.py` | Pydantic models (TriggerType, StepType, etc.) |
| **default YAML** | `src/backend/src/data/default_workflows.yaml` | Out-of-the-box workflow definitions |
| **products mgr** | `src/backend/src/controller/data_products_manager.py` | Data product lifecycle |
| **contracts mgr** | `src/backend/src/controller/data_contracts_manager.py` | Data contract lifecycle |
| **settings model** | `src/backend/src/models/settings.py` | Settings Pydantic models |
| **notif db model** | `src/backend/src/db_models/notifications.py` | Notification DB models |
| **notif model** | `src/backend/src/models/notifications.py` | Notification Pydantic models |
| **email svc** | `src/backend/src/common/email_service.py` | Email sending (created in #81) |
| **FE types** | `src/frontend/src/types/process-workflow.ts` | Frontend TypeScript types |
| **FE labels** | `src/frontend/src/lib/workflow-labels.ts` | Display labels for triggers/steps |
| **FE designer** | `src/frontend/src/components/workflows/workflow-designer.tsx` | Visual workflow designer |
| **workflows guide** | `src/docs/process-workflows-guide.md` | User-facing docs (#84) |

---

## Git Strategy

### Branch Structure

```
main (upstream: databrickslabs/ontos)
  └── feat/issue_77_workflow_system (our working branch)
        ← individual commits per issue
```

### Commit Flow

1. All work happens on `feat/issue_77_workflow_system`
2. One conventional commit per completed issue
3. After all issues are done (or a logical batch), create PR to upstream main
4. PR title: `feat(workflows): complete process workflow system (#77)`

### Push Cadence

Push to fork (`origin`) after each committed issue. This gives you a checkpoint.

```
finish #82 → commit → push
finish #83 → commit → push
finish #84 → commit → push
...
```

### If Something Goes Wrong

- **Bad commit:** AI can `git revert` the last commit (creates a new revert commit, safe)
- **Need to start over on an issue:** `git stash` uncommitted changes, or `git checkout -- .` for tracked files (AI will ask first)
- **Upstream changed:** `git fetch upstream && git rebase upstream/main` before continuing

---

## Communication Protocol

### What the AI Will Tell You

- "Here's the plan for issue #N" → Review and approve
- "I've made change X to file Y because Z" → Acknowledge or ask questions
- "Tests pass / Tests fail because..." → If fail, AI investigates
- "Please check in the UI: [specific instruction]" → You do the manual check
- "Ready to commit issue #N. Here's the acceptance criteria status:" → Review and approve commit
- "All issues complete. Ready to create PR?" → Approve PR creation

### What You Should Tell the AI

- "Go" / "Continue" / "Looks good" → Proceed with plan
- "Wait, what about X?" → AI pauses and addresses
- "I see a problem in the UI: [description]" → AI investigates and fixes
- "Skip the UI part for now" → AI proceeds without UI verification
- "Let's do #83 next" → AI loads context for that issue

---

## Baseline: Cherry-Picked PR #65

We cherry-picked the TypeScript fixes from [PR #65](https://github.com/databrickslabs/ontos/pull/65)
(commit `01a48ca`) to get a clean type-check baseline. This includes:
- 35 TypeScript error fixes across 16 files
- Workflow component type casts (approval-wizard, notification-bell)
- permissions-store test fix

**When PR #65 merges to main:** Our cherry-pick commit will conflict (identical changes).
Resolution: accept either side during rebase, or `git rebase --skip` this commit entirely.

**CI workflow file excluded** — the PAT lacks `workflow` scope. If CI matters later,
the file will arrive when PR #65 merges to main.

---

## Quick Start Checklist

Before starting the first issue:

- [ ] Dev servers running (backend :8000, frontend :3000)
- [ ] On branch `feat/issue_77_workflow_system`
- [ ] Fork synced with upstream main
- [ ] PR #65 cherry-picked (done — commit `01a48ca`)
- [ ] `yarn install` + `yarn type-check` pass (blocked until npm registry unblocked)
- [ ] This guide read and understood

To start: just say "Let's start with issue #82"

---

**Version:** 1.1.0
**Created:** 2026-03-23
**Last Updated:** 2026-03-23
**Scope:** Issues #77-#84 (Process Workflow System)

**Changelog:**
- v1.1.0: Added smoke test protocol, error handling boundaries, PR readiness checklist,
  YAML validation step, negative test cases. Sourced from Databricks PR checklist,
  Labs quality standards, and Ontos CUJ-0.3.
- v1.0.0: Initial guide with issue ordering, testing strategy, git workflow.
