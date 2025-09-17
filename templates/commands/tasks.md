---
description: Generate native Claude Code tasks with phase-based orchestration for the feature based on available design artifacts.
scripts:
  sh: scripts/bash/check-task-prerequisites.sh --json
  ps: scripts/powershell/check-task-prerequisites.ps1 -Json
---

Given the context provided as an argument, do this:

1. Run `{SCRIPT}` from repo root and parse FEATURE_DIR and AVAILABLE_DOCS list. All paths must be absolute.

2. Load and analyze available design documents:
   - Always read plan.md for tech stack and libraries
   - IF EXISTS: Read data-model.md for entities
   - IF EXISTS: Read contracts/ for API endpoints
   - IF EXISTS: Read research.md for technical decisions
   - IF EXISTS: Read quickstart.md for test scenarios

   Note: Not all projects have all documents. For example:
   - CLI tools might not have contracts/
   - Simple libraries might not need data-model.md
   - Generate tasks based on what's available

3. **IMPORTANT: Create native TodoWrite tasks instead of markdown files**
   - Use the native Claude Code task system via TodoWrite
   - Parse the implementation plan to extract:
     * Technology stack (Python/FastAPI, TypeScript/React, etc.)
     * Project structure (CLI, web app, mobile, etc.)
     * Available design artifacts

4. Generate phase-based task structure:
   * **Phase 3.1: Setup** - Project init, dependencies, linting
   * **Phase 3.2: Tests First (TDD)** - Contract tests, integration tests (all parallel)
   * **Phase 3.3: Core Implementation** - Models, services, endpoints, validation
   * **Phase 3.4: Integration** - Database, middleware, logging, security
   * **Phase 3.5: Polish** - Unit tests, performance, documentation

5. Task generation rules:
   - Each contract file → contract test task marked [P]
   - Each entity in data-model → model creation task marked [P]
   - Each endpoint → implementation task (sequential if shared files)
   - Each user story → integration test marked [P]
   - Different files = parallel [P]
   - Same file = sequential (no [P])

6. **Launch enhanced sub-agent orchestration with task-level parallelism:**
   - Create TodoWrite tasks for high-level phase tracking
   - Calculate time estimates for each phase and task sequence
   - Use intelligent scheduling with proper dependency ordering (topological sort)
   - Launch sub-agents at optimal granularity:
     * **Phase-level sub-agents** for phases that can run concurrently
     * **Task-sequence sub-agents** for parallel task groups within phases
     * **Sequential task sequences** that must run in order
   - Provide rich context to each sub-agent including:
     * Phase/sequence description and specific tasks
     * Dependency requirements and success criteria
     * TDD workflow enforcement and code style rules
     * Full autonomy within the assigned scope
   - Maximize parallelism while respecting dependencies:
     * Up to 10 parallel sub-agents per batch (Claude Code limit)
     * Intelligent batching based on phase dependencies
     * Task-level parallelism within compatible phases

7. Display execution summary:
   - Show total phases, task sequences, and estimated time
   - Display enhanced parallel execution strategy
   - Provide real-time progress via TodoWrite interface

**Output Format:**
```
Created N phases with M tasks
Estimated total time: X minutes

Enhanced sub-agent orchestration launched. Monitor progress via TodoWrite interface.

Execution Strategy:
- Batch 1: 4 parallel sub-agents, ~28min
  • Phase 3.1 (Setup)
  • TaskSeq 3.1-parallel-1 (parallel)
  • TaskSeq 3.1-parallel-2 (parallel)
  • TaskSeq 3.1-sequential (sequential)
- Batch 2: 3 parallel sub-agents, ~20min
  • Phase 3.2 (Tests First)
  • TaskSeq 3.2-parallel-1 (parallel)
  • TaskSeq 3.2-parallel-2 (parallel)
- etc.
```

Context for task generation: {ARGS}

The native tasks provide real-time progress tracking and true parallel execution via Claude Code's sub-agent system.
