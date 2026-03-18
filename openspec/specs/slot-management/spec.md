# Slot Management

## Overview

Specifies SIM slot management: selection of the next slot to use via circular rotation, state persistence across restarts, dynamic reload of the available positions list, and validation filters to exclude unfit SIMs. Implemented in the `SlotManager` class (`slot_logic.py`, 525 lines).

## Key Concepts

### Slot

A slot represents a specific physical position in a SimBank: the combination of **SimBank** (control port), **column**, and **row**. Additionally, each slot has associated metadata: phone number, ICCID, and registration status.

### Position (lista_pos.json)

JSON file containing the list of available positions (slots) for production. Generated from hardware scanning (`data_manager.py`) and contains the SIMs that passed all validation filters.

### Persistent State (slot_state.json)

JSON file that stores the current index of the circular rotation. Allows the system to resume from where it left off after a restart.

## Components

### SlotManager

Main class that manages slot selection and rotation.

**Responsibilities:**
- Load and dynamically reload `lista_pos.json`.
- Maintain the circular rotation index.
- Persist state in `slot_state.json`.
- Apply validation filters when generating positions.
- Provide the next available slot to each modem port.

## Circular Rotation

The SlotManager implements a **circular rotation** pattern over the position list:

1. A **global index** is maintained that points to the current position in `lista_pos.json`.
2. Each call to `get_next_slot()` advances the index by +1.
3. When reaching the end of the list, the index wraps back to 0 (wrap-around).
4. The index is persisted in `slot_state.json` after each advance.

```
lista_pos.json: [slot_A, slot_B, slot_C, slot_D, slot_E]
                                    ↑
                              current index = 2

get_next_slot() → slot_C, index advances to 3
get_next_slot() → slot_D, index advances to 4
get_next_slot() → slot_E, index advances to 0  (wrap-around)
get_next_slot() → slot_A, index advances to 1
```

## Dynamic Reload

The SlotManager can reload `lista_pos.json` on the fly without restarting the system:

- Detects changes in the file (modification timestamp or explicit signal).
- Reloads the position list.
- Adjusts the index if the new list is shorter than the current index.
- This allows the operator to update the available SIM list while the system is running.

## Position Generation (generate_slot_pos)

The `generate_slot_pos` function generates `lista_pos.json` by applying **5 sequential validation filters**:

### Filter 1: Phone Number Validation
- The SIM must have a valid associated phone number.
- Entries without a number or with an empty number are excluded.

### Filter 2: CCID Validation
- The SIM must have a valid ICCID that was successfully read.
- Entries with empty, error, or unavailable CCID are excluded.

### Filter 3: CREG Validation (Network Registration)
- The SIM must have achieved network registration during the last scan.
- SIMs that failed to register (CREG ≠ 1 or 5) are excluded.

### Filter 4: Country Format Validation
- The phone number must comply with the corresponding country format:
  - **Chile** (CCID with prefix 560): 11 digits, starts with `56`.
  - **Colombia** (CCID with prefix 570): 12 digits, starts with `57`.
  - **Generic**: Between 8 and 15 digits.

### Filter 5: Duplicate Removal
- Entries with duplicate phone numbers are removed.
- In case of duplicates, the first occurrence is kept.

## Data Structures

### lista_pos.json

```json
[
  {
    "simbank": "COM19",
    "column": 1,
    "row": 3,
    "phone": "56912345678",
    "iccid": "8956091234567890123"
  },
  {
    "simbank": "COM19",
    "column": 2,
    "row": 3,
    "phone": "56987654321",
    "iccid": "8956011234567890123"
  }
]
```

### slot_state.json

```json
{
  "current_index": 42,
  "last_updated": "2025-12-15T14:30:00",
  "total_slots": 128
}
```

## Interaction with Other Components

- **DataManager** → generates `lista_pos.json` after hardware scans.
- **Orchestrator** → calls `get_next_slot()` to obtain the next SIM to use on each port.
- **SlotManager** → queries `lista_pos.json` and persists state in `slot_state.json`.

## Constraints

- The SlotManager is **thread-safe**: multiple Orchestrator threads can request slots simultaneously.
- If `lista_pos.json` is empty or all slots fail validation, the system cannot start production.
- The index persisted in `slot_state.json` is validated against the current list size on load — if it exceeds the size, it resets to 0.

## Relevant Source Files

- `src/slot_logic.py` — Full SlotManager implementation (525 lines).
- `src/data_manager.py` — Generates `lista_pos.json` via `generate_slot_pos`.
