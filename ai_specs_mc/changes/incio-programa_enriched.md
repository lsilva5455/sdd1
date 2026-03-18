# Task: incio-programa — Startup Banner and Info Display

## Completeness Assessment

| Criterion | Status | Notes |
|-----------|--------|-------|
| Objective | Complete | Signal bars ASCII art + colored info banner at startup |
| Scope | Complete | Console-only, integrated into `src/main.py` |
| Acceptance criteria | Complete | Defined below with all data fields confirmed |
| Technical context | Complete | Presentation layer, `main.py` entry point, new `banner.py` module |
| Dependencies | Complete | `colorama` for colored output, `config.json` for dynamic data |
| Edge cases | Complete | No color support, missing config, narrow terminal, redirected output |
| Testing strategy | Complete | Unit tests + manual verification |
| Impact analysis | Complete | Only `main.py` (add banner call) and new module |

**Overall Score: 8/8 criteria complete**

## Original Description

> Al iniciar el programa necesito que se genere un icono usando * como pixeles. Luego de eso un mensaje en varios colores indicando datos del programa, capacidad, hora, etc

## Enhanced Description

### Objective

Display an ASCII art **signal bars icon** (built with `*` characters as "pixels") and a colored information banner when the mp-core application starts. The banner should show program metadata using multiple colors via `colorama` to improve readability and give the system a professional startup identity.

### Scope

- **In scope**:
  - ASCII art signal bars icon rendered with `*` characters, printed to the console at startup
  - Colored text banner showing program information (see data fields below)
  - Integration into the existing startup flow in `src/main.py`
  - New `__version__` constant for the project
- **Out of scope**:
  - GUI splash screen or graphical window
  - Changes to the logging system (the banner is a one-time console print, not a log message)
  - Changes to the Flask API or frontend dashboards

### Affected Architecture Layers

- [ ] Domain (entities, value objects, repository ABCs)
- [ ] Application (services, validators)
- [ ] Infrastructure (DB repos, hardware adapters, serial communication)
- [x] Presentation — Console output (startup banner in `main.py` + dedicated `banner.py` module)
- [ ] Presentation — Flask API (blueprints, routes)
- [ ] Presentation — React Dashboard (components, hooks)
- [ ] Presentation — Streamlit Dashboard (pages, widgets)

### Acceptance Criteria

1. When `src/main.py` starts, an ASCII art **signal bars** icon made of `*` characters is printed to the console before any other output
2. Immediately after the icon, a colored information block is printed showing:
   - **Program name** (e.g., "mp-core")
   - **Version** (e.g., "v1.0.0" — new `__version__` constant)
   - **Current date and time** (timestamp at startup)
   - **Number of SimBanks** (dynamic from `config.json`)
   - **Number of modems** (dynamic from `config.json`)
   - **IP address** (server or SimBank IPs from config)
   - **Flask server port** (e.g., `:5000`)
   - **Platform/OS** (e.g., "Windows 10")
   - **Node** (e.g., "N99" — from config or environment)
3. The colored output works on Windows terminals (cmd, PowerShell, Windows Terminal) using `colorama`
4. If the terminal does not support colors, the banner still displays without colors (graceful fallback via `colorama.init()`)
5. The banner does not interfere with the existing logging configuration or Flask startup output
6. All data fields read dynamically from `config.json`; if config is unavailable, show "N/A" for those fields

### Edge Cases and Error Scenarios

1. **No color support**: Terminal without ANSI color support (e.g., older cmd.exe) — `colorama.init()` handles this; banner displays plain text without crashing
2. **Headless/redirected output**: If stdout is redirected to a file or pipe, colored escape codes should be stripped (`colorama.init(strip=True)` when not a TTY)
3. **Missing config**: If `config.json` is not yet loaded or missing at banner time — show "N/A" for dynamic fields (SimBanks, modems, IP, Node)
4. **Very narrow terminal**: ASCII art may wrap if terminal width is less than the art width — keep the signal bars art reasonably narrow (< 60 chars)

### Dependencies

- **Prerequisites**: None — this is a standalone visual feature
- **External libraries**: `colorama` — lightweight, Windows-compatible, enables ANSI colors on Windows
- **Affected components**:
  - `src/main.py` — add banner call at startup (before logging/Flask init)
  - New module: `src/utils/banner.py` (or `src/startup_banner.py`) — banner logic
  - `config.json` — read for dynamic capacity data

### Testing Strategy

- **Unit tests**: Test the banner generation function returns a string containing all expected data fields
- **Unit tests**: Test that the function handles missing config values gracefully (returns "N/A" for missing fields)
- **Unit tests**: Test the ASCII art constant is properly formatted (non-empty, uses `*` characters)
- **Manual verification**: Run `python src/main.py` and visually confirm the banner appears correctly with colors on Windows Terminal, PowerShell, and cmd.exe
- **Edge case test**: Verify output is clean when piped to a file (`python src/main.py > output.txt`)

### Implementation Notes

- Create a dedicated module (e.g., `src/utils/banner.py`) to keep `main.py` clean
- The ASCII art signal bars should be stored as a multi-line string constant
- Create a `__version__ = "1.0.0"` constant (in `src/__init__.py` or `src/version.py`)
- Call the banner function as the first action in `main.py` before logging setup or Flask initialization
- Use `colorama.init(autoreset=True)` for Windows compatibility
- Follow the project's English convention for all new code, variable names, and comments
- Use different `colorama.Fore` colors to distinguish data categories (e.g., green for name/version, cyan for system info, yellow for capacity)

## Resolved Questions

1. **Icon shape**: Signal bars (cellular signal strength icon)
2. **Data fields**: Program name, version, date/time, SimBanks count, modem count, IP address, Flask port, platform/OS, Node (e.g., N99)
3. **Data source**: Dynamic from `config.json`, with "N/A" fallback
4. **Color library**: `colorama`
5. **Version string**: Create new `__version__ = "1.0.0"` constant
