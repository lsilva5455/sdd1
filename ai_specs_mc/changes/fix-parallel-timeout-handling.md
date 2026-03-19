# Fix Unhandled TimeoutError in Parallel Thread Orchestration

## Objective

Fix an intermittent crash caused by `TimeoutError: 16 (of 32) futures unfinished` in `switch_reboot_and_release_parallel`. The system terminates abruptly when threads exceed `max_thread_wait` because the primary `as_completed()` call has no `TimeoutError` handler. This stops 24/7 SIM-farming production operations.

## Context

The error occurs in `src/main.py:784` inside `switch_reboot_and_release_parallel`. The system launches 32 threads (one per COM port) via `ThreadPoolExecutor` and waits using `as_completed(futures, timeout=max_thread_wait)`. When threads don't finish within 30.5 minutes, Python raises `TimeoutError` which propagates unhandled, crashing the program.

Ironically, the retry phase (`_retry_failed_ports` at line 1603) already implements the correct pattern with `except TimeoutError` -- it was simply not applied to the primary phase.

### Root Causes

1. **Missing `TimeoutError` handler** (`main.py:784`): The `for future in as_completed(futures, timeout=max_thread_wait)` loop has no `try/except TimeoutError`, unlike `_retry_failed_ports` which handles it correctly.

2. **`_complete_mapping_for_empty_port` ignores `round_end_time`** (`main.py:1464`): This method iterates over ALL unregistered SIMs doing ~40s of work per SIM (switch + reboot + wait). With 16 SIMs, this takes ~640s (10+ min) without checking if the round time has expired. This is the primary reason threads exceed the timeout.

3. **`ThreadPoolExecutor.__exit__` blocks** (`main.py:766`): When `TimeoutError` escapes the `with` block, Python calls `executor.shutdown(wait=True)`, which blocks until ALL threads finish -- even if they're stuck in `time.sleep(35)`.

4. **`shutdown()` is minimal** (`main.py:2192`): Only sets `self.running = False` and kills SimClient. Does not close serial ports, stop logging threads, or cancel futures.

5. **Long `time.sleep` calls are not interruptible** (`main.py:1427`): `time.sleep(15)` blocks the thread for the full duration even if `round_end_time` has already passed.

## Error Traceback

```
File "src/main.py", line 1814, in run_continuous
    success = self.run_production_cycle()
File "src/main.py", line 1785, in run_production_cycle
    self.switch_reboot_and_release_parallel(serial_objects)
File "src/main.py", line 705, in switch_reboot_and_release_parallel
    for future in as_completed(futures, timeout=max_thread_wait):
TimeoutError: 16 (of 32) futures unfinished
```

## Acceptance Criteria

1. The system MUST NOT crash when threads exceed `max_thread_wait` -- it should log a warning and continue to the next production cycle
2. `_complete_mapping_for_empty_port` MUST check `round_end_time` before each SIM iteration and stop early if time has expired
3. `shutdown()` MUST close all open serial ports tracked in `self.port_states`
4. `shutdown()` MUST stop the status logging thread if active
5. Long `time.sleep()` calls in thread loops MUST be replaced with time-aware waits that check `round_end_time`
6. All existing tests MUST continue to pass
7. `ruff check src/main.py` MUST pass without errors

## Affected Code

| Method | File | Lines | Change |
|--------|------|-------|--------|
| `switch_reboot_and_release_parallel` | `src/main.py` | 766-788 | Add `try/except TimeoutError` around `as_completed` loop |
| `_complete_mapping_for_empty_port` | `src/main.py` | 1443-1536 | Add `round_end_time` parameter and check it per iteration |
| `_process_empty_port` | `src/main.py` | 1384 | Pass `round_end_time` to `_complete_mapping_for_empty_port` |
| `shutdown` | `src/main.py` | 2192-2203 | Add serial cleanup, logging thread stop, bounded waits |
| `_process_empty_port` | `src/main.py` | 1427 | Replace `time.sleep(15)` with round-time-aware sleep |
| `switch_reboot_and_release_parallel` | `src/main.py` | 764 | Increase safety margin from 30s to 60s |

## Resolved Questions

1. **Python version**: Python 3.12 (supports `cancel_futures` parameter in `shutdown()`, available since 3.9)
2. **Serial port cleanup**: Close all ports in `self.port_states` during shutdown; threads that are still running will get exceptions on their next serial I/O which they already handle
3. **`cancel()` on running futures**: `future.cancel()` only prevents not-yet-started futures. Already-running threads terminate naturally via `round_end_time` checks. This is acceptable.
4. **Retry phase**: The `_retry_failed_ports` method already handles `TimeoutError` correctly -- no changes needed there
5. **`max_thread_wait` margin**: Increase from 30s to 60s to account for thread wake-up delays from `time.sleep()` calls
