# Deployment

## Overview

Specifies deployment requirements, directory structure, dependencies, command-line arguments, logging system, and monitoring for operating the mp_simclient + mapeo_pool system in production.

## Execution Environment

### Operating System

- **Windows** (required) — Quectel modems and SimBanks connect via Windows COM ports.
- Supported versions: Windows 10/11, Windows Server 2016+.

### Required Hardware

| Component | Quantity | Description |
|-----------|----------|-------------|
| SimBank | 1+ (current: 2) | SIM matrix device, connected via USB serial |
| Quectel Modems | 8 per SimBank (current: 16 total) | EC25 or UC20 modems, connected via USB |
| USB Ports | Enough for SimBanks + modems | May require industrial USB hubs |
| SIM cards | Up to 16 x SimBanks | Inserted in SimBank slots |

### Required Software

| Software | Version | Purpose |
|----------|---------|---------|
| Python | 3.8+ | mp_simclient execution |
| SimClient | — | Third-party software for SMSHub connection |
| USB Drivers | Quectel USB drivers | Modem recognition as COM ports |

## Python Dependencies (mp_simclient)

Defined in `requirements.txt`:

| Package | Purpose |
|---------|---------|
| `pyserial` | Serial communication with SimBanks and modems |
| `pytest` | Testing framework |
| `colorama` | Terminal color output (Windows) |

Installation:
```bash
pip install -r requirements.txt
```

## mapeo_pool Dependencies

| Package | Purpose |
|---------|---------|
| Flask | Web API backend |
| React | Web frontend |
| PostgreSQL | Database for sessions and snapshots |
| Node.js / npm | React frontend build |

## Directory Structure

```
mp_core_context/
├── 
│   ├── src/
│   │   ├── main.py              ← Orchestrator (entry point)
│   │   ├── version.py           ← Project version constant
│   │   ├── hardware_controller.py ← SimController
│   │   ├── slot_logic.py         ← SlotManager
│   │   ├── data_manager.py       ← DataManager
│   │   ├── ccid_analyzer.py      ← CCIDAnalyzer
│   │   ├── reset_imei_all.py     ← IMEI reset utility
│   │   └── utils/
│   │       ├── __init__.py       ← Package init
│   │       └── banner.py         ← Startup banner display
│   ├── config.json               ← Topology and parameter configuration
│   ├── requirements.txt          ← Python dependencies
│   └── [runtime files]
│       ├── slot_state.json       ← Rotation state (generated)
│       ├── lista_pos.json        ← Valid positions (generated)
│       ├── numero_simid.txt      ← Phone-to-ICCID mapping (generated)
│       └── *.csv                 ← Scan CSVs (generated)
│
├── legacy/
│   ├── sadmin_legacy_docs/       ← Legacy sadmin documentation
│   │   ├── CTX_01_Reglas_Negocio.md
│   │   ├── CTX_02_Arquitectura_Datos.md
│   │   ├── CTX_03_Capa_Hardware_HAL.md
│   │   └── CTX_04_Flujo_Actual_Legacy.md
│   └── mapeo_pool_documentacion/ ← Legacy mapeo_pool documentation
│       ├── ESTRUCTURA_DICT_NODO.md
│       └── SISTEMA_POOLS_IMPLEMENTACION.md
│
├── utils/
│   └── json_sadmin_mp_simclient/
│       └── convert_dict_to_config.py ← dict_nodo → config.json converter
│
├── openspec/                     ← OpenSpec specifications (Spanish)
│   ├── config.yaml
│   ├── specs/
│   │   ├── hardware-topology/spec.md
│   │   ├── hardware-control/spec.md
│   │   ├── slot-management/spec.md
│   │   ├── orchestration/spec.md
│   │   ├── data-scanning/spec.md
│   │   ├── pool-visualization/spec.md
│   │   ├── session-management/spec.md
│   │   ├── configuration/spec.md
│   │   ├── simclient-integration/spec.md
│   │   └── deployment/spec.md
│   └── changes/
│
└── openspec-en/                  ← OpenSpec specifications (English)
    ├── config.yaml
    ├── specs/
    │   ├── hardware-topology/spec.md
    │   ├── hardware-control/spec.md
    │   ├── slot-management/spec.md
    │   ├── orchestration/spec.md
    │   ├── data-scanning/spec.md
    │   ├── pool-visualization/spec.md
    │   ├── session-management/spec.md
    │   ├── configuration/spec.md
    │   ├── simclient-integration/spec.md
    │   └── deployment/spec.md
    └── changes/
```

## Execution

### mp_simclient — Production Mode

```bash
python src/main.py
```

### mp_simclient — With CLI Arguments

The Orchestrator accepts command-line arguments to:

- Select specific SimBanks.
- Override config.json parameters.
- Activate debug/verbose mode.
- Execute scan only (no production).
- Select specific rows.

### mp_simclient — Scan Mode

Execute only the hardware scan without starting a production cycle:

```bash
python src/main.py --scan-only
```

## Logging

### Logging in mp_simclient

- **Framework**: Python standard `logging` module.
- **Levels**: DEBUG, INFO, WARNING, ERROR, CRITICAL.
- **Output**: Console (with colors via colorama) + log file.
- **Format**: Timestamp + level + module + message.

### Key Log Information

| Event | Level | Information |
|-------|-------|-------------|
| SIM switch | INFO | SimBank, column, row, result |
| Modem reboot | INFO | Port, model, result |
| CREG check | DEBUG | Port, CREG value, attempt # |
| Successful registration | INFO | Port, phone number, ICCID, time |
| Serial error | ERROR | Port, exception, retry attempt |
| Round start | INFO | Round #, rows to process, active modems |
| Round end | INFO | Statistics: successful/failed/total |
| CCID mismatch | WARNING | Port, expected vs found ICCID, diagnosis |
| SimClient kill/launch | INFO | PID, result |

## Monitoring

### Health Indicators

| Indicator | Normal Threshold | Action if Abnormal |
|-----------|------------------|-------------------|
| Registration rate (CREG) | > 70% of modems registered | Check SIMs, signal, antennas |
| CCID mismatches | < 5% | Check wiring, switch delays |
| Serial errors | < 2% of operations | Check USB cables, drivers |
| Round duration | ~30 min (cambio_fila_minutos) | Check timeouts, slow modems |
| SimClient crashes | 0 per round | Check compatibility, memory |

### State Files for Monitoring

Runtime-generated files serve as indicators:

- `slot_state.json` → Confirms SlotManager is rotating.
- `lista_pos.json` → Confirms count of operational SIMs.
- Scan CSV → Latest known data for each slot.

## Production Considerations

### Stability

- The system is designed for **continuous 24/7 operation**.
- Graceful Ctrl+C handling: closes ports, kills SimClient, saves state.
- Automatic retries for transient serial errors.
- Persisted state (slot_state.json) allows resuming after crashes.

### Scalability

- Adding SimBanks: Only requires updating `config.json` with new entries.
- Adding modems: Each SimBank supports up to 8 modems (8 columns).
- `max_workers` should be adjusted to the total number of modems.

### Maintenance

- **SIM replacement**: Physically replace SIMs in the SimBank, run a scan to update lista_pos.json.
- **Modem replacement**: Update config.json with new COM ports.
- **SimClient update**: Stop mp_simclient, update SimClient, restart.

## Relevant Source Files

- `requirements.txt` — Python dependencies.
- `config.json` — Primary configuration.
- `src/main.py` — Entry point and Orchestrator.
