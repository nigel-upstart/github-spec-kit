# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Spec Kit is a Python CLI tool and framework for **Spec-Driven Development (SDD)** - an approach where specifications become executable and directly generate working implementations rather than just guiding them. This inverts traditional development where code was king; here, specifications drive code generation via AI.

Key concepts:
- Specifications as the primary artifact and source of truth
- Implementation plans derived from specifications
- Code generation from detailed plans
- Feature branches (001-feature-name format) for iterative development

## Core Commands

### Development Commands
```bash
# Run the CLI directly
uv run src/specify_cli/__init__.py <command>

# Install and use globally
uv tool install .
specify <command>

# Development installation
uv sync
```

### Build and Package
```bash
# Run tests (check for test files/commands in project)
# No explicit test command found - search for test files or pytest config

# Build package
uv build

# Install locally for testing
uv tool install --editable .
```

## Architecture and Structure

### Python CLI Tool (`src/specify_cli/`)
- **Main CLI**: `__init__.py` - Typer-based CLI with commands:
  - `specify init <project-name>` - Initialize new Spec-Driven projects
  - `specify check` - Verify required tools (git, claude, gemini, code, cursor)
- **Rich UI**: Interactive selection, progress tracking, step visualization
- **Template Management**: Downloads and extracts project templates from GitHub releases

### Template System (`templates/`)
- **Command Templates**: `/specify`, `/tasks` commands for different AI assistants
- **Prompt Templates**: User-facing prompt templates for Claude Code workflows
- **Spec Template**: Structured specification format with execution flow
- **Plan Template**: Implementation planning template (used via Claude Code plan mode)
- **Tasks Template**: Task breakdown format

### Scripts (`scripts/bash/` and `scripts/powershell/`)
- **Branch Management**: Feature branch validation (001-feature-name format)
- **Path Management**: Automatic path resolution for specs, plans, tasks
- **Project Setup**: Repository initialization and configuration

### Memory System (`memory/`)
- **Constitution**: Project-specific principles and constraints (templated)
- **Constitution Checklist**: Validation and update procedures

## Development Workflow

### Feature Development Pattern
1. **Specification** (`/specify`): Create detailed specs in `specs/001-feature-name/spec.md`
2. **Planning** (Claude Code plan mode): Generate implementation plans in `specs/001-feature-name/plan.md`
3. **Tasks** (`/tasks`): Break down into actionable tasks
4. **Implementation**: AI generates code from specifications and plans

### File Organization
- Feature branches follow `001-feature-name` convention
- Each feature gets its own directory under `specs/`
- Core files per feature: `spec.md`, `plan.md`, `tasks.md`, `research.md`
- Optional: `data-model.md`, `quickstart.md`, `contracts/` directory

### Branch Workflow
- Features developed on numbered branches (001-, 002-, etc.)
- Scripts automatically detect feature branch and set up paths
- Common functions in `scripts/bash/common.sh` for path management

## Spec-Kit Planning Workflow

When asked to plan a feature implementation, use Claude Code's native plan mode:

### Planning Process
1. **Enter plan mode** (automatic when analyzing specs or via `claude --permission-mode plan`)
2. **Load specification** from `specs/[branch]/spec.md`
3. **Generate Development Specification**: Present recommended technology choices:
   - Language/Version (e.g., Python 3.11, TypeScript 5.0)
   - Primary Dependencies (e.g., FastAPI, React, Express)
   - Storage (e.g., PostgreSQL, Redis, filesystem)
   - Testing Framework (e.g., pytest, Jest, vitest)
   - Target Platform (e.g., Linux server, browser, mobile)
   - Performance Goals (e.g., 1000 req/s, <200ms p95)
   - Constraints (e.g., memory limits, offline capability)
4. **Wait for user approval** of technology choices before proceeding
5. **Apply constitution checks** from `memory/constitution.md`
6. **Execute plan template phases**:
   - **Phase 0**: Research (generate `research.md`)
   - **Phase 1**: Design (generate `data-model.md`, `contracts/`, `quickstart.md`)
   - **Phase 2**: Task planning approach (describe only, don't create `tasks.md`)
7. **Use ExitPlanMode** to present complete plan for approval

### Prompt Templates
Users can reference `templates/prompts/plan-prompt.md` for:
- **Option 1**: Provide specific technology choices
- **Option 2**: Let Claude suggest and verify technology choices

### Generated Artifacts
Following the plan template structure from `templates/plan-template.md`:
- **Development Specification**: Verified technology stack and constraints
- **research.md**: Research findings for unclear aspects
- **data-model.md**: Entity definitions and relationships
- **contracts/**: API contracts and specifications
- **quickstart.md**: Step-by-step validation procedures
- **Complete Implementation Plan**: With constitution checks and task approach

The planning follows spec-kit constitutional principles: TDD, library-first architecture, simplicity, and proper testing strategies.

## Important Implementation Notes

### Cross-Platform Support
- Supports both bash/zsh (`.sh`) and PowerShell (`.ps`) script variants
- Uses `readchar` for cross-platform keyboard input
- Conditional execute permissions setting on POSIX systems only

### AI Assistant Integration
- Templates generated per AI assistant: `claude`, `gemini`, `copilot`, `cursor`
- Each assistant has specific command templates and workflows
- Agent tool verification unless `--ignore-agent-tools` used

### Network and Security
- Uses `truststore` for SSL/TLS verification
- Optional `--skip-tls` flag for testing (not recommended)
- GitHub API integration for template downloads with error handling

### Rich Terminal UI
- Step tracking with tree visualization (no emojis)
- Interactive arrow-key selection menus
- Live progress updates during operations
- Color-coded status indicators

## Common Development Tasks

### Adding New CLI Commands
1. Add command function to `src/specify_cli/__init__.py` using `@app.command()`
2. Follow existing patterns for Rich UI and error handling
3. Use StepTracker for multi-step operations

### Extending Template System
1. Add templates to appropriate directories under `templates/`
2. Update download logic if new asset patterns needed
3. Consider both bash and PowerShell variants

### Modifying Script Workflows
1. Common functions go in `scripts/bash/common.sh`
2. Feature-specific scripts follow existing path resolution patterns
3. Maintain cross-platform compatibility

## Dependencies and Requirements

- **Python 3.11+** (specified in pyproject.toml)
- **Core Dependencies**: typer, rich, httpx[socks], platformdirs, readchar, truststore
- **External Tools**: git (recommended), AI assistant CLIs (claude, gemini, etc.)
- **Build System**: Hatchling

## Testing and Quality

- Currently no explicit test framework configured
- CLI includes built-in tool checking (`specify check`)
- Integration testing happens through template initialization and project setup
- Error handling includes debug modes and detailed error reporting