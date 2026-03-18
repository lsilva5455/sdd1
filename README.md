# mp-core: AI Specifications & Development Rules

Development standards, AI agent configurations, and spec-driven workflows for the **mp-core** project -- a SIM card hardware control and pool management system (SimBanks, Quectel modems, AT commands, slot management, SimClient lifecycle).

This setup combines two systems:
- **ai_specs_mc/** -- Development standards, AI agents, and task-based commands (adapted from [LIDR ai-specs](https://github.com/LIDR-academy/ai-specs))
- **openspec/** -- Spec-Driven Development with [OpenSpec](https://github.com/Fission-AI/OpenSpec) for architectural capability specs

Both integrate with multiple AI copilots (Claude, Cursor, GitHub Copilot, Gemini) via stub files and naming conventions.

## Repository Structure

```
.
├── ai_specs_mc/                     # Development standards and AI configurations
│   ├── specs/                       # Technical standards
│   │   ├── base-standards.mdc       # Core rules (single source of truth)
│   │   ├── backend-standards.mdc    # Python / Flask / pytest patterns
│   │   ├── frontend-standards.mdc   # React + Streamlit conventions
│   │   ├── documentation-standards.mdc
│   │   ├── development_guide.md     # Setup guide (Python/pip/venv/Windows)
│   │   └── api-spec.yml             # OpenAPI specification
│   ├── .commands/                   # Reusable command prompts
│   │   ├── enrich-task.md           # Evaluate and enrich a task description
│   │   ├── plan-task.md             # Generate implementation plan
│   │   ├── develop.md               # Implement a task end-to-end
│   │   ├── commit.md                # Commit workflow
│   │   ├── explain.md               # Explain code
│   │   ├── meta-prompt.md           # Meta-prompt generation
│   │   └── update-docs.md           # Update documentation
│   ├── .agents/                     # Agent role definitions
│   │   ├── fullstack-developer.md   # Unified developer agent (Python + React/Streamlit)
│   │   └── product-strategy-analyst.md  # Product analysis agent
│   └── changes/                     # Task files and implementation plans
│       └── archive/                 # Completed/archived task files
│
├── openspec/                        # Spec-Driven Development (OpenSpec)
│   ├── config.yaml                  # Project config (mp-core)
│   ├── specs/                       # 10 capability specifications
│   │   ├── hardware-topology/       # SimBanks, ports, column-to-modem mapping
│   │   ├── hardware-control/        # AT commands, SimController, retry_serial
│   │   ├── slot-management/         # Circular rotation, slot_state.json
│   │   ├── orchestration/           # Production cycle, PortState, barriers
│   │   ├── data-scanning/           # DataManager, parallel scanning, CSV
│   │   ├── pool-visualization/      # Flask API, React frontend, modem grid
│   │   ├── session-management/      # PostgreSQL, pool sessions, JSONB snapshots
│   │   ├── configuration/           # config.json, dict_nodo.json
│   │   ├── simclient-integration/   # SimClient launch/kill, model detection
│   │   └── deployment/              # Directory structure, CLI, logs, monitoring
│   └── changes/                     # OpenSpec change proposals
│       └── archive/                 # Archived completed changes
│
├── .claude/                         # Claude/Claude Code configuration
│   ├── agents/                      # Stub files -> ../ai_specs_mc/.agents/
│   └── commands/                    # Stub files -> ../ai_specs_mc/.commands/
│
├── .cursor/                         # Cursor configuration
│   ├── agents/                      # Stub files -> ../ai_specs_mc/.agents/
│   ├── commands/                    # Stub files -> ../ai_specs_mc/.commands/
│   └── rules/
│       └── use-base-rules.mdc       # Points to ../ai_specs_mc/specs/base-standards.mdc
│
├── .github/                         # GitHub Copilot / OpenSpec prompts
│   ├── prompts/                     # opsx-propose, opsx-apply, opsx-explore, opsx-archive
│   └── skills/                      # OpenSpec skill definitions
│
├── AGENTS.md                        # Generic agent config -> ai_specs_mc/specs/base-standards.mdc
├── CLAUDE.md                        # Claude config -> ai_specs_mc/specs/base-standards.mdc
├── GEMINI.md                        # Gemini config -> ai_specs_mc/specs/base-standards.mdc
└── codex.md                         # GitHub Copilot config -> ai_specs_mc/specs/base-standards.mdc
```

## Source Code Layout (`src/`)

The production code uses a **monolithic architecture**. Scaffold subdirectories exist for a future DDD refactoring but are not yet wired into production.

```
src/
├── main.py                  # Orchestrator & entry point (~2000 lines)
├── version.py               # Project version constant (__version__)
├── hardware_controller.py   # SimController — serial ports, AT commands (~740 lines)
├── data_manager.py          # DataManager — scanning, CSV, persistence (~1730 lines)
├── slot_logic.py            # SlotManager — circular slot rotation (~525 lines)
├── ccid_analyzer.py         # CCIDAnalyzer — CCID validation & carrier detection
├── logger_config.py         # Logging configuration (file + console)
├── reset_imei_all.py        # Legacy IMEI reset script (standalone)
├── config/
│   └── config_manager.py    # ConfigManager — loads config.json
├── hardware/                # [SCAFFOLD] Future hardware abstraction layer
├── models/                  # [SCAFFOLD] Future domain models
├── orchestration/           # [SCAFFOLD] Future orchestration services
└── utils/
    ├── __init__.py           # Package init
    └── banner.py             # Startup banner — ASCII art and system info display
```

## Multi-Copilot Support

The root config files (`AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `codex.md`) all reference the same core rules in `ai_specs_mc/specs/base-standards.mdc`. Each AI tool finds its configuration using its preferred naming convention.

The `.claude/` and `.cursor/` directories contain **stub files** (single-line text files with a relative path) that point to the actual agent/command definitions in `ai_specs_mc/`. This avoids duplication while maintaining compatibility with each tool's expected directory structure.

| Copilot | Config file | Agent/command discovery |
|---------|------------|----------------------|
| Claude / Claude Code | `CLAUDE.md` | `.claude/agents/`, `.claude/commands/` |
| Cursor | -- | `.cursor/agents/`, `.cursor/commands/`, `.cursor/rules/` |
| GitHub Copilot | `codex.md` | `.github/prompts/`, `.github/skills/` |
| Gemini | `GEMINI.md` | `AGENTS.md` |

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Hardware control | Python, pyserial, threading |
| Backend API | Flask |
| Large dashboards | React |
| Small dashboards / prototyping | Streamlit |
| Database | PostgreSQL |
| Testing | pytest (backend), Jest + RTL (frontend) |
| Linting | ruff, mypy |
| Platform | Windows |

## Development Workflows

This project has **two workflow systems** for different purposes:

| Use case | Workflow | Artifacts location |
|----------|---------|-------------------|
| Day-to-day implementation tasks | **Task-based** (ai_specs_mc commands) | `ai_specs_mc/changes/` |
| Architectural changes affecting capability specs | **OpenSpec proposals** | `openspec/changes/<name>/` |

---

### Workflow A: Task-Based Development (ai_specs_mc)

Use this for concrete implementation work: new endpoints, bug fixes, new views, refactors, feature additions.

The pipeline is: **create task file -> enrich -> plan -> develop -> archive**

#### Step 1: Create the Task File

Create a markdown file in `ai_specs_mc/changes/` describing what you want to do. The name is your task identifier.

```
ai_specs_mc/changes/add-modem-status-endpoint.md
```

The content can be informal -- the enrichment step will structure it. At minimum, include:

```markdown
# Add Modem Status Endpoint

## Objective
Create a REST endpoint that returns the current status of all connected modems.

## Context
Currently there is no way to query modem status without connecting
directly via serial port. The pool visualization needs this data.

## Acceptance Criteria
- GET /api/modems returns a list of modems with their status
- If a modem does not respond to the AT command, it appears as "offline"
- Response includes port, model, and ICCID for each modem
```

#### Step 2: Enrich the Task

Run the `enrich-task` command with the task file name (without the `.md` extension):

```
/enrich-task add-modem-status-endpoint
```

The command reads your task file, evaluates it against 8 completeness criteria (objective, scope, acceptance criteria, technical context, dependencies, edge cases, testing strategy, impact analysis), and generates an enriched version:

```
ai_specs_mc/changes/add-modem-status-endpoint_enriched.md
```

The enriched file includes:
- Completeness score (e.g., "5/8 criteria complete")
- Gaps identified and flagged with `[TO BE DEFINED]`
- Architecture layer mapping (domain, application, infrastructure, presentation)
- Edge cases and error scenarios
- Testing strategy
- Open questions that need answers before implementation

**When to skip this step:** If your task description is already detailed with clear acceptance criteria, technical context, and edge cases.

#### Step 3: Plan the Implementation

```
/plan-task add-modem-status-endpoint_enriched
```

Generates a step-by-step implementation plan:

```
ai_specs_mc/changes/add-modem-status-endpoint_enriched_plan.md
```

The plan includes:
- Architecture context (affected DDD layers and components)
- Ordered implementation steps (domain -> application -> infrastructure -> presentation)
- Testing checklist
- Error handling strategy
- Dependencies

#### Step 4: Implement

```
/develop add-modem-status-endpoint_enriched
```

The AI follows the plan and:
1. Creates a feature branch (`feature/add-modem-status-endpoint`)
2. Implements each layer following DDD and project standards
3. Writes tests (pytest for backend, Jest+RTL for frontend)
4. Runs quality checks (ruff, mypy)
5. **Updates documentation** (mandatory — per `documentation-standards.mdc`, always before commit)
6. Commits with a descriptive message
7. Pushes and creates a pull request

#### Step 5: Archive Completed Task

Once the task is fully implemented, tested, committed, and pushed (or PR merged), move all task files to the archive:

```bash
# Move completed task files to archive
mv ai_specs_mc/changes/scan-ccid-validation*.md ai_specs_mc/changes/archive/
```

This keeps `ai_specs_mc/changes/` clean — only active/in-progress tasks remain at the top level. Completed tasks are preserved in `archive/` for reference.

#### Complete Example

```
# 1. Write your task (informal is fine)
# Create: ai_specs_mc/changes/scan-ccid-validation.md

# 2. Enrich it
/enrich-task scan-ccid-validation

# 3. Review the enriched file, answer any open questions, then plan
/plan-task scan-ccid-validation_enriched

# 4. Implement
/develop scan-ccid-validation_enriched

# 5. Archive completed task files
mv ai_specs_mc/changes/scan-ccid-validation*.md ai_specs_mc/changes/archive/
```

#### Available Commands Reference

| Command | Purpose | Input | Output |
|---------|---------|-------|--------|
| `/enrich-task <id>` | Evaluate and enrich a task description | `ai_specs_mc/changes/<id>.md` | `<id>_enriched.md` |
| `/plan-task <id>` | Generate implementation plan | `ai_specs_mc/changes/<id>.md` | `<id>_plan.md` |
| `/develop <id>` | Implement task end-to-end | `ai_specs_mc/changes/<id>.md` | Code, tests, PR |
| `/commit` | Commit following project conventions | Staged changes | Git commit |
| `/explain` | Explain code in detail | Code reference | Explanation |
| `/update-docs` | Update project documentation | -- | Updated docs |
| `/meta-prompt` | Generate optimized prompts | Prompt draft | Refined prompt |

#### Available Agents

| Agent | Purpose |
|-------|---------|
| `fullstack-developer` | Unified developer agent for Python (Flask, pyserial, threading), React, and Streamlit. Follows DDD and clean architecture. |
| `product-strategy-analyst` | Analyzes product ideas, identifies use cases, develops value propositions. Outputs analysis to `ai_specs_mc/changes/analysis/`. |

---

### Workflow B: OpenSpec Proposals

Use this for changes that affect the **architectural capability specs** -- e.g., redesigning how hardware topology works, adding a new capability, changing the orchestration pattern.

OpenSpec manages 10 capability specs in `openspec/specs/` and uses a structured proposal workflow:

```
opsx-explore  (think and investigate)
  -> opsx-propose  (create proposal.md + design.md + tasks.md)
     -> opsx-apply  (implement the tasks)
        -> opsx-archive  (archive the completed change)
```

#### When to Use OpenSpec vs. Task Files

| Signal | Use OpenSpec | Use Task File |
|--------|-------------|--------------|
| Changes a capability spec in `openspec/specs/` | Yes | -- |
| Adds a new system capability | Yes | -- |
| Concrete feature / endpoint / view | -- | Yes |
| Bug fix | -- | Yes |
| Refactor within existing architecture | -- | Yes |
| Exploratory / not sure yet | `opsx-explore` | -- |

#### OpenSpec Proposal Steps

1. **Explore** (optional): `opsx-explore` to think through the idea
2. **Propose**: `opsx-propose <change-name>` creates `openspec/changes/<change-name>/` with:
   - `proposal.md` -- what and why
   - `design.md` -- how (technical design)
   - `tasks.md` -- implementation steps with checkboxes
3. **Apply**: `opsx-apply <change-name>` implements the tasks
4. **Archive**: `opsx-archive <change-name>` archives to `openspec/changes/archive/`

---

## Core Development Principles

All development follows the standards defined in `ai_specs_mc/specs/base-standards.mdc`:

1. **Small tasks, one at a time** -- baby steps, never skip ahead
2. **Test-Driven Development (TDD)** -- write failing tests first
3. **Type safety** -- fully typed Python code (type hints, mypy)
4. **Clear naming** -- descriptive variables and functions
5. **English preferred** -- new code, comments, documentation in English; Spanish acceptable in existing code and domain terms
6. **90%+ test coverage** -- comprehensive testing across all layers
7. **Incremental changes** -- focused, reviewable modifications
8. **DDD and clean architecture** -- domain, application, infrastructure, presentation layers
9. **SOLID, DRY, KISS** -- standard software engineering principles

### Standards Files

| File | Scope |
|------|-------|
| `ai_specs_mc/specs/base-standards.mdc` | Core architecture principles, conventions, DDD layers |
| `ai_specs_mc/specs/backend-standards.mdc` | Python / Flask / pyserial / threading / pytest patterns |
| `ai_specs_mc/specs/frontend-standards.mdc` | React (large dashboards) + Streamlit (small dashboards) |
| `ai_specs_mc/specs/documentation-standards.mdc` | Documentation structure and maintenance |
| `ai_specs_mc/specs/development_guide.md` | Environment setup (Python, pip, venv, Windows) |

## Customization

### Adapting Standards

1. **Core rules**: Edit `ai_specs_mc/specs/base-standards.mdc` (single source of truth)
2. **Backend/frontend patterns**: Edit the respective `*-standards.mdc` files
3. **Agents**: Modify or add agents in `ai_specs_mc/.agents/`
4. **Commands**: Modify or add commands in `ai_specs_mc/.commands/`
5. **Capability specs**: Edit or add specs in `openspec/specs/`

### Adding a New Agent or Command

1. Create the file in `ai_specs_mc/.agents/` or `ai_specs_mc/.commands/`
2. Create stub files in `.claude/` and `.cursor/` with the relative path:
   ```
   ../ai_specs_mc/.commands/my-new-command.md
   ```
3. For GitHub Copilot, add a prompt in `.github/prompts/` if needed

### Maintaining Standards

- **Single source of truth**: always update `base-standards.mdc` first
- **Version control**: track changes to standards like code
- **Keep examples current**: update documentation when patterns change

## Origin

This setup is adapted from the [LIDR ai-specs](https://github.com/LIDR-academy/ai-specs) project (MIT License, LIDR.co). The original was designed for team-based Node.js/TypeScript/Express/Prisma development with Jira integration. It has been refactored for:

- Solo developer workflow (no Jira, no SCRUM ceremonies)
- Python tech stack (Flask, pyserial, threading, pytest, ruff)
- SIM card hardware control domain (SimBanks, Quectel modems, AT commands)
- Local markdown task files instead of ticket systems
- Unified fullstack agent (instead of separate backend/frontend agents)
- Integration with OpenSpec for spec-driven development
