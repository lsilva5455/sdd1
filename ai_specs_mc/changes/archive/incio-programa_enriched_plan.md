# Implementation Plan: incio-programa — Startup Banner and Info Display

## Overview

Add a startup banner to the mp-core application that displays an ASCII art signal bars icon (using `*` characters) and a colored information block with program metadata when `python src/main.py` is executed. This is a presentation-layer-only change that introduces a new utility module (`src/utils/banner.py`), a version constant (`src/version.py`), and a single call in `src/main.py`.

**Architecture principles**: This feature follows DDD layered architecture — it lives entirely in the presentation/utility layer and has no impact on domain, application, or infrastructure layers. It follows clean architecture by keeping the banner logic in a dedicated module, separate from the Orchestrator.

## Architecture Context

- **Layers involved**: Presentation (console output only)
- **Components/files affected**:
  - `src/version.py` — **NEW** — project version constant
  - `src/utils/banner.py` — **NEW** — banner generation and display logic
  - `src/main.py` — **MODIFY** — add banner call as first action
  - `tests/test_banner.py` — **NEW** — unit tests for banner module
- **Backend/frontend**: Backend only (console output at startup)

## Implementation Steps

### Step 0: Create Feature Branch

- **Action**: Create and switch to a new feature branch
- **Branch Naming**: `feature/incio-programa`
- **Implementation Steps**:
  1. Ensure you're on the latest `main` branch
  2. Pull latest changes: `git pull origin main`
  3. Create new branch: `git checkout -b feature/incio-programa`
  4. Verify branch creation: `git branch`
- **Notes**: This must be the FIRST step before any code changes.

### Step 1: Create Version Module

- **File**: `src/version.py` (NEW)
- **Action**: Create a single-file module with the project version constant
- **Implementation Steps**:
  1. Create `src/version.py` with a single constant:
     ```python
     """Project version constant for mp-core."""

     __version__: str = "1.0.0"
     ```
  2. This module will be imported by `banner.py` and can be reused elsewhere (Flask API, logs, etc.)
- **Dependencies**: None (standard Python)
- **Implementation Notes**: 
  - Use type hint on the constant (`str`)
  - Keep the module minimal — only the version string
  - English docstring

### Step 2: Create Banner Module

- **File**: `src/utils/banner.py` (NEW)
- **Action**: Create the startup banner module with ASCII art and colored info display
- **Function Signatures**:
  ```python
  SIGNAL_BARS_ART: str  # Multi-line constant with the ASCII art

  def _load_config(config_path: str) -> dict[str, Any]:
      """Load config.json safely, returning empty dict on failure."""
      ...

  def _get_system_info() -> dict[str, str]:
      """Gather platform, IP address, and other system information."""
      ...

  def _extract_capacity_info(config: dict[str, Any]) -> dict[str, str]:
      """Extract SimBanks count, modem count, rows, and total capacity from config."""
      ...

  def print_startup_banner(config_path: str = "config.json") -> None:
      """Print the startup banner with ASCII art and colored system information."""
      ...
  ```
- **Implementation Steps**:
  1. Define `SIGNAL_BARS_ART` as a multi-line string constant using `*` characters to form signal bars. Keep width under 60 characters. Example shape:
     ```
              *
           *  *
        *  *  *
     *  *  *  *
     *  *  *  *
     ```
  2. Implement `_load_config(config_path)`:
     - Use `json.load()` to read the file
     - Wrap in try/except for `FileNotFoundError`, `json.JSONDecodeError`
     - Return empty `{}` on any failure (never crash)
  3. Implement `_get_system_info()`:
     - Use `platform.system()` and `platform.release()` for OS
     - Use `socket.gethostbyname(socket.gethostname())` for IP address (wrap in try/except, fallback to "N/A")
     - Return a dict with keys: `"platform"`, `"ip_address"`
  4. Implement `_extract_capacity_info(config)`:
     - Parse the **array-based** SimBanks structure from `config.json`:
       ```python
       simbanks = config.get("simbanks", [])
       simbank_count = len(simbanks)
       modem_count = sum(len(sb.get("modems", [])) for sb in simbanks)
       rows = config.get("filas", "N/A")
       ```
     - Calculate total capacity: `simbank_count * 8 * rows` (if rows is int, else "N/A")
     - Extract node: `config.get("node", os.environ.get("MP_NODE", "N/A"))`
     - Extract Flask port: `config.get("flask_port", "5000")`
     - Return dict with keys: `"simbanks"`, `"modems"`, `"rows"`, `"capacity"`, `"node"`, `"flask_port"`
  5. Implement `print_startup_banner(config_path)`:
     - Call `colorama.init(autoreset=True)` at the start
     - Print `SIGNAL_BARS_ART` in `Fore.CYAN`
     - Load config via `_load_config(config_path)`
     - Gather system info via `_get_system_info()`
     - Extract capacity via `_extract_capacity_info(config)`
     - Import and display `__version__` from `src.version`
     - Print each field with its designated color:
       - `Fore.GREEN`: program name ("mp-core") and version
       - `Fore.YELLOW`: capacity data (SimBanks, modems, rows, total capacity)
       - `Fore.WHITE`: system info (date/time, OS, IP, Flask port)
       - `Fore.MAGENTA`: Node identifier
     - Use `datetime.now().strftime("%Y-%m-%d %H:%M:%S")` for timestamp
     - Print a separator line at the end (e.g., `"=" * 50`)
- **Dependencies**:
  - `colorama` (Fore, init)
  - `json`, `os`, `platform`, `socket`, `datetime` (standard library)
  - `src.version` (__version__)
- **Implementation Notes**:
  - All private helpers prefixed with `_` per PEP 8
  - All functions fully type-hinted
  - English docstrings on every function
  - The config loading is independent from `ConfigManager` — simple `json.load()` because `ConfigManager` may not be initialized yet at banner time
  - `colorama.init(autoreset=True)` ensures colors reset after each print, avoiding color leaking into subsequent logging output
  - Handle the real `config.json` structure: `simbanks` is an **array** of objects with `control_port` and `modems` (array of `{"port": "COMx", "col": "0x"}`)

### Step 3: Integrate Banner into main.py

- **File**: `src/main.py` (MODIFY)
- **Action**: Add banner call as the very first action in the module's execution flow
- **Implementation Steps**:
  1. Add import at the top of `main.py` (after existing imports):
     ```python
     from utils.banner import print_startup_banner
     ```
  2. Find the entry point at the bottom of `main.py` (the `if __name__ == "__main__":` block or wherever the Orchestrator is instantiated)
  3. Add `print_startup_banner()` as the **first call** before any other initialization:
     ```python
     if __name__ == "__main__":
         print_startup_banner()  # Display startup banner
         # ... existing Orchestrator initialization code ...
     ```
- **Dependencies**: `src.utils.banner`
- **Implementation Notes**:
  - The banner call must come BEFORE `setup_logger()`, before `ConfigManager()`, before `Orchestrator()` init
  - Only 2 lines changed in `main.py` (1 import + 1 function call) — minimal impact
  - If `main.py` uses `sys.path.insert` to add `src/` to path (it does, at line 19), the import `from utils.banner import print_startup_banner` will work correctly

### Step 4: Write Unit Tests

- **File**: `tests/test_banner.py` (NEW)
- **Action**: Create comprehensive unit tests for the banner module
- **Implementation Steps**:
  1. Create test fixtures:
     ```python
     @pytest.fixture
     def sample_config() -> dict:
         """Sample config matching real config.json structure."""
         return {
             "simbanks": [
                 {
                     "control_port": "COM19",
                     "modems": [
                         {"port": "COM4", "col": "01"},
                         {"port": "COM3", "col": "02"},
                     ]
                 },
                 {
                     "control_port": "COM20",
                     "modems": [
                         {"port": "COM11", "col": "01"},
                         {"port": "COM12", "col": "02"},
                     ]
                 }
             ],
             "filas": 16,
             "node": "N99"
         }

     @pytest.fixture
     def sample_config_file(tmp_path, sample_config) -> str:
         """Write sample config to a temp file and return its path."""
         config_file = tmp_path / "config.json"
         config_file.write_text(json.dumps(sample_config))
         return str(config_file)
     ```
  2. Test `_load_config`:
     - `test_should_load_valid_config_when_file_exists` — reads real JSON correctly
     - `test_should_return_empty_dict_when_file_not_found` — missing file returns `{}`
     - `test_should_return_empty_dict_when_json_invalid` — malformed JSON returns `{}`
  3. Test `_extract_capacity_info`:
     - `test_should_extract_correct_counts_from_valid_config` — 2 SimBanks, 4 modems, 16 rows, capacity = 256
     - `test_should_return_na_when_config_empty` — all fields "N/A"
     - `test_should_return_na_when_simbanks_key_missing` — handles missing keys
  4. Test `_get_system_info`:
     - `test_should_return_platform_info` — returns non-empty platform string
     - `test_should_return_ip_address` — returns a string for IP
  5. Test `SIGNAL_BARS_ART`:
     - `test_signal_bars_art_should_not_be_empty` — constant is not empty
     - `test_signal_bars_art_should_contain_asterisks` — contains `*` characters
     - `test_signal_bars_art_width_should_be_under_60_chars` — max line width < 60
  6. Test `print_startup_banner`:
     - `test_should_print_banner_without_crashing(sample_config_file, capsys)` — runs without error, captured output contains "mp-core"
     - `test_should_print_banner_with_missing_config(capsys)` — runs with nonexistent path, output contains "N/A"
- **Dependencies**: `pytest`, `json`, `unittest.mock`
- **Implementation Notes**:
  - Follow AAA pattern (Arrange-Act-Assert)
  - Use `capsys` fixture to capture stdout for `print_startup_banner` tests
  - Use `tmp_path` fixture for temporary config files
  - Test naming: `test_should_[expected]_when_[condition]`
  - Mock `socket.gethostbyname` in tests where network may not be available

### Step 5: Verify Quality

- **Action**: Run quality checks to ensure the implementation meets project standards
- **Implementation Steps**:
  1. Run tests: `pytest tests/test_banner.py -v`
  2. Run tests with coverage: `pytest tests/test_banner.py --cov=src/utils/banner --cov-report=term-missing`
  3. Run linter: `ruff check src/utils/banner.py src/version.py tests/test_banner.py`
  4. Run formatter: `ruff format src/utils/banner.py src/version.py tests/test_banner.py`
  5. Run type checker: `mypy src/utils/banner.py src/version.py`
  6. Manual verification: `python src/main.py` — visually confirm banner appears with colors

### Step 6: Update Technical Documentation

- **Action**: Review and update technical documentation according to changes made
- **Implementation Steps**:
  1. **Review Changes**: New files (`version.py`, `banner.py`), modified file (`main.py`)
  2. **Identify Documentation Files**:
     - `openspec/specs/deployment/spec.md` — update directory structure to include `version.py` and `utils/banner.py`
     - `README.md` — update Source Code Layout section to mention `banner.py` and `version.py`
  3. **Update Documentation**:
     - Add `src/version.py` and `src/utils/banner.py` to the directory trees in deployment spec and README
     - Note that the banner uses `colorama` (already documented in deployment spec dependencies)
  4. **Verify Documentation**: Confirm all new files are reflected in the directory structures
- **References**:
  - Follow process described in `ai_specs_mc/specs/documentation-standards.mdc`
  - All documentation must be written in English
- **Notes**: This step is MANDATORY before considering the implementation complete.

## Implementation Order

1. **Step 0**: Create feature branch `feature/incio-programa`
2. **Step 1**: Create `src/version.py` with `__version__` constant
3. **Step 2**: Create `src/utils/banner.py` with ASCII art and colored info display
4. **Step 3**: Integrate banner call into `src/main.py`
5. **Step 4**: Write unit tests in `tests/test_banner.py`
6. **Step 5**: Run quality checks (pytest, ruff, mypy)
7. **Step 6**: Update technical documentation

## Testing Checklist

- [ ] `test_should_load_valid_config_when_file_exists` passes
- [ ] `test_should_return_empty_dict_when_file_not_found` passes
- [ ] `test_should_return_empty_dict_when_json_invalid` passes
- [ ] `test_should_extract_correct_counts_from_valid_config` passes
- [ ] `test_should_return_na_when_config_empty` passes
- [ ] `test_should_return_na_when_simbanks_key_missing` passes
- [ ] `test_should_return_platform_info` passes
- [ ] `test_should_return_ip_address` passes
- [ ] `test_signal_bars_art_should_not_be_empty` passes
- [ ] `test_signal_bars_art_should_contain_asterisks` passes
- [ ] `test_signal_bars_art_width_should_be_under_60_chars` passes
- [ ] `test_should_print_banner_without_crashing` passes
- [ ] `test_should_print_banner_with_missing_config` passes
- [ ] Coverage for `src/utils/banner.py` >= 80%
- [ ] `ruff check` passes with no errors
- [ ] `mypy` passes with no errors
- [ ] Manual: banner displays correctly with colors on Windows Terminal
- [ ] Manual: banner shows correct data from `config.json` (2 SimBanks, 16 modems, 256 capacity)
- [ ] Manual: banner shows "N/A" when `config.json` is missing

## Dependencies

| Package | Type | Purpose | Status |
|---------|------|---------|--------|
| `colorama` | pip | Colored console output on Windows | Already in `requirements.txt` |
| `pytest` | pip (dev) | Unit testing | Already in `requirements.txt` |
| `ruff` | pip (dev) | Linting and formatting | Project standard |
| `mypy` | pip (dev) | Static type checking | Project standard |

No new dependencies needed.

## Notes

- **Minimal impact**: Only 2 lines added to `main.py` (1 import + 1 call). All logic is in the new `banner.py` module.
- **Config loading independence**: The banner loads `config.json` via `json.load()` directly, not through `ConfigManager`, because `ConfigManager` is not yet initialized at banner time.
- **config.json array format**: The real `config.json` uses `"simbanks": [{"control_port": "COM19", "modems": [...]}]` (array), not the dict format shown in some OpenSpec specs. The implementation must handle this correctly.
- **Color safety**: `colorama.init(autoreset=True)` resets colors after each print, preventing color leakage into subsequent log messages from `logger_config.py`.
- **English only**: All new code, comments, docstrings, and variable names must be in English per `base-standards.mdc`.
- **Type hints required**: All functions must have full type annotations per `base-standards.mdc`.

## Next Steps After Implementation

1. Commit changes with descriptive message following project conventions
2. Create pull request from `feature/incio-programa` to `main`
3. Consider future enhancements:
   - Add `--no-banner` CLI flag to suppress banner output
   - Add `__version__` to Flask API response headers
   - Add more dynamic data (uptime, last scan timestamp, etc.)

## Implementation Verification

- [ ] **Code Quality**: `ruff check` and `mypy` pass without errors
- [ ] **Functionality**: Banner prints correctly with all data fields and colors
- [ ] **Testing**: All 13 unit tests pass, coverage >= 80% for `banner.py`
- [ ] **Integration**: Banner appears before Orchestrator init in `main.py`, no interference with logging
- [ ] **Documentation**: `deployment/spec.md` and `README.md` updated with new files
