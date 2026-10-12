# Iteration 2 — The Docker sandbox service

- **Commit SHA:** (filled by student)
- **Previous iteration:** `5a61b7e` includes `01-pure-pieces.md`.
- **Mode:** one agent; staged verification (D-118); Spec 02 v0.7.

## Implemented scope
- Student-built image recipe; isolated script/table folder with 0755/0644 modes and configurable
  base directory; SDK factory and chained safe error translation; exact container limits;
  timeout kill, bounded stdout/stderr tails, container/folder cleanup and client ownership.
- Read-only daemon/image check; startup gate and developer setup screen; service-check report.
- Fake Docker client in `tests/analyst_stubs.py`; approved offline harness integration.

## Verification
Commands are from the repo root through the existing WSL venv (`wsl.exe --cd "<repo>" -- …`).
- **RED:** smoke command below first produced 3 collection errors (missing service/fake).
  After the service landed: 2 execution cases passed, 4 integration cases failed because startup
  and diagnostic wiring was absent. Implementation then made them pass.
- **PASS:** `.venv/bin/python -m pytest -q tests/unit/test_sandbox.py tests/unit/test_sandbox_health.py tests/functional/test_sandbox_startup.py tests/unit/test_health.py tests/unit/test_check_services.py tests/unit/test_error_screen.py tests/functional/test_error_screen.py`
  — 51 passed in 25.19 s; six new smoke cases. No real daemon, generated script execution or network.
- **PASS:** `.venv/bin/python -m pytest -q` — 665 passed, 1 live test deselected in 39.54 s.
- **PASS:** `git diff --check -- <iteration-owned tracked files>` — no whitespace errors.

## Deferred to the final iteration (D-118)
- Exhaustive individual checks of VC-215, VC-216, VC-217, VC-218, VC-229, VC-230,
  VC-239 (container portion), VC-242 (Dockerfile portion). Smoke cases exercise these contracts
  together; they do not replace the final per-VC coverage sweep.
- VC-215's prelude integration and VC-228's graph failure route are implemented in Iteration 3;
  their exhaustive verification is in Iteration 5. README portion of VC-242 also belongs there.
- Real isolation and timing checks (VC-245/247) remain student-run in Iteration 5.

## Files
- **Created:** `services/sandbox.py`, `sandbox/Dockerfile`, `tests/unit/test_sandbox.py`,
  `tests/unit/test_sandbox_health.py`, `tests/functional/test_sandbox_startup.py`, this record.
- **Changed:** `.gitignore`, `services/health.py`, `scripts/check_services.py`, `ui/startup.py`,
  `ui/error_screen.py`, `tests/analyst_stubs.py`, `tests/conftest.py`,
  `tests/unit/test_check_services.py`, `tests/unit/test_error_screen.py`,
  `specs/02-analyst-plan-artifacts/CONTEXT.md`, `specs/02-analyst-plan-artifacts/DECISIONS.md`.
- **Deleted:** none. Spec 01's concurrent changes are excluded from this list.

## Deviations and gotchas
- Student-approved S02-D-012/013/014: frozen result/status objects, optional base directory,
  lazy SDK loading, `create` then `start` instead of implicit-pull `run`, last 64 KB retained.
- Shared startup/health files and `tests/conftest.py` were explicitly approved before edits.
  No additional spec 01 interface-name mapping was needed; real names remain authoritative.
- Existing diagnostic/startup expectations were updated for the extra check. The UI smoke tests
  normalize the error bubble's wrapped text when checking the README title.
- The venv lacks the pinned Docker SDK (`ModuleNotFoundError: No module named 'docker'`).
  Production startup reports unavailable; offline fakes remain usable. Nothing installed,
  downloaded, built, pulled, committed or pushed. README changes remain in Iteration 5.

## For the next iteration
- `execute` supplies `prelude_source(...) + "\n" + code` and Selected table paths to
  `prepare_run_folder`; use `base_dir=FALLBACK_RUN_DIR` when system temp is not mountable.
- `run_script(folder, settings.SANDBOX_TIMEOUT_SECONDS)` returns the four attributes consumed by
  `classify_attempt`. Timeout exit code is 137; the flag determines timeout classification.
- Injected clients remain caller-owned. Health owns/closes its factory client. Internal clients
  close automatically. Fakes have no pull method and record creation settings and lifecycle.
- The new README target is `Getting started › Build the sandbox image`; add it in Iteration 5.
- Student review/commit is required before Iteration 3. Iteration 4 additionally requires spec 01
  Iteration 7 committed. This run stops after Iteration 2.

Commit summary: `Spec 02 · Iter 2: Add the Docker sandbox service and startup checks`
