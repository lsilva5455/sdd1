# Hardware Control

## Overview

Specifies the hardware control layer that manages serial communication with SimBanks and Quectel modems. Implemented in the `SimController` class (`hardware_controller.py`, 742 lines), this layer abstracts all AT commands, handles concurrency locks, automatic retries, and modem model detection.

## Components

### SimController

Main class that encapsulates all interaction with serial hardware. Instantiated with the SimBank configuration loaded from `config.json`.

**Responsibilities:**
- Open/close serial connections to SimBanks and modems.
- Send AT commands with automatic retries.
- Initialize SimBanks (AT+CWSIM / AT+NEXT00 sequence).
- Execute SIM switching (AT+SWIT).
- Reboot modems (AT+CFUN).
- Monitor network signal (AT+CREG).
- Verify SIM identity (AT+CCID).
- Detect modem model (EC25/UC20).

## AT Commands

### SimBank Control Commands

| Command | Purpose | Target |
|---------|---------|--------|
| `AT+CWSIM` | Initialize SimBank — reset internal state | SimBank control port |
| `AT+NEXT00` | Initialize SimBank — position at row 0 | SimBank control port |
| `AT+SWIT{col}-{row:04d}` | Switch SIM: column `col`, row `row` (zero-padded 4 digits) | SimBank control port |

### Modem Commands

| Command | Purpose | Target |
|---------|---------|--------|
| `AT+CCID` | Get ICCID of the active SIM | Modem port |
| `AT+CREG?` | Query cellular network registration status | Modem port |
| `AT+CSQ` | Get signal level (RSSI) | Modem port |
| `AT+CFUN=0` / `AT+CFUN=1` | EC25 modem reboot (radio off → on) | Modem port |
| `AT+CFUN=1,1` | UC20 modem reboot (full reset) | Modem port |
| `ATI` / `AT+CGMM` | Identify modem model | Modem port |

### AT+SWIT Format

```
AT+SWIT{column}-{row:04d}
```
- `column`: Column number (1–8).
- `row`: Row number, zero-padded to 4 digits (e.g., `0001`, `0016`).
- Example: `AT+SWIT3-0005` → Column 3, Row 5.

## Concurrency Mechanisms

### pool_locks

Dictionary of `threading.Lock()` indexed by SimBank control port. Ensures that only one thread at a time sends commands to a specific SimBank.

```python
pool_locks = {
    "COM19": threading.Lock(),
    "COM20": threading.Lock()
}
```

**Usage**: The SimBank lock is acquired before sending any AT command to the control port.

### _swit_global_lock

Global `threading.Lock()` that serializes ALL AT+SWIT commands regardless of SimBank. Includes a mandatory delay of **1 second** between consecutive AT+SWIT commands.

**Reason**: SimBanks share an internal communication bus; simultaneous sends can corrupt the signal.

```python
with self._swit_global_lock:
    self._send_at_command(control_port, f"AT+SWIT{col}-{row:04d}", port_name)
    time.sleep(1)  # Mandatory post-SWIT delay
```

## retry_serial Decorator

Decorator that wraps serial operations with automatic retry logic:

- **Caught exceptions**: `serial.SerialException`, `serial.SerialTimeoutException`, `OSError`.
- **Behavior**: Retries the operation a configurable number of times with backoff.
- **Logging**: Records each retry and the final error if retries are exhausted.

## SimBank Initialization Sequence

1. Open serial connection to SimBank control port (baudrate 115200).
2. Send `AT+CWSIM` — reset SimBank internal state.
3. Wait for OK response.
4. Send `AT+NEXT00` — position at row 0.
5. Wait for OK response.
6. SimBank is now ready to receive AT+SWIT commands.

## Main Operations

### switch_sim(control_port, column, row)

Switches the active SIM at a specific column/row of the SimBank:

1. Acquire `_swit_global_lock`.
2. Acquire `pool_lock` for the corresponding SimBank.
3. Send `AT+SWIT{col}-{row:04d}`.
4. Wait for OK response.
5. 1-second post-send delay.
6. Release locks.

### reboot_modem(port, model)

Restarts a modem to force re-registration on the cellular network:

- **EC25**: Send `AT+CFUN=0` (radio off), wait 2s, send `AT+CFUN=1` (radio on).
- **UC20**: Send `AT+CFUN=1,1` (full reset).
- Post-reboot: wait `reboot_stabilization_seconds` (default: **15 seconds**).

### wait_for_signal(port, timeout)

Monitors AT+CREG in a loop until the modem reports network registration:

- **CREG values**: `0,1` (registered home) or `0,5` (registered roaming) = success.
- **Polling interval**: every **15 seconds**.
- **Initial timeout**: `network_registration_first_seconds` (default: **20 seconds**) for the first attempt.
- Returns `True` if registration succeeds, `False` if timeout expires.

### verify_sim_identity(port)

Reads the ICCID of the SIM currently inserted in the modem via `AT+CCID`:

- Parses the response to extract the ICCID number.
- Used to verify that the expected SIM was actually switched correctly.
- Detects mismatches that are analyzed by `CCIDAnalyzer`.

### detect_model(port)

Identifies the model of the connected Quectel modem:

- Sends `ATI` or `AT+CGMM`.
- Parses response looking for "EC25" or "UC20".
- The model determines which reboot method to use.

### kill_simclient()

Terminates the SimClient process (third-party software) if running:

- Searches for the process by name.
- Sends termination signal.
- Waits for confirmation that the process has ended.

## Error Handling

- **SerialException**: Port unavailable or disconnected. Retried via `retry_serial`.
- **SerialTimeoutException**: Read/write serial timeout. Retried.
- **OSError**: Operating system error accessing the port. Retried.
- **Unexpected response**: If SimBank doesn't respond OK to a command, the error is logged and the operation may be retried.
- **Buffer flushing**: Before sending critical commands, `flushInput()` and `flushOutput()` are executed to clear residual serial buffers.

## Relevant Source Files

- `src/hardware_controller.py` — Full SimController implementation (742 lines).
- `legacy/sadmin_legacy_docs/CTX_03_Capa_Hardware_HAL.md` — Extended AT catalog and ModemDriver proposal (legacy reference).
