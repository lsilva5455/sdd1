# Session Management

## Overview

Specifies the pool session management system, implemented in mapeo_pool over PostgreSQL (`db1`). Records pool state history, production sessions, and modem grid snapshots. This system is **95% implemented but DEACTIVATED** — the hooks in the code are commented out, pending `db1` database configuration.

## Database — PostgreSQL db1

### Schema

The `db1` database contains three main tables:

### Table: pools_registry

Master registry of pools (hardware nodes). Each pool represents a server with connected SimBanks.

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL PK | Unique identifier |
| pool_name | VARCHAR UNIQUE | Pool name (e.g., "nodo-santiago-01") |
| created_at | TIMESTAMP | Creation date |
| config | JSONB | Pool configuration (dict_nodo.json) |
| status | VARCHAR | Current status (active/inactive/maintenance) |

### Table: pool_sessions

Production session records. Each time mp_simclient starts a production cycle, a session is created.

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL PK | Unique identifier |
| pool_id | INTEGER FK | Reference to pools_registry |
| session_name | VARCHAR | Descriptive session name |
| started_at | TIMESTAMP | Session start time |
| ended_at | TIMESTAMP | Session end time (null if active) |
| status | VARCHAR | Status (running/completed/failed/aborted) |
| metadata | JSONB | Additional metadata (config snapshot, etc.) |

### Table: pool_grid_snapshots

Periodic snapshots of the modem grid state. Stores the complete state of all modems at a given point in time as JSONB.

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL PK | Unique identifier |
| session_id | INTEGER FK | Reference to pool_sessions |
| captured_at | TIMESTAMP | Capture timestamp |
| grid_data | JSONB | Complete grid state |

### JSONB grid_data Structure

```json
{
  "simbanks": {
    "COM19": {
      "modems": {
        "COM3": {
          "status": "registered",
          "phone": "56912345678",
          "iccid": "8956091234567890123",
          "operator": "WOM",
          "creg": 1,
          "csq": 18,
          "row": 3
        },
        "COM5": {
          "status": "unregistered",
          "phone": null,
          "iccid": "8956011234567890123",
          "operator": "ENTEL",
          "creg": 0,
          "csq": 5,
          "row": 3
        }
      }
    },
    "COM20": {
      "modems": { }
    }
  },
  "timestamp": "2025-12-15T14:30:00Z",
  "active_row": 3
}
```

## Data Retention

- **Retention period**: **45 days**.
- **Cleanup**: Daily cleanup task that deletes snapshots older than 45 days.
- **Completed sessions**: Kept in `pool_sessions` as history.
- **Orphan sessions**: Sessions without `ended_at` that are older than 24 hours are marked as `aborted`.

## Session Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/pools/<pool_name>/session/<session_name>` | Get session data |
| GET | `/api/pools/<pool_name>/sessions` | List sessions for a pool |
| GET | `/api/pools/<pool_name>/session/<session_name>/snapshots` | Get session snapshots |

## Session Flow

```
1. mp_simclient starts production cycle
   │
   ├── (hook) INSERT INTO pool_sessions (started_at, status='running')
   │
2. Each production round generates a snapshot
   │
   ├── (hook) INSERT INTO pool_grid_snapshots (grid_data=JSONB)
   │
3. mp_simclient completes the cycle
   │
   ├── (hook) UPDATE pool_sessions SET ended_at=NOW(), status='completed'
   │
4. Daily cleanup
   │
   └── DELETE FROM pool_grid_snapshots WHERE captured_at < NOW() - INTERVAL '45 days'
```

## Implementation Status

| Component | Status |
|-----------|--------|
| SQL Schema (CREATE TABLE) | Defined |
| Hooks in mp_simclient | **COMMENTED OUT** (code exists but deactivated) |
| Flask endpoints | Implemented |
| React frontend (session consumption) | Implemented |
| Daily cleanup task | Defined |
| db1 connection configuration | **PENDING** |

### Current Blocker

The entire session system is blocked by the lack of PostgreSQL `db1` configuration:
- The database connection string is not configured.
- The tables have not been created in production.
- The hooks in the source code are commented out with `# TODO: pending db1 setup`.

### To Activate

1. Install and configure PostgreSQL on the server.
2. Create the `db1` database.
3. Run the table creation scripts (CREATE TABLE).
4. Configure the connection string in mapeo_pool configuration.
5. Uncomment the hooks in mp_simclient code.
6. Enable the daily cleanup task (cron job or scheduler).

## Relevant Source Files

- `legacy/mapeo_pool_documentacion/SISTEMA_POOLS_IMPLEMENTACION.md` — Full pool pages system documentation (SQL schema, endpoints, hooks).
