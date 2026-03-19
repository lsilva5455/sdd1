# Task: fix-parallel-timeout-handling — Fix Unhandled TimeoutError in Parallel Thread Orchestration

## Completeness Assessment

| Criterion | Status | Notes |
|-----------|--------|-------|
| Objective | Complete | Clear problem statement with error traceback, root cause analysis, and production impact |
| Scope | Complete | Six specific code locations identified with line numbers and exact methods |
| Acceptance criteria | Complete | 7 measurable criteria defined covering crash prevention, time checks, cleanup, and quality gates |
| Technical context | Complete | Affected layers identified (Infrastructure — threading/serial), root causes traced to specific code paths |
| Dependencies | Complete | No external dependencies needed; Python 3.12 stdlib only (`concurrent.futures`, `threading`) |
| Edge cases | Complete | Serial I/O hangs, `time.sleep` blocking past `round_end_time`, `cancel()` on running futures, race conditions on serial close during shutdown |
| Testing strategy | Partial | Acceptance criteria mention existing tests must pass and ruff check, but no specific new test cases are defined for the timeout handling |
| Impact analysis | Complete | All affected methods listed with line numbers; retry phase confirmed unaffected; no API or config changes |

**Overall Score: 7.5/8 criteria complete**

## Original Description

> Fix an intermittent crash caused by `TimeoutError: 16 (of 32) futures unfinished` in `switch_reboot_and_release_parallel`. The system terminates abruptly when threads exceed `max_thread_wait` because the primary `as_completed()` call has no `TimeoutError` handler. This stops 24/7 SIM-farming production operations.
>
> The error occurs in `src/main.py:784` inside `switch_reboot_and_release_parallel`. The system launches 32 threads (one per COM port) via `ThreadPoolExecutor` and waits using `as_completed(futures, timeout=max_thread_wait)`. When threads don't finish within 30.5 minutes, Python raises `TimeoutError` which propagates unhandled, crashing the program.
>
> Root Causes:
> 1. Missing `TimeoutError` handler (`main.py:784`)
> 2. `_complete_mapping_for_empty_port` ignores `round_end_time` (`main.py:1464`)
> 3. `ThreadPoolExecutor.__exit__` blocks (`main.py:766`)
> 4. `shutdown()` is minimal (`main.py:2192`)
> 5. Long `time.sleep` calls are not interruptible (`main.py:1427`)

## Enhanced Description

### Objective

Fix a production-critical intermittent crash where the Orchestrator's primary parallel processing phase (`switch_reboot_and_release_parallel`) raises an unhandled `TimeoutError` when worker threads exceed the configured timeout. The fix must ensure graceful degradation -- logging the timeout, cleaning up resources, and continuing to the next production cycle -- instead of terminating the entire 24/7 SIM-farming process.

The inconsistency is notable: the retry phase (`_retry_failed_ports`) already handles `TimeoutError` correctly at line 1603, but the primary phase at line 784 does not. This is a pattern-consistency bug compounded by missing time-boundary enforcement in long-running sub-operations.

### Scope

- **In scope**:
  - Add `TimeoutError` exception handling to the primary `as_completed` call in `switch_reboot_and_release_parallel`
  - Add `round_end_time` boundary enforcement inside `_complete_mapping_for_empty_port` loop
  - Replace blocking `time.sleep()` calls in `_process_empty_port` with time-aware waits
  - Increase `max_thread_wait` safety margin from 30s to 60s
  - Improve `shutdown()` to close all tracked serial ports and stop the status logging thread
  - Cancel unfinished futures when `TimeoutError` is caught
- **Out of scope**:
  - Refactoring the monolithic `main.py` into separate modules (future DDD migration)
  - Changes to `_retry_failed_ports` (already handles `TimeoutError` correctly)
  - Changes to `_process_single_port` monitoring loop (already checks `round_end_time` at loop start)
  - Changes to `data_manager.py` `as_completed` call (separate concern, no timeout configured there)
  - Configuration schema changes (`config.json`)
  - Flask API or frontend changes
  - Adding new dependencies

### Affected Architecture Layers

- [ ] Domain (entities, value objects, repository ABCs)
- [ ] Application (services, validators)
- [x] Infrastructure (DB repos, hardware adapters, serial communication) — serial port lifecycle management in `shutdown()`
- [ ] Presentation — Flask API (blueprints, routes)
- [ ] Presentation — React Dashboard (components, hooks)
- [ ] Presentation — Streamlit Dashboard (pages, widgets)

**Note**: The primary changes are in the Orchestrator class (`src/main.py`), which in the current monolithic architecture handles both application-layer orchestration and infrastructure-layer thread/serial management. Per `backend-standards.mdc`, since we are modifying existing production code, we follow the conventions of the surrounding code rather than refactoring to DDD layers.

### Acceptance Criteria

1. **GIVEN** 32 threads are running and 16 exceed `max_thread_wait`, **WHEN** `as_completed` raises `TimeoutError`, **THEN** the system logs a warning with the count of unfinished futures and continues to the post-parallel-phase logic (status logging stop, round summary, next cycle) instead of crashing
2. **GIVEN** `_complete_mapping_for_empty_port` is iterating over unregistered SIMs, **WHEN** `datetime.now() >= round_end_time`, **THEN** the method stops iterating and returns the slots registered so far
3. **GIVEN** `_process_empty_port` is in its 15-second sleep between CREG checks, **WHEN** `round_end_time` is reached during the sleep, **THEN** the sleep exits within 1 second instead of waiting the full 15 seconds
4. **GIVEN** the system is shutting down via `shutdown()`, **WHEN** `self.port_states` contains open serial objects, **THEN** all open serial ports are closed with per-port error handling, and the count of closed ports is logged
5. **GIVEN** the system is shutting down via `shutdown()`, **WHEN** the status logging thread is active, **THEN** `status_logging_active` is set to `False` and the thread is joined with a bounded timeout
6. **GIVEN** `TimeoutError` is caught in `switch_reboot_and_release_parallel`, **WHEN** there are unfinished futures, **THEN** `future.cancel()` is called on each unfinished future to prevent queued-but-not-started tasks from executing
7. **GIVEN** all changes are applied, **WHEN** `pytest tests/ -v` is run, **THEN** all existing tests pass; **AND WHEN** `ruff check src/main.py` is run, **THEN** no linting errors are reported

### Edge Cases and Error Scenarios

1. **All 32 threads timeout**: The `TimeoutError` handler logs a warning, cancels all futures, and the round completes with 0 successful ports. The next cycle starts normally.
2. **`TimeoutError` during retry phase**: Already handled by existing `except TimeoutError` in `_retry_failed_ports` -- no change needed.
3. **Serial port already closed when `shutdown()` tries to close it**: Each port close is wrapped in `try/except`, so an already-closed port is silently skipped.
4. **Thread holding serial when `shutdown()` closes it**: The thread will get a `SerialException` on its next `serial_obj.write()`/`serial_obj.read()` call, which is already caught by the per-thread `except Exception` handler in `_process_single_port` (line 1189) and `_process_empty_port` (line 1433).
5. **`_complete_mapping_for_empty_port` called with 0 unregistered slots**: Returns empty list immediately -- no change in behavior.
6. **`round_end_time` reached mid-switch in `_complete_mapping_for_empty_port`**: The check happens at the top of each iteration, so a switch/reboot/wait in progress will complete before the check fires. This is acceptable because the operation takes ~40s and the extra time is within the 60s safety margin.
7. **`status_thread` is `None` or not started when `shutdown()` runs**: Guarded by `hasattr` and `None` checks.
8. **`self.port_states` not yet initialized when `shutdown()` runs**: Guarded by `hasattr` check.

### Dependencies

- **Prerequisites**: None -- this is a bugfix to existing production code
- **External**: No new libraries required. Uses only Python 3.12 stdlib (`concurrent.futures`, `threading`, `datetime`, `time`)
- **Affected components**:
  - `src/main.py` — `Orchestrator` class: methods `switch_reboot_and_release_parallel`, `_complete_mapping_for_empty_port`, `_process_empty_port`, `shutdown`
  - No changes to `hardware_controller.py`, `slot_logic.py`, `data_manager.py`, or any other file

### Testing Strategy

- **Unit tests**: The existing test suite (`tests/`) must continue to pass. No new hardware-dependent tests are needed since the changes are defensive error handling.
- **Integration tests**: Not applicable -- the changes affect thread lifecycle management which requires real hardware to trigger.
- **Manual verification**:
  - Deploy to a test node and run for multiple production cycles
  - Verify that when threads exceed `max_thread_wait`, the system logs the timeout warning and starts the next cycle
  - Verify that `shutdown()` (Ctrl+C) closes serial ports and logs the count
  - Monitor logs for `_complete_mapping_for_empty_port` early termination messages when `round_end_time` is reached
- **Regression check**: Run `pytest tests/ -v` and `ruff check src/main.py` after all changes

### Implementation Notes

- **Pattern consistency**: The `TimeoutError` handler in `switch_reboot_and_release_parallel` should mirror the existing pattern in `_retry_failed_ports` (line 1603-1611) for code consistency.
- **`future.cancel()` semantics**: In Python's `concurrent.futures`, `cancel()` only prevents futures that haven't started yet. Already-running threads are NOT interrupted -- they terminate naturally when they check `round_end_time`. This is by design and documented in the Resolved Questions.
- **Time-aware sleep pattern**: Replace `time.sleep(N)` with a loop of `time.sleep(1)` that checks `round_end_time` each second. This is a common pattern for interruptible waits in threaded Python code.
- **`shutdown()` ordering**: Stop the logging thread first, then close serial ports, then kill SimClient. This prevents log messages about closed ports from being swallowed.
- **Spanish in existing code**: Per `base-standards.mdc`, existing Spanish identifiers and log messages are acceptable. New log messages added by this fix should use English.
- **No DDD refactoring**: Per `backend-standards.mdc`, since we are modifying existing production code in the monolithic `main.py`, we follow the surrounding code conventions. The DDD layered structure is a future target.
