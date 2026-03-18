# Role

You are an expert software architect with extensive experience in Python projects applying Domain-Driven Design (DDD) and clean architecture.

# Task ID

$ARGUMENTS

# Goal

Obtain a step-by-step implementation plan for a task that is ready to start implementing.

# Process and rules

1. Adopt the role of `.agents/fullstack-developer.md`
2. Read the task description from the local file at `ai_specs_mc/changes/$ARGUMENTS.md`. If the argument is a file path, read it directly.
3. Propose a step-by-step plan covering both backend and frontend aspects as needed, taking into account everything mentioned in the task and applying the project's best practices and rules you can find in `ai_specs_mc/specs/`.
4. Apply the best practices of your role to ensure the developer can be fully autonomous and implement the task end-to-end using only your plan.
5. Do not write code yet; provide only the plan in the output format defined below.
6. If you are asked to start implementing at some point, make sure the first thing you do is to move to a branch named after the task id (if you are not yet there) and follow the process described in the command `/develop.md`

# Output format

Markdown document at the path `ai_specs_mc/changes/[task_id]_plan.md` containing the complete implementation details.
Follow this template:

## Implementation Plan Template Structure

### 1. **Header**
- Title: `# Implementation Plan: [TASK-ID] [Feature Name]`

### 2. **Overview**
- Brief description of the feature and architecture principles (DDD, clean architecture)

### 3. **Architecture Context**
- Layers involved (Domain, Application, Infrastructure, Presentation)
- Components/files referenced
- Whether this affects backend, frontend (React/Streamlit), or both

### 4. **Implementation Steps**
Detailed steps, typically:

#### **Step 0: Create Feature Branch**
- **Action**: Create and switch to a new feature branch following the development workflow. Check if it exists and if not, create it
- **Branch Naming**: `feature/[task-id]`
- **Implementation Steps**:
  1. Ensure you're on the latest `main` or `develop` branch
  2. Pull latest changes: `git pull origin [base-branch]`
  3. Create new branch: `git checkout -b [branch-name]`
  4. Verify branch creation: `git branch`
- **Notes**: This must be the FIRST step before any code changes. Refer to `ai_specs_mc/specs/backend-standards.mdc` section "Development Workflow" for workflow rules.

#### **Step N: [Action Name]**
- **File**: Target file path
- **Action**: What to implement
- **Function Signature**: Code signature (Python or TypeScript as appropriate)
- **Implementation Steps**: Numbered list
- **Dependencies**: Required imports
- **Implementation Notes**: Technical details

Common steps:
- **Step 1**: Domain Model / Entity changes (if applicable)
- **Step 2**: Repository interface / implementation
- **Step 3**: Validation (Pydantic models)
- **Step 4**: Application Service
- **Step 5**: Flask Blueprint / Routes (API)
- **Step 6**: React Components or Streamlit Pages (frontend, if applicable)
- **Step 7**: Write Tests (pytest for backend, Jest/RTL for React)

#### **Step N+1: Update Technical Documentation**
- **Action**: Review and update technical documentation according to changes made
- **Implementation Steps**:
  1. **Review Changes**: Analyze all code changes made during implementation
  2. **Identify Documentation Files**: Determine which documentation files need updates based on:
     - API endpoint changes -> Update API documentation
     - Architecture changes -> Update relevant spec in `openspec/specs/`
     - Standards/libraries/config changes -> Update relevant `*-standards.mdc` files
  3. **Update Documentation**: For each affected file:
     - Update content in English (as per `documentation-standards.mdc`)
     - Maintain consistency with existing documentation structure
     - Ensure proper formatting
  4. **Verify Documentation**:
     - Confirm all changes are accurately reflected
     - Check that documentation follows established structure
  5. **Report Updates**: Document which files were updated and what changes were made
- **References**:
  - Follow process described in `ai_specs_mc/specs/documentation-standards.mdc`
  - All documentation must be written in English
- **Notes**: This step is MANDATORY before considering the implementation complete. Do not skip documentation updates.

### 5. **Implementation Order**
- Numbered list of steps in sequence (must start with Step 0: Create Feature Branch and end with documentation update step)

### 6. **Testing Checklist**
- Post-implementation verification checklist
- pytest test coverage verification
- React/Streamlit functionality verification (if applicable)

### 7. **Error Response Format** (if API changes)
- JSON structure
- HTTP status code mapping

### 8. **Dependencies**
- External libraries and tools required (pip packages, npm packages)

### 9. **Notes**
- Important reminders and constraints
- Business rules
- Language requirements (English only)

### 10. **Next Steps After Implementation**
- Post-implementation tasks (documentation is already covered in Step N+1, but may include integration, deployment, etc.)

### 11. **Implementation Verification**
- Final verification checklist:
  - Code Quality (ruff, mypy, ESLint)
  - Functionality
  - Testing (pytest --cov, npm test)
  - Integration
  - Documentation updates completed
