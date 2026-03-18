# Hardware Topology

## Overview

Defines the physical topology of the SIM card control system: SimBanks, serial control ports, Quectel modems, and the logical mapping between columns, rows, and physical ports. This specification is the foundation upon which all other layers operate.

## Key Concepts

### SimBank

A physical device containing a matrix of SIM card slots organized in **rows** and **columns**. Each SimBank connects to the server via a **serial control port** (e.g., COM19, COM20).

- Each SimBank manages **8 columns** (columns 1–8).
- Each column is linked to a **Quectel modem** (EC25 or UC20) connected via its own serial port.
- Each SimBank has **16 rows** of SIMs (configurable via the `filas` parameter).
- Total capacity per SimBank: 8 columns x 16 rows = **128 SIM slots**.

### Quectel Modem

Cellular modems, models **EC25** and **UC20**, connected via USB and exposing serial ports. Each modem has:
- A **serial port** (e.g., COM3, COM5, COM7...).
- An assigned **column** within a specific SimBank.
- A communication **baudrate** of **115200**.

### Column-to-Modem Mapping

Each entry in the SimBank configuration maps a column (1–8) to a modem serial port:

```
SimBank COM19:
  column 1 → COM3
  column 2 → COM5
  column 3 → COM7
  column 4 → COM9
  column 5 → COM11
  column 6 → COM13
  column 7 → COM15
  column 8 → COM17

SimBank COM20:
  column 1 → COM23
  column 2 → COM25
  column 3 → COM27
  column 4 → COM29
  column 5 → COM31
  column 6 → COM33
  column 7 → COM35
  column 8 → COM37
```

### Control Port vs Modem Port

- **Control port** (`pool_com`): Serial port connected to the SimBank. Used to send SIM switching AT commands (AT+SWIT, AT+CWSIM, AT+NEXT00).
- **Modem port** (`slot_com`): Serial port connected to each individual Quectel modem. Used for cellular communication (AT+CREG, AT+CCID, AT+CFUN, etc.).

### Rows and Columns

- **Row**: Vertical position in the SimBank (1–16). All columns share the same row simultaneously — row switching is **global** per SimBank.
- **Column**: Horizontal position (1–8). Each column corresponds to an independent physical modem.
- **Slot**: Intersection of a row and a column. Identifies a specific SIM card in the SimBank.

## Data Structures

### config.json — mp_simclient Format

```json
{
  "simbanks": {
    "COM19": {
      "columns": {
        "1": "COM3",
        "2": "COM5",
        "3": "COM7",
        "4": "COM9",
        "5": "COM11",
        "6": "COM13",
        "7": "COM15",
        "8": "COM17"
      }
    },
    "COM20": {
      "columns": {
        "1": "COM23",
        "2": "COM25",
        "3": "COM27",
        "4": "COM29",
        "5": "COM31",
        "6": "COM33",
        "7": "COM35",
        "8": "COM37"
      }
    }
  }
}
```

### dict_nodo.json — Legacy Format (mapeo_pool)

Alternative format used by mapeo_pool where the primary key is the `pool_com` (SimBank control port) and contains an array of `slot_com` (modem ports):

```json
{
  "COM19": ["COM3", "COM5", "COM7", "COM9", "COM11", "COM13", "COM15", "COM17"],
  "COM20": ["COM23", "COM25", "COM27", "COM29", "COM31", "COM33", "COM35", "COM37"]
}
```

### Format Conversion

A converter exists at `utils/json_sadmin_mp_simclient/convert_dict_to_config.py` that transforms `dict_nodo.json` into mp_simclient's `config.json` format.

## Topological Diagram

```
Windows Server
├── SimBank [COM19] ──────────────────────────────┐
│   ├── Col 1 → Quectel Modem [COM3]  ← active row SIM
│   ├── Col 2 → Quectel Modem [COM5]  ← active row SIM
│   ├── Col 3 → Quectel Modem [COM7]  ← active row SIM
│   ├── Col 4 → Quectel Modem [COM9]  ← active row SIM
│   ├── Col 5 → Quectel Modem [COM11] ← active row SIM
│   ├── Col 6 → Quectel Modem [COM13] ← active row SIM
│   ├── Col 7 → Quectel Modem [COM15] ← active row SIM
│   └── Col 8 → Quectel Modem [COM17] ← active row SIM
│   └── [16 SIM rows per column]
│
├── SimBank [COM20] ──────────────────────────────┐
│   ├── Col 1 → Quectel Modem [COM23] ← active row SIM
│   ├── Col 2 → Quectel Modem [COM25] ← active row SIM
│   ├── Col 3 → Quectel Modem [COM27] ← active row SIM
│   ├── Col 4 → Quectel Modem [COM29] ← active row SIM
│   ├── Col 5 → Quectel Modem [COM31] ← active row SIM
│   ├── Col 6 → Quectel Modem [COM33] ← active row SIM
│   ├── Col 7 → Quectel Modem [COM35] ← active row SIM
│   └── Col 8 → Quectel Modem [COM37] ← active row SIM
│   └── [16 SIM rows per column]
│
└── SimClient (third-party software) ← connects to modems via serial
```

## Constraints

- **Global switching per SimBank**: The AT+SWIT command switches the SIM in ONE column of ONE SimBank. However, AT+CWSIM/AT+NEXT00 affect all columns of the SimBank simultaneously.
- **One modem = one active SIM**: Each modem can only have one active SIM at a time (the one from the currently selected row in its column).
- **SWIT command serialization**: AT+SWIT commands must be serialized with a global lock (`_swit_global_lock`) and a minimum delay of **1 second** between sends to avoid bus collisions in the SimBank.
- **Fixed baudrate**: All serial ports operate at **115200 baud**.
- **Modem models**: The system supports EC25 and UC20. The model is auto-detected via AT command and affects the reboot method (EC25: CFUN=0→1, UC20: CFUN=1,1).

## SIM Identification

### ICCID and Carriers

SIM cards are identified by their ICCID. Chilean carriers are identified by prefix:
- `895609` → **WOM**
- `895601` → **ENTEL**
- `895603` → **CLARO**
- `895602` → **MOVISTAR**

### SIM Lifecycle

SIM cards follow a lifecycle defined by their usage state:
- **Virgin**: New SIM, not yet activated.
- **3M**: SIM with 3 months of usage.
- **7M**: SIM with 7 months of usage.
- **Dead**: Exhausted SIM, no commercial value.

## Relevant Source Files

- `config.json` — Current topology configuration.
- `src/hardware_controller.py` — SimController (hardware access).
- `utils/json_sadmin_mp_simclient/convert_dict_to_config.py` — Format converter.
- `legacy/mapeo_pool_documentacion/ESTRUCTURA_DICT_NODO.md` — dict_nodo.json format documentation.
