# Implementation Plan: fix-parallel-timeout-handling — Fix Unhandled TimeoutError in Parallel Thread Orchestration

## Overview

Fix a production-critical intermittent crash where `switch_reboot_and_release_parallel` raises an unhandled `TimeoutError` when worker threads exceed `max_thread_wait`. The fix adds graceful timeout handling (matching the existing pattern in `_retry_failed_ports`), enforces `round_end_time` boundaries in long-running sub-operations, replaces blocking `time.sleep()` with time-aware waits, and improves `shutdown()` for proper serial port cleanup.

**Architecture principles**: This is a bugfix to existing production code in the monolithic `src/main.py`. Per `backend-standards.mdc`, we follow the conventions of the surrounding code rather than refactoring to DDD layers. All changes are in a single file (`src/main.py`) within the `Orchestrator` class.

## Architecture Context

- **Layers involved**: Infrastructure (threading lifecycle, serial port management)
- **Components/files affected**:
  - `src/main.py` — **MODIFY** — `Orchestrator` class: 4 methods changed, 0 new methods
- **Backend/frontend**: Backend only (no API, no frontend changes)
- **No new files, no new dependencies**

## Implementation Steps

### Step 0: Create Feature Branch

- **Action**: Create and switch to a new feature branch
- **Branch Naming**: `feature/fix-parallel-timeout-handling`
- **Implementation Steps**:
  1. Ensure you're on the latest `main` branch
  2. Pull latest changes: `git pull origin main`
  3. Create new branch: `git checkout -b feature/fix-parallel-timeout-handling`
  4. Verify branch creation: `git branch`
- **Notes**: This must be the FIRST step before any code changes. Refer to `ai_specs_mc/specs/backend-standards.mdc` section "Development Workflow" for workflow rules.

### Step 1: Add TimeoutError Handler to `switch_reboot_and_release_parallel`

- **File**: `src/main.py` (MODIFY)
- **Action**: Wrap the `with ThreadPoolExecutor` block in a `try/except TimeoutError` to match the pattern already used in `_retry_failed_ports` (lines 1603-1611). Also increase the safety margin from 30s to 60s.
- **Target Lines**: 764-789
- **Implementation Steps**:
  1. **Change line 764** — increase margin from `+ 30` to `+ 60`:
     ```python
     max_thread_wait = (self.cambio_fila_minutos * 60) + 60
     ```
  2. **Wrap the `with ThreadPoolExecutor` block** (lines 766-788) in a `try/except TimeoutError` that mirrors the pattern from `_retry_failed_ports` (lines 1603-1611):
     ```python
     try:
         with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
             # ... existing futures submission code (unchanged) ...

             for future in as_completed(futures, timeout=max_thread_wait):
                 try:
                     future.result()
                 except Exception as e:
                     self.logger.warning(f"⚠️ Task generó excepción: {e}")
     except TimeoutError:
         unfinished = sum(1 for f in futures if not f.done())
         self.logger.warning(
             f"⚠️ TimeoutError in parallel phase: {unfinished} of {len(futures)} futures unfinished after {max_thread_wait}s"
         )
         # Cancel queued-but-not-started futures
         cancelled = sum(1 for f in futures if f.cancel())
         if cancelled:
             self.logger.info(f"   Cancelled {cancelled} queued futures")
         self.logger.info(
             "   Running threads will terminate naturally when they check round_end_time"
         )
     ```
  3. **Ensure `futures` is declared before the try block** so it's accessible in the `except` clause. Move the list initialization outside the `with` block or ensure the variable is accessible. Since `futures` is built inside the `with` block, declare `futures: list = []` before the `try` to handle the edge case where the executor fails before creating futures.
- **Dependencies**: No new imports needed — `TimeoutError` is a builtin, `as_completed` and `ThreadPoolExecutor` are already imported.
- **Implementation Notes**:
  - The `except TimeoutError` must be OUTSIDE the `with` block. When `TimeoutError` escapes the `with` block, Python calls `executor.shutdown(wait=True)` which blocks. By placing `try/except` outside `with`, we catch the error after `__exit__` completes, which is correct — the threads have already had time to finish by then.
  - Actually, to avoid `executor.shutdown(wait=True)` blocking, we should use `executor.shutdown(wait=False, cancel_futures=True)` explicitly before the `with` block exits. **Revised approach**: catch the `TimeoutError` INSIDE the `with` block, call `executor.shutdown(wait=False, cancel_futures=True)`, then break/return. Let me reconsider...
  - **Final approach**: The `TimeoutError` is raised by the `as_completed()` iterator, NOT by the `with` block. We catch it inside the `for` loop scope but still inside the `with` block. Then we cancel futures explicitly. The `with` block's `__exit__` calls `shutdown(wait=True)`, which will return quickly because running threads will finish when they hit `round_end_time` checks. The 60s margin ensures this is reasonable.
  - **Pattern match**: Mirror the exact structure from `_retry_failed_ports` (lines 1590-1613), which places the `try/except TimeoutError` OUTSIDE the `with` block.

### Step 2: Add `round_end_time` Parameter to `_complete_mapping_for_empty_port`

- **File**: `src/main.py` (MODIFY)
- **Action**: Add `round_end_time` parameter to the method signature and check the time boundary at the top of each iteration
- **Target Lines**: 1443-1536
- **Function Signature**:
  ```python
  def _complete_mapping_for_empty_port(
      self, port: str, pool_com: str, unregistered_slots: List[Dict], state: PortState,
      round_end_time: datetime
  ) -> List[Dict]:
  ```
- **Implementation Steps**:
  1. **Add `round_end_time: datetime` parameter** to the method signature (line 1444, after `state: PortState`)
  2. **Add time check at the top of the `for` loop** (after line 1464, before processing each slot):
     ```python
     # Check time boundary before processing next SIM
     if datetime.now() >= round_end_time:
         self.logger.warning(
             f"[{port}] ⏰ round_end_time reached during mapping at {idx}/{total} — returning {len(registered_slots)} registered so far"
         )
         break
     ```
  3. Keep the rest of the method unchanged — the `break` will fall through to the existing return at line 1536
- **Dependencies**: `datetime` is already imported
- **Implementation Notes**:
  - The time check is at the TOP of each iteration, so an in-progress switch/reboot/wait will complete before the next check fires. This is acceptable because each iteration takes ~40s and the 60s margin accommodates this.
  - If 0 SIMs have been processed when the timeout fires, the method returns `[]`, which is handled correctly by the caller.

### Step 3: Pass `round_end_time` to `_complete_mapping_for_empty_port` from Caller

- **File**: `src/main.py` (MODIFY)
- **Action**: Update the call site in `_process_empty_port` to pass the `round_end_time` argument
- **Target Lines**: 1384-1386
- **Implementation Steps**:
  1. **Update the method call** at line 1384-1386 to include `round_end_time`:
     ```python
     registered_slots = self._complete_mapping_for_empty_port(
         port, pool_com, unregistered_slots, state, round_end_time
     )
     ```
  2. Verify that `round_end_time` is available in the `_process_empty_port` scope — it IS, as it's a parameter of `_process_empty_port` (passed from the thread submission at line 776).
- **Dependencies**: None
- **Implementation Notes**: Single-line change — just add `round_end_time` to the existing call.

### Step 4: Replace Blocking `time.sleep(15)` with Time-Aware Wait

- **File**: `src/main.py` (MODIFY)
- **Action**: Replace the blocking `time.sleep(15)` at line 1427 with a time-aware loop that checks `round_end_time` every second
- **Target Line**: 1427
- **Implementation Steps**:
  1. **Replace** `time.sleep(15)` with:
     ```python
     # Time-aware sleep: check round_end_time every second
     for _ in range(15):
         if datetime.now() >= round_end_time:
             break
         time.sleep(1)
     ```
- **Dependencies**: `datetime` already imported, `time` already imported
- **Implementation Notes**:
  - This pattern allows the thread to exit within 1 second of `round_end_time` being reached, instead of waiting the full 15 seconds.
  - The next iteration of the outer loop will hit the existing `round_end_time` check at line 1419 and return.
  - We do NOT replace `time.sleep(5)` at line 1431 (error recovery sleep) — it's short enough and only fires on exceptions.

### Step 5: Improve `shutdown()` for Serial Port Cleanup and Logging Thread Stop

- **File**: `src/main.py` (MODIFY)
- **Action**: Enhance the `shutdown` method to: (1) stop the status logging thread, (2) close all tracked serial ports, (3) then kill SimClient
- **Target Lines**: 2192-2203
- **Function Signature** (unchanged):
  ```python
  def shutdown(self):
  ```
- **Implementation Steps**:
  1. **Add logging thread stop** — before killing SimClient, stop the status logging thread:
     ```python
     # Stop status logging thread
     self.status_logging_active = False
     if hasattr(self, '_status_thread') and self._status_thread is not None:
         try:
             self._status_thread.join(timeout=5)
             self.logger.info("Status logging thread stopped")
         except Exception as e:
             self.logger.warning(f"Error stopping status thread: {e}")
     ```
  2. **Add serial port cleanup** — iterate `self.port_states` and close all open serial objects:
     ```python
     # Close all tracked serial ports
     if hasattr(self, 'port_states'):
         closed_count = 0
         for port, state in self.port_states.items():
             try:
                 if state.serial_obj and state.serial_obj.is_open:
                     state.serial_obj.close()
                     closed_count += 1
             except Exception as e:
                 self.logger.warning(f"Error closing serial port {port}: {e}")
         if closed_count:
             self.logger.info(f"Closed {closed_count} serial port(s)")
     ```
  3. **Keep existing SimClient kill** after the serial cleanup
  4. **Final order in `shutdown()`**:
     1. `self.running = False`
     2. Stop status logging thread
     3. Close serial ports
     4. Kill SimClient
     5. Log completion
- **Dependencies**: No new imports
- **Implementation Notes**:
  - Need to verify the attribute name for the status logging thread. Search for where the thread is created/stored in the Orchestrator class. It may be `self._status_thread`, `self.status_thread`, or started inline without being saved. If it's not saved as an attribute, we skip the thread join (the `hasattr` guard handles this).
  - Each serial port close is wrapped in its own `try/except` so one failing port doesn't prevent closing the others.
  - New log messages are in English per `base-standards.mdc`.

### Step 6: Verify Quality

- **Action**: Run quality checks to ensure the implementation meets project standards
- **Implementation Steps**:
  1. Run linter: `ruff check src/main.py`
  2. Run existing tests: `pytest tests/ -v`
  3. Verify no new imports are needed
  4. Manual review: Confirm the `TimeoutError` handler matches the pattern in `_retry_failed_ports`
  5. Manual review: Confirm `_complete_mapping_for_empty_port` breaks correctly when `round_end_time` is reached
  6. Manual review: Confirm `shutdown()` ordering is correct (stop logging → close serial → kill SimClient)

### Step 7: Update Technical Documentation

- **Action**: Review and update technical documentation according to changes made
- **Implementation Steps**:
  1. **Review Changes**: All changes are in `src/main.py`, `Orchestrator` class — 4 methods modified, 0 new files
  2. **Identify Documentation Files**:
     - `openspec/specs/orchestration/spec.md` — if it documents `switch_reboot_and_release_parallel` behavior, update to reflect TimeoutError handling
     - No API changes → no API docs update
     - No new dependencies → no `requirements.txt` update
     - No architecture changes → no `backend-standards.mdc` update
  3. **Update Documentation**:
     - Update `openspec/specs/orchestration/spec.md` if it references the parallel phase behavior to note that `TimeoutError` is now handled gracefully
     - Add a note about `shutdown()` serial cleanup if the spec documents shutdown behavior
  4. **Verify Documentation**: Confirm all behavioral changes are reflected
- **References**:
  - Follow process described in `ai_specs_mc/specs/documentation-standards.mdc`
  - All documentation must be written in English
- **Notes**: This step is MANDATORY before considering the implementation complete.

## Implementation Order

1. **Step 0**: Create feature branch `feature/fix-parallel-timeout-handling`
2. **Step 1**: Add `TimeoutError` handler to `switch_reboot_and_release_parallel` (lines 764-789)
3. **Step 2**: Add `round_end_time` parameter to `_complete_mapping_for_empty_port` (lines 1443-1445)
4. **Step 3**: Pass `round_end_time` to `_complete_mapping_for_empty_port` from `_process_empty_port` (line 1384)
5. **Step 4**: Replace `time.sleep(15)` with time-aware wait in `_process_empty_port` (line 1427)
6. **Step 5**: Improve `shutdown()` for serial cleanup and logging thread stop (lines 2192-2203)
7. **Step 6**: Run quality checks (ruff, pytest)
8. **Step 7**: Update technical documentation

## Testing Checklist

- [ ] `ruff check src/main.py` passes with no errors related to our changes
- [ ] `pytest tests/ -v` — all existing tests pass
- [ ] Manual review: `TimeoutError` handler in `switch_reboot_and_release_parallel` mirrors `_retry_failed_ports` pattern
- [ ] Manual review: `_complete_mapping_for_empty_port` signature includes `round_end_time: datetime`
- [ ] Manual review: Time check at top of `for` loop in `_complete_mapping_for_empty_port`
- [ ] Manual review: `time.sleep(15)` replaced with 1-second loop checking `round_end_time`
- [ ] Manual review: `shutdown()` closes serial ports with per-port error handling
- [ ] Manual review: `shutdown()` stops status logging thread before closing ports
- [ ] Manual review: All new log messages are in English
- [ ] Manual review: `futures` variable accessible in `except TimeoutError` scope

## Dependencies

| Package | Type | Purpose | Status |
|---------|------|---------|--------|
| No new dependencies | — | All changes use Python 3.12 stdlib | N/A |

No new dependencies needed. Uses only existing imports: `concurrent.futures.ThreadPoolExecutor`, `concurrent.futures.as_completed`, `datetime.datetime`, `time`, `threading`.

## Notes

- **Minimal impact**: All changes are in `src/main.py`, modifying 4 existing methods. No new files, no new imports, no config changes.
- **Pattern consistency**: The `TimeoutError` handler mirrors the exact pattern from `_retry_failed_ports` (lines 1603-1611), making the code consistent.
- **`future.cancel()` semantics**: `cancel()` only prevents futures that haven't started yet. Already-running threads are NOT interrupted — they terminate naturally when they check `round_end_time`. This is by design.
- **Safety margin**: Increased from 30s to 60s to accommodate the time it takes for `_complete_mapping_for_empty_port` to complete its current iteration before checking `round_end_time`.
- **Spanish in existing code**: Per `base-standards.mdc`, existing Spanish identifiers, log messages, and comments are acceptable. New log messages added by this fix use English.
- **Type hints**: All modified signatures maintain full type annotations per `base-standards.mdc`.
- **Pre-existing LSP errors**: `main.py`, `hardware_controller.py`, and `data_manager.py` have pre-existing type hint issues that are NOT caused by our changes and should not be addressed in this task.
- **`executor.shutdown(wait=True)` blocking**: When `TimeoutError` is caught outside the `with` block (matching `_retry_failed_ports` pattern), `__exit__` calls `shutdown(wait=True)`. The running threads will finish when they hit their `round_end_time` checks, which happens within the 60s margin. This is acceptable and matches the existing pattern.

## Next Steps After Implementation

1. Commit changes with descriptive message following project conventions
2. Deploy to a test node and run for multiple production cycles to confirm:
   - Timeout events are logged and the system continues to the next cycle
   - `_complete_mapping_for_empty_port` respects `round_end_time`
   - `shutdown()` (Ctrl+C) properly closes serial ports
3. Monitor production logs for `TimeoutError in parallel phase` messages to validate the fix under real load
4. Consider future improvements:
   - Refactor `main.py` into separate modules following DDD architecture
   - Add metrics/counters for timeout events
   - Add configurable margin (currently hardcoded 60s)

## Implementation Verification

- [ ] **Code Quality**: `ruff check src/main.py` passes without new errors
- [ ] **Functionality**: `TimeoutError` is caught, logged, and the system continues to the next cycle
- [ ] **Testing**: All existing tests pass (`pytest tests/ -v`)
- [ ] **Integration**: No changes to other files, no import changes, no config changes
- [ ] **Documentation**: `openspec/specs/orchestration/spec.md` updated if needed
