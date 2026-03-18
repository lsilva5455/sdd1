# Development Guide

This guide provides step-by-step instructions for setting up the development environment and running the mp-core system.

## Prerequisites

Ensure you have the following installed:
- **Python 3.8+** (3.10+ recommended)
- **pip** (Python package manager)
- **Git**
- **PostgreSQL 14+** (native or via Docker)
- **Node.js 18+** and **npm** (for React dashboards only)

### Windows-Specific Requirements
- USB serial port drivers for Quectel modems (EC25/UC20)
- COM port access permissions
- pyserial-compatible USB-to-serial adapters

## 1. Clone the Repository

```bash
git clone <repository-url>
cd mp-core
```

## 2. Environment Configuration

Create a `.env` file in the project root:

```env
# Database Configuration
DATABASE_URL=postgresql://user:password@localhost:5432/db1

# Application Configuration
FLASK_APP=src/main.py
FLASK_ENV=development
FLASK_PORT=5000
SECRET_KEY=your-secret-key-here

# Hardware Configuration (optional, can also use config.json)
# SERIAL_BAUD_RATE=115200
# SCAN_TIMEOUT=30
```

## 3. Database Setup (PostgreSQL)

### Option A: Native PostgreSQL
```bash
# Create the database
psql -U postgres -c "CREATE DATABASE db1;"
psql -U postgres -c "CREATE USER mp_user WITH PASSWORD 'your_password';"
psql -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE db1 TO mp_user;"
```

### Option B: Docker
```bash
docker run -d \
  --name mp-postgres \
  -e POSTGRES_DB=db1 \
  -e POSTGRES_USER=mp_user \
  -e POSTGRES_PASSWORD=your_password \
  -p 5432:5432 \
  postgres:14
```

### Apply Migrations (if using Alembic)
```bash
alembic upgrade head
```

## 4. Backend Setup (Python)

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install development dependencies
pip install -r requirements-dev.txt

# Run the Flask API server
flask --app src/main:app run --debug --port 5000
```

The backend API will be available at `http://localhost:5000`

### Running the Hardware Orchestrator
```bash
# For production cycle (requires hardware access)
python src/main.py

# For scanning mode
python src/main.py --scan
```

## 5. Frontend Setup (React Dashboards)

```bash
cd frontend

# Install dependencies
npm install

# Start the development server
npm start
```

The React dashboard will be available at `http://localhost:3000`

## 6. Streamlit Dashboards

```bash
# Run the main Streamlit dashboard
streamlit run streamlit_apps/app.py

# Run a specific page directly
streamlit run streamlit_apps/pages/1_scan_viewer.py
```

The Streamlit dashboard will be available at `http://localhost:8501`

## Testing

### Backend Testing (pytest)

```bash
# Run all tests
pytest

# Run tests with coverage
pytest --cov=src --cov-report=html

# Run tests in watch mode (requires pytest-watch)
ptw

# Run specific test file
pytest tests/unit/domain/test_pool.py

# Run tests matching a pattern
pytest -k "test_should_activate"

# Run with verbose output
pytest -v
```

### Frontend Testing (React)

```bash
cd frontend

# Run unit tests
npm test

# Run tests with coverage
npm run test -- --coverage
```

### Linting and Type Checking

```bash
# Python linting and formatting
ruff check src/ tests/
ruff format src/ tests/

# Python type checking
mypy src/

# React linting
cd frontend && npx eslint src/
```

## Project Structure Overview

```
sdd1/
├── src/                        # Python backend source
│   ├── main.py                 # Application entry point & orchestrator (monolithic)
│   ├── hardware_controller.py  # SimController — serial port & AT command control
│   ├── data_manager.py         # DataManager — scanning, CSV, data persistence
│   ├── slot_logic.py           # SlotManager — circular slot rotation
│   ├── ccid_analyzer.py        # CCIDAnalyzer — CCID validation & carrier detection
│   ├── logger_config.py        # Logging configuration (file + console)
│   ├── reset_imei_all.py       # Legacy IMEI reset script (standalone)
│   ├── config/
│   │   └── config_manager.py   # ConfigManager — loads config.json
│   ├── hardware/               # [SCAFFOLD] Future DDD hardware layer
│   ├── models/                 # [SCAFFOLD] Future DDD domain models
│   ├── orchestration/          # [SCAFFOLD] Future DDD orchestration layer
│   └── utils/                  # [SCAFFOLD] Future DDD utilities
├── tests/                      # pytest test suite
├── openspec/                   # OpenSpec capability specifications
├── ai_specs_mc/                # AI agent specs and standards
├── utils/                      # External utilities
│   └── json_sadmin_mp_simclient/  # dict_nodo → config.json converter
├── legacy/                     # Legacy documentation
├── config.json                 # Hardware topology configuration
├── requirements.txt            # Python production dependencies
├── .env                        # Environment variables (not committed)
├── Instalar_mps.bat            # Installation script (Windows)
├── Iniciar_mps.bat             # Start script (Windows)
└── Continuar_mps.bat           # Resume script (Windows)
```

> **Note:** The `src/` directory currently has a **monolithic architecture** — most production logic lives in a few large files (`main.py`, `hardware_controller.py`, `data_manager.py`, `slot_logic.py`). The subdirectories (`hardware/`, `models/`, `orchestration/`, `utils/`) are **scaffold stubs** prepared for a future DDD refactoring. See `backend-standards.mdc` for the target architecture.
