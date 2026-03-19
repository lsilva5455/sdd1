# Task: incio-programa — Startup Banner and Info Display

## Completeness Assessment

| Criterion | Status | Notes |
|-----------|--------|-------|
| Objective | Complete | Signal bars ASCII art + colored info banner at startup |
| Scope | Complete | Console-only, integrated into `src/main.py` entry point |
| Acceptance criteria | Complete | 6 measurable criteria defined with all data fields confirmed |
| Technical context | Complete | Presentation layer, `main.py` Orchestrator entry point, new `banner.py` module, `config.json` as data source |
| Dependencies | Complete | `colorama` (already in `requirements.txt`), `config.json` for dynamic data |
| Edge cases | Complete | No color support, missing config, narrow terminal, redirected output |
| Testing strategy | Complete | Unit tests + manual verification |
| Impact analysis | Complete | `src/main.py` (add banner call before Orchestrator init) and new module |

**Overall Score: 8/8 criteria complete**

## Original Description

> Al iniciar el programa necesito que se genere un icono usando * como pixeles. Luego de eso un mensaje en varios colores indicando datos del programa, capacidad, hora, etc

## Enhanced Description

### Objective

Display an ASCII art **signal bars icon** (built with `*` characters as "pixels") and a colored information banner when the mp-core application starts. The banner should show program metadata using multiple colors via `colorama` to improve readability and give the system a professional startup identity.

This banner will be the first visual output when `python src/main.py` is executed, before the Orchestrator begins its production cycle (kill SimClient → init SimBanks → open ports → etc.).

### Scope

- **In scope**:
  - ASCII art signal bars icon rendered with `*` characters, printed to the console at startup
  - Colored text banner showing program information (see data fields below)
  - Integration into the existing startup flow in `src/main.py` (before Orchestrator initialization)
  - New `__version__` constant for the project
- **Out of scope**:
  - GUI splash screen or graphical window
  - Changes to the logging system or `logger_config.py` (the banner is a one-time console print, not a log message)
  - Changes to the Flask API, React dashboard, or Streamlit dashboards
  - Changes to the production cycle or Orchestrator logic

### Affected Architecture Layers

- [ ] Domain (entities, value objects, repository ABCs)
- [ ] Application (services, validators)
- [ ] Infrastructure (DB repos, hardware adapters, serial communication)
- [x] Presentation — Console output (startup banner in `main.py` + dedicated `banner.py` module)
- [ ] Presentation — Flask API (blueprints, routes)
- [ ] Presentation — React Dashboard (components, hooks)
- [ ] Presentation — Streamlit Dashboard (pages, widgets)

### Acceptance Criteria

1. When `src/main.py` starts, an ASCII art **signal bars** icon made of `*` characters is printed to the console before any other output (before Orchestrator init, before logging setup)
2. Immediately after the icon, a colored information block is printed showing all the fields listed below
3. The colored output works on Windows terminals (cmd, PowerShell, Windows Terminal) using `colorama`
4. If the terminal does not support colors, the banner still displays without colors (graceful fallback via `colorama.init()`)
5. The banner does not interfere with the existing logging configuration (`logger_config.py`) or Flask startup output
6. All dynamic data fields read from `config.json`; if config is unavailable at banner time, show "N/A" for those fields

### Data Fields to Display

| Field | Source | Example Value |
|-------|--------|---------------|
| Program name | Hardcoded constant | `mp-core` |
| Version | New `__version__` constant | `v1.0.0` |
| Current date and time | `datetime.now()` | `2026-03-18 14:30:00` |
| Number of SimBanks | Dynamic from `config.json` → `len(config["simbanks"])` | `2` |
| Number of modems | Dynamic from `config.json` → sum of modems across all SimBanks | `16` |
| SIM rows per SimBank | Dynamic from `config.json` → `config["filas"]` | `16` |
| Total SIM capacity | Calculated: SimBanks × columns(8) × rows | `256` |
| IP address | Server IP or SimBank IPs from config/environment | `192.168.1.10` |
| Flask server port | From config or default | `:5000` |
| Platform/OS | `platform.system()` + `platform.release()` | `Windows 10` |
| Node | From config or environment variable | `N99` |

**Note on config.json structure**: The actual `config.json` uses an array format for SimBanks (not the dict format shown in some specs). Each SimBank has a `control_port` and a `modems` array with `port` and `col` fields. The banner must parse this correctly:

```json
{
  "simbanks": [
    {
      "control_port": "COM19",
      "modems": [
        {"port": "COM4", "col": "01"},
        {"port": "COM3", "col": "02"},
        ...
      ]
    }
  ],
  "filas": 16
}
```

So:
- SimBanks count = `len(config["simbanks"])` → 2
- Modems count = sum of `len(sb["modems"])` for each SimBank → 16
- Total SIM capacity = SimBanks × 8 columns × `config["filas"]` rows → 2 × 8 × 16 = 256

### Edge Cases and Error Scenarios

1. **No color support**: Terminal without ANSI color support (e.g., older cmd.exe) — `colorama.init()` handles this; banner displays plain text without crashing
2. **Headless/redirected output**: If stdout is redirected to a file or pipe, colored escape codes should be stripped (`colorama` handles this with `strip=True` when not a TTY)
3. **Missing config.json**: If `config.json` is not found or not yet loaded at banner time — show "N/A" for all dynamic fields (SimBanks, modems, capacity, Node). The banner should never crash the program.
4. **Malformed config.json**: If the JSON is valid but missing expected keys (e.g., no `simbanks` key) — handle with `dict.get()` and show "N/A"
5. **Very narrow terminal**: ASCII art may wrap if terminal width is less than the art width — keep the signal bars art reasonably narrow (< 60 chars wide)
6. **Node not defined**: If there is no "node" field in `config.json` or environment — show "N/A"

### Dependencies

- **Prerequisites**: None — this is a standalone visual feature that runs before the production cycle
- **External libraries**: `colorama` — already listed in `requirements.txt` per `openspec/specs/deployment/spec.md`. Lightweight, Windows-compatible, enables ANSI colors on Windows
- **Standard library**: `datetime`, `platform`, `json`, `os`
- **Affected components**:
  - `src/main.py` — add banner call at startup, before Orchestrator init and logging setup
  - New module: `src/utils/banner.py` — banner generation logic
  - New constant: `__version__ = "1.0.0"` in `src/version.py` or `src/__init__.py`
  - `config.json` — read for dynamic capacity data (SimBanks, modems, rows, node)

### Testing Strategy

- **Unit tests** (`tests/test_banner.py`):
  - Test the banner generation function returns a string containing all expected data fields (program name, version, date, SimBanks count, modems count, etc.)
  - Test that the function handles missing config gracefully (returns "N/A" for missing fields)
  - Test that the function handles malformed config (missing keys) without crashing
  - Test the ASCII art constant is properly formatted (non-empty, uses `*` characters, width < 60 chars)
  - Test with a sample `config.json` fixture that mirrors the real structure (array-based SimBanks)
- **Manual verification**:
  - Run `python src/main.py` and visually confirm the banner appears correctly with colors on Windows Terminal, PowerShell, and cmd.exe
  - Verify the banner data matches the actual `config.json` values (2 SimBanks, 16 modems, 256 capacity)
- **Edge case tests**:
  - Verify output is clean when piped to a file (`python src/main.py > output.txt` — no ANSI escape codes in file)
  - Verify banner works when `config.json` is temporarily renamed/missing

### Implementation Notes

- Create `src/utils/banner.py` as the dedicated module. The `src/utils/` directory already exists with `__init__.py`.
- The ASCII art signal bars should be stored as a multi-line string constant (e.g., `SIGNAL_BARS_ART`)
- Create `src/version.py` with `__version__ = "1.0.0"` — imported by banner and potentially by other modules later
- Call the banner function as the **first action** in `main.py`, before `logger_config` setup, before Orchestrator initialization, before `config.json` loading. The banner should load `config.json` independently (simple `json.load()`) since `ConfigManager` may not be initialized yet.
- Use `colorama.init(autoreset=True)` for Windows compatibility
- Use different `colorama.Fore` colors to distinguish data categories. Suggested color scheme:
  - Cyan: ASCII art icon
  - Green: program name and version
  - Yellow: capacity data (SimBanks, modems, SIM capacity)
  - White: system info (date, OS, IP, port)
  - Magenta: Node identifier
- Follow the project's English convention for all new code, variable names, and comments (per `base-standards.mdc`)
- All code must use type hints (per `base-standards.mdc`)
- The banner function should be a pure function: `def print_startup_banner(config_path: str = "config.json") -> None`
