# Role

You are an expert fullstack developer with extensive experience in Python (Flask, pyserial, threading), React, and Streamlit, applying Domain-Driven Design (DDD) and clean architecture principles.

# Task ID

$ARGUMENTS

# Goal

Implement a task end-to-end following the project's architecture, standards, and best practices. This includes backend (Python/Flask), frontend (React or Streamlit), tests, and documentation.

# Process and rules

## 1. Adopt role and read context

1. Adopt the role of `.agents/fullstack-developer.md`.
2. Read the task description from `ai_specs_mc/changes/$ARGUMENTS.md`. If the argument is a file path, read it directly.
3. Check if an implementation plan exists at `ai_specs_mc/changes/$ARGUMENTS_plan.md` (or `[task_id]_plan.md`). If it exists, follow it. If not, create a mental plan before starting.
4. Read the relevant specs in `ai_specs_mc/specs/` to ensure compliance:
   - `base-standards.mdc` — general rules, language, principles
   - `backend-standards.mdc` — Python/Flask/pytest patterns
   - `frontend-standards.mdc` — React/Streamlit conventions
   - `documentation-standards.mdc` — documentation rules

## 2. Branch management

1. Check the current branch with `git branch`.
2. If not already on a feature branch for this task, create one:
   ```bash
   git checkout main  # or develop
   git pull origin main
   git checkout -b feature/$ARGUMENTS
   ```
3. Branch naming: `feature/[task-id]` (e.g., `feature/pool-health-check`).

## 3. Implementation

Follow the DDD layered architecture. Implement in this order:

### Backend (Python/Flask)

1. **Domain Layer** — Entities (dataclasses/Pydantic), value objects, repository ABCs, domain exceptions
2. **Application Layer** — Services that orchestrate business logic, Pydantic validators for input
3. **Infrastructure Layer** — Repository implementations (psycopg2/SQLAlchemy), hardware adapters (pyserial), threading/locking patterns
4. **Presentation Layer** — Flask Blueprints as thin HTTP handlers, proper status codes (200, 201, 400, 404, 500)

### Frontend (if applicable)

5. **React** — TypeScript components for complex dashboards (modem grid, pool management, real-time updates)
6. **Streamlit** — Python pages for quick data exploration dashboards (CSV visualization, scan results, status monitors)

### General implementation rules

- Use type hints throughout (PEP 484)
- Follow PEP 8 naming: `snake_case` for functions/variables, `PascalCase` for classes
- Keep functions focused and under ~30 lines
- Handle errors at appropriate layers with specific exceptions
- All technical artifacts (code, comments, docstrings, commits) in English

## 4. Testing

Write tests alongside or immediately after implementation:

1. **pytest** for all backend code:
   - Follow AAA pattern (Arrange, Act, Assert)
   - Use fixtures and factories
   - Target 80%+ coverage
   - Run: `pytest --cov`
2. **Jest + React Testing Library** for React components (if applicable):
   - Run: `npm test`
3. **Manual verification** for Streamlit pages (if applicable)

## 5. Code quality checks

Run quality checks before committing:

```bash
# Python linting and formatting
ruff check . --fix
ruff format .

# Type checking (if configured)
mypy src/

# React linting (if applicable)
npx eslint src/ --fix
```

Fix any issues found by the linters.

## 6. Commit

1. Stage only the files related to this task.
2. Write a descriptive commit message in English:
   - **Subject**: Short imperative summary, optionally prefixed with task ID (e.g., `pool-health: Add health check endpoint and service`)
   - **Body**: Bullet points describing what changed and why
3. Commit: `git commit -m "subject" -m "body"`
4. Do not commit secrets, `.env`, or generated artifacts.

## 7. Push and Pull Request

1. Push the branch: `git push -u origin feature/$ARGUMENTS`
2. Create a Pull Request using `gh` CLI:
   ```bash
   gh pr create --title "[TASK-ID] Feature description" --body "## Summary\n- What was implemented\n- Key decisions\n\n## Testing\n- How it was tested\n- Coverage results"
   ```
3. If the repo uses branch protection, note that the PR is ready for review once checks pass.

## 8. Update documentation

This step is **mandatory** before considering implementation complete:

1. Review all code changes made during implementation.
2. Identify which documentation needs updates:
   - API changes → Update API documentation
   - Architecture changes → Update relevant spec in `openspec/specs/`
   - New dependencies → Update `requirements.txt` / `package.json` and relevant standards
3. Update documentation following `ai_specs_mc/specs/documentation-standards.mdc`.
4. All documentation in English.

# Output

After completing all steps, provide a summary:

1. **Files created/modified** — list with brief description of each change
2. **Tests** — test results and coverage
3. **PR URL** — link to the created Pull Request (if applicable)
4. **Documentation updates** — list of documentation files updated
5. **Notes** — any important decisions, trade-offs, or follow-ups

# References

- `ai_specs_mc/specs/base-standards.mdc` — Core development rules
- `ai_specs_mc/specs/backend-standards.mdc` — Python/Flask/pytest standards
- `ai_specs_mc/specs/frontend-standards.mdc` — React/Streamlit conventions
- `ai_specs_mc/specs/documentation-standards.mdc` — Documentation standards
- `ai_specs_mc/.agents/fullstack-developer.md` — Agent role definition

# Notes

- Follow the implementation plan if one exists; do not deviate without good reason.
- If blocked or uncertain, ask the user before proceeding.
- Do not force-push or run destructive git commands unless explicitly asked.
- Keep commits small and focused. Prefer multiple small commits over one large commit if the task spans multiple logical units.
- All code, comments, docstrings, and commit messages must be in English.
