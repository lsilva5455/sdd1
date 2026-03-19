# Orchestration

## Overview

Specifies the main system orchestrator (`Orchestrator`), which manages the complete SIM production cycle: from hardware initialization to continuous network registration monitoring. Implemented in the `Orchestrator` class within `main.py` (~2441 lines), it coordinates SimController, SlotManager, and DataManager in a multi-threaded flow with a barrier pattern.

## Key Concepts

### Production Cycle

Complete sequence that the system executes repeatedly to maximize SIM utilization:

1. **Kill SimClient** → terminate previous instance.
2. **Initialize SimBanks** → hardware reset (AT+CWSIM / AT+NEXT00).
3. **Open serial ports** → block all modem ports.
4. **Launch SimClient** → start third-party software.
5. **Parallel processing per port** → switch, reboot, verify, monitor.
6. **Retry failed ports** → second attempt for ports with errors.
7. **Complete round** → wait `cambio_fila_minutos` before the next one.

### Round

A complete iteration of the production cycle. Each round processes all available modems with the current row (or slot), then advances to the next position.

### PortState

Class that encapsulates the state of each modem port in a **thread-safe** manner. Each port has an independent PortState.

## PortState — Port States

```
waiting_registration  →  Modem is waiting to register on the cellular network.
released              →  Modem registered successfully and is available for SimClient.
failed                →  Modem failed (no registration, serial error, invalid SIM, etc.).
```

### State Transitions

```
[start] → waiting_registration
              │
              ├── CREG = 1 or 5 ──→ released
              │
              ├── Timeout/Error ──→ failed
              │
              └── sim_intento_operativo reached ──→ [change SIM] → waiting_registration
```

### PortState Attributes

- `state`: Current state (waiting_registration / released / failed).
- `serial_obj`: `serial.Serial` object for the port.
- `phone`: Phone number of the active SIM.
- `iccid`: ICCID of the active SIM.
- `simbank`: Control port of the associated SimBank.
- `column`: SimBank column.
- `row`: Current row.

## Barrier Pattern

The Orchestrator uses a barrier pattern to synchronize operations that must be global:

1. **Switching phase**: All modems switch their SIM in parallel (each thread switches its column). Threads wait until ALL complete the switch before continuing.
2. **Launch phase**: SimClient is launched ONCE after all switches are completed.
3. **Monitoring phase**: Each modem monitors its network registration independently.

```
Thread-1 (COM3)  ─── switch_sim ───┐
Thread-2 (COM5)  ─── switch_sim ───┤
Thread-3 (COM7)  ─── switch_sim ───┤ BARRIER: wait for all to finish
Thread-4 (COM9)  ─── switch_sim ───┤
...                                │
Thread-16(COM37) ─── switch_sim ───┘
                                   │
                          Launch SimClient
                                   │
Thread-1 (COM3)  ─── monitor_creg ─── released/failed
Thread-2 (COM5)  ─── monitor_creg ─── released/failed
...
```

## Detailed Cycle Sequence

### 1. Kill SimClient
- Terminate any running SimClient instance.
- Ensure modem serial ports are free.

### 2. Initialize SimBanks
- For each SimBank in `config.json`:
  - Open control serial port.
  - Send `AT+CWSIM` (reset).
  - Send `AT+NEXT00` (position at row 0).

### 3. Open Serial Ports
- Open serial connection to ALL modems (16 ports).
- Create a PortState for each modem in `waiting_registration` state.

### 4. Launch SimClient
- Start the SimClient process (third-party software).
- SimClient connects to the modems and to SMSHub marketplace.

### 5. Parallel Processing Per Port

For each modem port, in an independent thread:

#### 5a. Switch SIM
- Get the next slot from SlotManager (`get_next_slot()`).
- Send `AT+SWIT{col}-{row:04d}` command to the corresponding SimBank.
- Wait `switch_wait_seconds` (**3.2 seconds**).

#### 5b. Staggered Wait
- Apply staggered delay per column: `delay = (col_num - 1) * 3` seconds.
- **Purpose**: Avoid RF jamming when multiple modems boot simultaneously.
- Column 1: 0s delay, Column 2: 3s, Column 3: 6s, ..., Column 8: 21s.

#### 5c. Reboot Modem
- Send reboot command based on model:
  - EC25: `AT+CFUN=0` → wait 2s → `AT+CFUN=1`.
  - UC20: `AT+CFUN=1,1`.
- Wait `reboot_stabilization_seconds` (**15 seconds**).

#### 5d. CCID Verification
- Read modem ICCID via `AT+CCID`.
- Compare with the expected ICCID from the slot.
- If mismatch: `CCIDAnalyzer` diagnoses the cause.

#### 5e. Continuous CREG Monitoring
- Query `AT+CREG?` every **15 seconds**.
- If `CREG = 0,1` or `0,5` → mark port as `released`.
- If timeout (first time: `network_registration_first_seconds` = **20s**):
  - Increment attempt counter.
  - If attempts < `sim_intento_operativo` (**5**) → retry with same SIM.
  - If attempts >= `sim_intento_operativo` → **change SIM** (get new slot from SlotManager and return to 5a).

### 6. Retry Failed Ports
- After completing the first pass, collect ports in `failed` state.
- Execute a full second attempt (switch → reboot → verify → monitor) for each failed port.

### 7. Complete Round
- Wait until `cambio_fila_minutos` (**30 minutes**) have elapsed since the round started.
- Start the next round (return to step 1).

## Relevant Configuration Parameters

| Parameter | Default Value | Description |
|-----------|---------------|-------------|
| `cambio_fila_minutos` | 30 | Duration of each round in minutes |
| `sim_intento_operativo` | 5 | Maximum attempts per SIM before switching |
| `max_workers` | 16 | Parallel threads for port processing |
| `switch_wait_seconds` | 3.2 | Post-SIM-switch wait time |
| `reboot_stabilization_seconds` | 15 | Post-modem-reboot wait time |
| `network_registration_first_seconds` | 20 | Timeout for first registration attempt |

## CLI Arguments

The Orchestrator accepts command-line arguments to control its behavior:

- Selection of specific SimBanks to use.
- Override of configuration parameters.
- Debug/verbose mode.
- Selection of specific rows.

## Error Handling

- **Serial port unresponsive**: Marked as `failed` and retried in the retry phase.
- **SimBank doesn't respond to initialization**: Fatal error, the SimBank is excluded from the round.
- **SimClient won't start**: Fatal error, the round is aborted.
- **All ports fail**: Event is logged and the next round continues.
- **TimeoutError in parallel phase**: When worker threads in `switch_reboot_and_release_parallel` exceed `max_thread_wait` (calculated as `cambio_fila_minutos * 60 + 60s` margin), the `TimeoutError` from `as_completed()` is caught gracefully. Unfinished futures are cancelled (queued-but-not-started only), running threads terminate naturally when they check `round_end_time`, and the system continues to the next cycle. The same pattern is used in `_retry_failed_ports`.
- **Round time boundary enforcement**: `_complete_mapping_for_empty_port` checks `round_end_time` before processing each SIM slot, breaking early if the round deadline has passed. The 15-second stabilization sleep in `_process_empty_port` is time-aware (checks `round_end_time` every second).
- **User interruption**: Graceful handling of Ctrl+C via `shutdown()`, which stops the status logging thread, closes all tracked serial ports (with per-port error handling), and terminates SimClient.

## Relevant Source Files

- `src/main.py` — Orchestrator and PortState (~2441 lines).
- `src/hardware_controller.py` — SimController invoked by Orchestrator.
- `src/slot_logic.py` — SlotManager invoked by Orchestrator.
- `legacy/sadmin_legacy_docs/CTX_04_Flujo_Actual_Legacy.md` — Legacy flow and FSM proposal (reference).
