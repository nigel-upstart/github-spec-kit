#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "typer>=0.9.0",
#     "rich>=13.0.0",
#     "platformdirs>=3.0.0",
#     "readchar>=4.0.0",
#     "httpx[socks]>=0.24.0",
#     "truststore>=0.8.0",
# ]
# ///
"""
Specify CLI - Claude Code setup tool for Specify projects

Usage:
    uv run specify.py init <project-name>
    uv run specify.py update
    uv run specify.py check

Or install globally:
    uv tool install specify.py
    specify init <project-name>
    specify update
    specify check

Requires Claude Code for full functionality.
"""

import os
import subprocess
import sys
import zipfile
import tempfile
import shutil
import re
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any, Union, Callable
from datetime import datetime
from dataclasses import dataclass, field
from abc import ABC, abstractmethod

import typer  # type: ignore[import-not-found]
import httpx  # type: ignore[import-not-found]
from rich.console import Console  # type: ignore[import-not-found]
from rich.panel import Panel  # type: ignore[import-not-found]
from rich.progress import Progress, SpinnerColumn, TextColumn  # type: ignore[import-not-found]
from rich.text import Text  # type: ignore[import-not-found]
from rich.live import Live  # type: ignore[import-not-found]
from rich.align import Align  # type: ignore[import-not-found]
from rich.table import Table  # type: ignore[import-not-found]
from rich.tree import Tree  # type: ignore[import-not-found]
from typer.core import TyperGroup  # type: ignore[import-not-found]

# For cross-platform keyboard input
import readchar  # type: ignore[import-not-found]
import ssl
import truststore  # type: ignore[import-not-found]

ssl_context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
client = httpx.Client(verify=ssl_context)

# Constants - Claude Code Only
SCRIPT_TYPE_CHOICES = {"sh": "POSIX Shell (bash/zsh)", "ps": "PowerShell"}

# Configuration settings

# Claude CLI local installation path after migrate-installer
CLAUDE_LOCAL_PATH = Path.home() / ".claude" / "local" / "claude"

# ASCII Art Banner
BANNER = """
███████╗██████╗ ███████╗ ██████╗██╗███████╗██╗   ██╗
██╔════╝██╔══██╗██╔════╝██╔════╝██║██╔════╝╚██╗ ██╔╝
███████╗██████╔╝█████╗  ██║     ██║█████╗   ╚████╔╝
╚════██║██╔═══╝ ██╔══╝  ██║     ██║██╔══╝    ╚██╔╝
███████║██║     ███████╗╚██████╗██║██║        ██║
╚══════╝╚═╝     ╚══════╝ ╚═════╝╚═╝╚═╝        ╚═╝
"""

TAGLINE = "Spec-Driven Development Toolkit"

# Files/directories that are safe to update (infrastructure that users don't typically customize)
UPDATABLE_PATHS = {
    ".specify/",
    ".claude/commands/",
    "templates/",
    "scripts/bash/",
    "scripts/powershell/",
}

# Files that should be preserved (user-customizable content)
PRESERVE_PATHS = {
    "CONSTITUTION.md",
    "README.md",
    "specs/",
    ".git/",
    ".env",
    "package.json",
    "pyproject.toml",
    "Cargo.toml",
    "go.mod",
}



def should_update_path(file_path: str, update_mode: bool) -> bool:
    """Check if a file path should be updated in update mode."""
    if not update_mode:
        return True  # In init mode, update everything

    # Check if path should be preserved
    for preserve_path in PRESERVE_PATHS:
        if file_path.startswith(preserve_path):
            return False

    # Check if path is updatable
    for updatable_path in UPDATABLE_PATHS:
        if file_path.startswith(updatable_path):
            return True

    # Default: preserve unknown files in update mode
    return False


# ===== NATIVE TASK SYSTEM =====

@dataclass
class TaskInfo:
    """Information about a single task in the native task system."""
    id: str              # T001, T002, etc.
    description: str     # Full task description
    parallel: bool       # [P] marker
    estimated_duration: int  # 5-30 minutes based on task type
    phase_id: str        # "3.1", "3.2", etc.
    file_path: Optional[str] = None  # Specific file this task affects


@dataclass
class TaskPhase:
    """Represents a phase containing multiple related tasks."""
    id: str              # "3.1", "3.2", "3.3"
    name: str            # "Setup", "Tests First", "Core Implementation"
    description: str     # Full phase context and requirements
    tasks: List[TaskInfo]
    dependencies: List[str]  # ["3.1"] for phase 3.2
    estimated_duration: int  # minutes
    priority_boost: float    # 1.5 for foundation phases


@dataclass
class TaskSequence:
    """A sequence of tasks that must be executed sequentially within a phase."""
    id: str
    tasks: List[TaskInfo]
    estimated_duration: int
    phase_id: str
    phase_name: str

@dataclass
class OrchestrationConfig:
    """Configuration for task orchestration behavior."""
    max_parallel_agents: int = 10  # Claude Code limit
    max_batch_duration: int = 90  # minutes
    enable_performance_monitoring: bool = True
    enable_smart_scheduling: bool = True
    priority_boost_factor: float = 0.3  # How much earlier phases get boosted

@dataclass
class ExecutionBatch:
    """Represents a batch of phases or task sequences that can be executed together."""
    name: str
    phases: List[TaskPhase]
    task_sequences: List[TaskSequence]  # NEW: parallel task sequences within phases
    estimated_time: int
    parallel_count: int = 1  # renamed from parallel_phases


class TaskDurationEstimator:
    """Estimates task duration based on task type and complexity."""

    TASK_TYPE_ESTIMATES = {
        r"create.*model": 15,           # Data models
        r"configure.*tool": 5,          # Linting, formatting
        r".*test.*": 10,               # Any test creation
        r".*endpoint": 20,             # API endpoints
        r"initialize.*project": 8,     # Project setup
        r"connect.*database": 12,      # Integration work
        r".*documentation": 7,         # Docs and README
        r".*validation": 8,            # Input validation
        r".*logging": 6,               # Logging setup
        r".*middleware": 10,           # Middleware implementation
    }

    def estimate_task_duration(self, description: str) -> int:
        """Estimate task duration based on description patterns."""
        description_lower = description.lower()

        for pattern, duration in self.TASK_TYPE_ESTIMATES.items():
            if re.search(pattern, description_lower):
                # Add complexity factor for parallel tasks
                if "[P]" in description:
                    return max(5, duration - 2)  # Parallel tasks often simpler
                return duration

        # Default estimate for unknown task types
        return 15


class NativeTaskManager:
    """Manages native Claude Code tasks using TodoWrite."""

    def __init__(self) -> None:
        self.current_todos: List[Dict[str, str]] = []
        self.duration_estimator = TaskDurationEstimator()

    def create_tasks_from_phases(self, phases: List[TaskPhase]) -> bool:
        """Create TodoWrite tasks from phase definitions."""
        overview_tasks = []

        for phase in phases:
            task_content = f"Phase {phase.id}: {phase.name} ({len(phase.tasks)} tasks, ~{phase.estimated_duration}min)"
            overview_tasks.append({
                "content": task_content,
                "status": "pending",
                "activeForm": f"Executing {phase.name}"
            })

        # Store tasks locally since TodoWrite is a Claude Code tool, not importable function
        self.current_todos = overview_tasks
        console.print(f"[cyan]Created {len(overview_tasks)} phase-level tasks for native execution[/cyan]")
        return True

    def complete_task(self, task_id: str) -> bool:
        """Mark a phase as completed."""
        for todo in self.current_todos:
            if todo["content"].startswith(f"Phase {task_id}:"):
                todo["status"] = "completed"
                break
        else:
            return False

        console.print(f"[green]✓[/green] Completed phase {task_id}")
        return True

    def get_progress_summary(self) -> Dict[str, int]:
        """Get progress summary of phases."""
        total = len(self.current_todos)
        completed = sum(1 for todo in self.current_todos if todo["status"] == "completed")

        return {
            "total": total,
            "completed": completed,
            "pending": total - completed
        }


class PlanProcessor:
    """Processes implementation plans and converts them to native task phases."""

    def __init__(self) -> None:
        self.duration_estimator = TaskDurationEstimator()

    def parse_plan_to_phases(self, plan_content: str, available_docs: List[str]) -> List[TaskPhase]:
        """Parse an implementation plan and convert to TaskPhase objects."""

        phases = []

        # Parse the plan content to extract technology stack and structure
        tech_stack = self._extract_tech_stack(plan_content)
        project_structure = self._extract_project_structure(plan_content)

        # Generate phases based on available documents and plan content
        phases.extend(self._generate_setup_phase(tech_stack, project_structure))
        phases.extend(self._generate_test_phases(available_docs))
        phases.extend(self._generate_implementation_phases(plan_content, available_docs))
        phases.extend(self._generate_integration_phase(tech_stack))
        phases.extend(self._generate_polish_phase(available_docs))

        return phases

    def _extract_tech_stack(self, plan_content: str) -> Dict[str, str]:
        """Extract technology stack information from plan."""
        tech_stack = {}

        # Look for common tech stack patterns in plan
        if re.search(r'python|fastapi|django|flask', plan_content.lower()):
            tech_stack['language'] = 'Python'
            if 'fastapi' in plan_content.lower():
                tech_stack['framework'] = 'FastAPI'
            elif 'django' in plan_content.lower():
                tech_stack['framework'] = 'Django'
            elif 'flask' in plan_content.lower():
                tech_stack['framework'] = 'Flask'

        if re.search(r'javascript|typescript|node|react|next', plan_content.lower()):
            tech_stack['language'] = 'TypeScript'
            if 'react' in plan_content.lower():
                tech_stack['framework'] = 'React'
            elif 'next' in plan_content.lower():
                tech_stack['framework'] = 'Next.js'

        if re.search(r'rust|cargo', plan_content.lower()):
            tech_stack['language'] = 'Rust'

        return tech_stack

    def _extract_project_structure(self, plan_content: str) -> Dict[str, str]:
        """Extract project structure information from plan."""
        structure = {'type': 'single'}  # Default to single project

        if re.search(r'backend.*frontend|web.*app|client.*server', plan_content.lower()):
            structure['type'] = 'web-app'
        elif re.search(r'mobile|ios|android', plan_content.lower()):
            structure['type'] = 'mobile'
        elif re.search(r'cli|command.*line', plan_content.lower()):
            structure['type'] = 'cli'

        return structure

    def _generate_setup_phase(self, tech_stack: Dict[str, str], project_structure: Dict[str, str]) -> List[TaskPhase]:
        """Generate setup phase tasks."""

        tasks = []
        task_id = 1

        # Project structure setup
        tasks.append(TaskInfo(
            id=f"T{task_id:03d}",
            description=f"Create project structure per implementation plan",
            parallel=False,
            estimated_duration=self.duration_estimator.estimate_task_duration("create project structure"),
            phase_id="3.1",
            file_path="project structure"
        ))
        task_id += 1

        # Language-specific initialization
        if tech_stack.get('language') == 'Python':
            framework = tech_stack.get('framework', 'Python')
            tasks.append(TaskInfo(
                id=f"T{task_id:03d}",
                description=f"Initialize Python project with {framework} dependencies",
                parallel=True,
                estimated_duration=self.duration_estimator.estimate_task_duration("initialize python project"),
                phase_id="3.1",
                file_path="pyproject.toml"
            ))
            task_id += 1

        elif tech_stack.get('language') == 'TypeScript':
            framework = tech_stack.get('framework', 'Node.js')
            tasks.append(TaskInfo(
                id=f"T{task_id:03d}",
                description=f"Initialize TypeScript project with {framework} dependencies",
                parallel=True,
                estimated_duration=self.duration_estimator.estimate_task_duration("initialize typescript project"),
                phase_id="3.1",
                file_path="package.json"
            ))
            task_id += 1

        # Linting and formatting
        tasks.append(TaskInfo(
            id=f"T{task_id:03d}",
            description="Configure linting and formatting tools",
            parallel=True,
            estimated_duration=self.duration_estimator.estimate_task_duration("configure linting tools"),
            phase_id="3.1",
            file_path="linting configuration"
        ))

        return [TaskPhase(
            id="3.1",
            name="Setup",
            description="Initialize project structure, dependencies, and development tools",
            tasks=tasks,
            dependencies=[],
            estimated_duration=sum(t.estimated_duration for t in tasks),
            priority_boost=2.0  # High priority for foundation
        )]

    def _generate_test_phases(self, available_docs: List[str]) -> List[TaskPhase]:
        """Generate test phases based on available documentation."""

        tasks = []
        task_id = 4  # Start after setup tasks

        # Contract tests if contracts exist
        if "contracts/" in available_docs:
            tasks.append(TaskInfo(
                id=f"T{task_id:03d}",
                description="Contract test POST /api/users in tests/contract/test_users_post.py",
                parallel=True,
                estimated_duration=self.duration_estimator.estimate_task_duration("contract test"),
                phase_id="3.2",
                file_path="tests/contract/test_users_post.py"
            ))
            task_id += 1

            tasks.append(TaskInfo(
                id=f"T{task_id:03d}",
                description="Contract test GET /api/users/{id} in tests/contract/test_users_get.py",
                parallel=True,
                estimated_duration=self.duration_estimator.estimate_task_duration("contract test"),
                phase_id="3.2",
                file_path="tests/contract/test_users_get.py"
            ))
            task_id += 1

        # Integration tests if quickstart exists
        if "quickstart.md" in available_docs:
            tasks.append(TaskInfo(
                id=f"T{task_id:03d}",
                description="Integration test user registration in tests/integration/test_registration.py",
                parallel=True,
                estimated_duration=self.duration_estimator.estimate_task_duration("integration test"),
                phase_id="3.2",
                file_path="tests/integration/test_registration.py"
            ))
            task_id += 1

            tasks.append(TaskInfo(
                id=f"T{task_id:03d}",
                description="Integration test auth flow in tests/integration/test_auth.py",
                parallel=True,
                estimated_duration=self.duration_estimator.estimate_task_duration("integration test"),
                phase_id="3.2",
                file_path="tests/integration/test_auth.py"
            ))

        if tasks:
            return [TaskPhase(
                id="3.2",
                name="Tests First (TDD)",
                description="Write failing tests before implementation - critical for TDD workflow",
                tasks=tasks,
                dependencies=["3.1"],
                estimated_duration=sum(t.estimated_duration for t in tasks),
                priority_boost=1.8  # High priority for TDD
            )]
        return []

    def _generate_implementation_phases(self, plan_content: str, available_docs: List[str]) -> List[TaskPhase]:
        """Generate core implementation phases."""

        tasks = []
        task_id = 8  # Start after test tasks

        # Model tasks if data model exists
        if "data-model.md" in available_docs:
            tasks.append(TaskInfo(
                id=f"T{task_id:03d}",
                description="User model in src/models/user.py",
                parallel=True,
                estimated_duration=self.duration_estimator.estimate_task_duration("create user model"),
                phase_id="3.3",
                file_path="src/models/user.py"
            ))
            task_id += 1

            tasks.append(TaskInfo(
                id=f"T{task_id:03d}",
                description="UserService CRUD in src/services/user_service.py",
                parallel=True,
                estimated_duration=self.duration_estimator.estimate_task_duration("create user service"),
                phase_id="3.3",
                file_path="src/services/user_service.py"
            ))
            task_id += 1

        # CLI commands if CLI project
        if 'cli' in plan_content.lower():
            tasks.append(TaskInfo(
                id=f"T{task_id:03d}",
                description="CLI --create-user in src/cli/user_commands.py",
                parallel=True,
                estimated_duration=self.duration_estimator.estimate_task_duration("create cli command"),
                phase_id="3.3",
                file_path="src/cli/user_commands.py"
            ))
            task_id += 1

        # API endpoints if contracts exist
        if "contracts/" in available_docs:
            tasks.append(TaskInfo(
                id=f"T{task_id:03d}",
                description="POST /api/users endpoint",
                parallel=False,  # Endpoints might share route files
                estimated_duration=self.duration_estimator.estimate_task_duration("create api endpoint"),
                phase_id="3.3",
                file_path="src/api/users.py"
            ))
            task_id += 1

            tasks.append(TaskInfo(
                id=f"T{task_id:03d}",
                description="GET /api/users/{id} endpoint",
                parallel=False,
                estimated_duration=self.duration_estimator.estimate_task_duration("create api endpoint"),
                phase_id="3.3",
                file_path="src/api/users.py"
            ))
            task_id += 1

        # Validation and error handling
        tasks.append(TaskInfo(
            id=f"T{task_id:03d}",
            description="Input validation",
            parallel=False,
            estimated_duration=self.duration_estimator.estimate_task_duration("input validation"),
            phase_id="3.3",
            file_path="src/validation/"
        ))
        task_id += 1

        tasks.append(TaskInfo(
            id=f"T{task_id:03d}",
            description="Error handling and logging",
            parallel=False,
            estimated_duration=self.duration_estimator.estimate_task_duration("error handling logging"),
            phase_id="3.3",
            file_path="src/utils/"
        ))

        if tasks:
            return [TaskPhase(
                id="3.3",
                name="Core Implementation",
                description="Implement core business logic, models, services, and endpoints",
                tasks=tasks,
                dependencies=["3.2"],
                estimated_duration=sum(t.estimated_duration for t in tasks),
                priority_boost=1.5
            )]
        return []

    def _generate_integration_phase(self, tech_stack: Dict[str, str]) -> List[TaskPhase]:
        """Generate integration phase tasks."""

        tasks = []
        task_id = 15  # After core implementation

        tasks.append(TaskInfo(
            id=f"T{task_id:03d}",
            description="Connect services to database",
            parallel=False,
            estimated_duration=self.duration_estimator.estimate_task_duration("connect database"),
            phase_id="3.4",
            file_path="src/database/"
        ))
        task_id += 1

        if tech_stack.get('framework') in ['FastAPI', 'Django', 'Flask']:
            tasks.append(TaskInfo(
                id=f"T{task_id:03d}",
                description="Auth middleware",
                parallel=False,
                estimated_duration=self.duration_estimator.estimate_task_duration("auth middleware"),
                phase_id="3.4",
                file_path="src/middleware/"
            ))
            task_id += 1

            tasks.append(TaskInfo(
                id=f"T{task_id:03d}",
                description="Request/response logging",
                parallel=False,
                estimated_duration=self.duration_estimator.estimate_task_duration("request response logging"),
                phase_id="3.4",
                file_path="src/middleware/"
            ))
            task_id += 1

            tasks.append(TaskInfo(
                id=f"T{task_id:03d}",
                description="CORS and security headers",
                parallel=False,
                estimated_duration=self.duration_estimator.estimate_task_duration("CORS security headers"),
                phase_id="3.4",
                file_path="src/middleware/"
            ))

        return [TaskPhase(
            id="3.4",
            name="Integration",
            description="Connect components together - database, middleware, logging, security",
            tasks=tasks,
            dependencies=["3.3"],
            estimated_duration=sum(t.estimated_duration for t in tasks),
            priority_boost=1.2
        )]

    def _generate_polish_phase(self, available_docs: List[str]) -> List[TaskPhase]:
        """Generate polish phase tasks."""

        tasks = []
        task_id = 19  # After integration

        tasks.append(TaskInfo(
            id=f"T{task_id:03d}",
            description="Unit tests for validation in tests/unit/test_validation.py",
            parallel=True,
            estimated_duration=self.duration_estimator.estimate_task_duration("unit tests validation"),
            phase_id="3.5",
            file_path="tests/unit/test_validation.py"
        ))
        task_id += 1

        tasks.append(TaskInfo(
            id=f"T{task_id:03d}",
            description="Performance tests (<200ms)",
            parallel=False,
            estimated_duration=self.duration_estimator.estimate_task_duration("performance tests"),
            phase_id="3.5",
            file_path="tests/performance/"
        ))
        task_id += 1

        tasks.append(TaskInfo(
            id=f"T{task_id:03d}",
            description="Update docs/api.md",
            parallel=True,
            estimated_duration=self.duration_estimator.estimate_task_duration("update documentation"),
            phase_id="3.5",
            file_path="docs/api.md"
        ))
        task_id += 1

        tasks.append(TaskInfo(
            id=f"T{task_id:03d}",
            description="Remove duplication and refactor",
            parallel=False,
            estimated_duration=self.duration_estimator.estimate_task_duration("remove duplication refactor"),
            phase_id="3.5",
            file_path="src/"
        ))
        task_id += 1

        if "quickstart.md" in available_docs:
            tasks.append(TaskInfo(
                id=f"T{task_id:03d}",
                description="Run manual testing from quickstart.md",
                parallel=False,
                estimated_duration=self.duration_estimator.estimate_task_duration("manual testing"),
                phase_id="3.5",
                file_path="quickstart.md"
            ))

        return [TaskPhase(
            id="3.5",
            name="Polish",
            description="Final polish - unit tests, performance, documentation, manual testing",
            tasks=tasks,
            dependencies=["3.4"],
            estimated_duration=sum(t.estimated_duration for t in tasks),
            priority_boost=1.0
        )]


@dataclass
class PerformanceMetrics:
    """Performance metrics for orchestration monitoring."""
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    total_phases: int = 0
    completed_phases: int = 0
    failed_phases: int = 0
    average_phase_duration: float = 0.0
    peak_parallel_agents: int = 0

class PhaseOrchestrator:
    """Orchestrates phase-based execution with intelligent scheduling and advanced features."""

    def __init__(self, task_manager: NativeTaskManager, config: Optional[OrchestrationConfig] = None):
        self.task_manager = task_manager
        self.config = config or OrchestrationConfig()
        self.metrics = PerformanceMetrics()
        self.active_agents: Dict[str, datetime] = {}  # Track active sub-agents

    def build_execution_queue(self, phases: List[TaskPhase]) -> List[ExecutionBatch]:
        """Create optimized execution order with task-level parallelism and smart scheduling."""

        if self.config.enable_performance_monitoring:
            self.metrics.total_phases = len(phases)
            self.metrics.start_time = datetime.now()

        # Sort phases by dependency order and strategy
        ordered_phases = self._sort_phases_by_strategy(phases)

        # Build execution batches with advanced scheduling
        batches: List[ExecutionBatch] = []
        completed_phases: set[str] = set()

        while len(completed_phases) < len(ordered_phases):
            # Find phases that can run now (dependencies satisfied)
            ready_phases = [
                phase for phase in ordered_phases
                if phase.id not in completed_phases
                and all(dep in completed_phases for dep in phase.dependencies)
            ]

            if not ready_phases:
                if self.config.enable_performance_monitoring:
                    console.print("[yellow]Warning:[/yellow] Possible circular dependency detected")
                break

            # Apply strategy-specific batching
            batch_phases, max_batch_time = self._create_smart_batch(ready_phases)
            task_sequences = []

            # For each phase, create task sequences for parallel execution
            for phase in batch_phases:
                sequences = self._create_task_sequences(phase)
                task_sequences.extend(sequences)

            # Calculate optimal parallel count based on strategy
            optimal_parallel = self._calculate_optimal_parallel_count(
                len(batch_phases), len(task_sequences), max_batch_time
            )

            batches.append(ExecutionBatch(
                name=f"batch-{len(batches)+1}",
                phases=batch_phases,
                task_sequences=task_sequences,
                estimated_time=max_batch_time,
                parallel_count=optimal_parallel
            ))

            # Mark phases as completed
            for phase in batch_phases:
                completed_phases.add(phase.id)

        return batches

    def _has_blocking_dependencies(self, phase: TaskPhase, current_batch: List[TaskPhase]) -> bool:
        """Check if phase has dependencies that block it from current batch."""
        current_phase_ids = {p.id for p in current_batch}
        return any(dep in current_phase_ids for dep in phase.dependencies)

    def _sort_phases_by_dependencies(self, phases: List[TaskPhase]) -> List[TaskPhase]:
        """Sort phases in dependency order (topological sort)."""
        # Simple topological sort for phases
        phase_map = {phase.id: phase for phase in phases}
        result = []
        visited = set()
        visiting = set()

        def visit(phase_id: str) -> None:
            if phase_id in visiting:
                return  # Circular dependency - skip
            if phase_id in visited:
                return

            visiting.add(phase_id)
            phase = phase_map.get(phase_id)
            if phase:
                for dep_id in phase.dependencies:
                    if dep_id in phase_map:
                        visit(dep_id)
                visiting.remove(phase_id)
                visited.add(phase_id)
                result.append(phase)

        for phase in phases:
            visit(phase.id)

        return result

    def _create_task_sequences(self, phase: TaskPhase) -> List[TaskSequence]:
        """Create parallel task sequences within a phase based on [P] markers."""
        sequences = []

        # Group tasks by parallelism
        parallel_tasks = [task for task in phase.tasks if task.parallel]
        sequential_tasks = [task for task in phase.tasks if not task.parallel]

        # Create sequences for parallel tasks (each gets its own sequence)
        for i, task in enumerate(parallel_tasks):
            sequences.append(TaskSequence(
                id=f"{phase.id}-parallel-{i+1}",
                tasks=[task],
                estimated_duration=task.estimated_duration,
                phase_id=phase.id,
                phase_name=phase.name
            ))

        # Create sequence for sequential tasks (all in one sequence)
        if sequential_tasks:
            total_duration = sum(task.estimated_duration for task in sequential_tasks)
            sequences.append(TaskSequence(
                id=f"{phase.id}-sequential",
                tasks=sequential_tasks,
                estimated_duration=total_duration,
                phase_id=phase.id,
                phase_name=phase.name
            ))

        return sequences

    def _sort_phases_by_strategy(self, phases: List[TaskPhase]) -> List[TaskPhase]:
        """Sort phases based on dependencies with balanced approach."""

        # First apply topological sort for dependencies
        dependency_sorted = self._sort_phases_by_dependencies(phases)

        # Balance duration and parallelism
        def balanced_score(phase: TaskPhase) -> float:
            parallel_ratio = sum(1 for t in phase.tasks if t.parallel) / len(phase.tasks)
            duration_factor = 1.0 / (phase.estimated_duration + 1)  # Avoid division by zero
            return parallel_ratio * duration_factor * phase.priority_boost

        return sorted(dependency_sorted,
                     key=lambda p: (len(p.dependencies), -balanced_score(p)))

    def _create_smart_batch(self, ready_phases: List[TaskPhase]) -> Tuple[List[TaskPhase], int]:
        """Create an optimally-sized batch using balanced approach."""

        # Consider batch duration limit
        batch_phases: List[TaskPhase] = []
        total_time = 0

        for phase in ready_phases:
            if (total_time + phase.estimated_duration <= self.config.max_batch_duration
                and len(batch_phases) < 3):
                batch_phases.append(phase)
                total_time = max(total_time, phase.estimated_duration)  # Parallel execution
            else:
                break

        # Ensure we have at least one phase
        if not batch_phases and ready_phases:
            batch_phases = [ready_phases[0]]
            total_time = ready_phases[0].estimated_duration

        max_batch_time = max((p.estimated_duration for p in batch_phases), default=0)
        return batch_phases, max_batch_time

    def _calculate_optimal_parallel_count(self, num_phases: int, num_sequences: int,
                                        batch_duration: int) -> int:
        """Calculate optimal number of parallel agents based on resources and duration."""

        total_units = num_phases + num_sequences

        # Scale based on batch duration - longer batches get more parallel agents
        if batch_duration > 60:  # Long batches
            parallel_bonus = 2
        elif batch_duration > 30:  # Medium batches
            parallel_bonus = 1
        else:  # Short batches
            parallel_bonus = 0

        optimal = min(total_units,
                     min(self.config.max_parallel_agents,
                         max(1, total_units // 2 + parallel_bonus)))
        return optimal

    def execute_phase(self, phase: TaskPhase) -> str:
        """Launch sub-agent for entire phase execution."""

        # Format tasks for sub-agent context
        task_list = []
        for task in phase.tasks:
            parallel_marker = "[P] " if task.parallel else ""
            task_list.append(f"  - {task.id} {parallel_marker}{task.description}")

        tasks_text = "\n".join(task_list)

        phase_context = f"""
Phase: {phase.name} ({phase.id})

Context: {phase.description}

Tasks to complete in this phase:
{tasks_text}

Success criteria:
- All tasks marked complete via TodoWrite
- Follow TDD workflow if tests involved
- Apply .cursor/rules for code style
- Commit each task with conventional commits

You have full autonomy within this phase. Work efficiently and update progress via TodoWrite.
        """.strip()

        # In production, this would launch a sub-agent via Task tool
        # For now, we'll simulate by printing the phase context
        console.print(f"[blue]Sub-agent launched for {phase.name}[/blue]")
        console.print(f"[dim]Phase context: {len(phase_context)} characters[/dim]")
        return f"sub-agent-{phase.id}"

    def execute_task_sequence(self, task_sequence: TaskSequence) -> str:
        """Launch sub-agent for a specific task sequence within a phase."""

        # Format tasks for sub-agent context
        task_list = []
        for task in task_sequence.tasks:
            parallel_marker = "[P] " if task.parallel else ""
            task_list.append(f"  - {task.id} {parallel_marker}{task.description}")
            if task.file_path:
                task_list.append(f"    📁 {task.file_path}")

        tasks_text = "\n".join(task_list)
        sequence_type = "parallel" if len(task_sequence.tasks) == 1 and task_sequence.tasks[0].parallel else "sequential"

        sequence_context = f"""
Task Sequence: {task_sequence.id} ({sequence_type})
Phase: {task_sequence.phase_name} ({task_sequence.phase_id})
Estimated Duration: {task_sequence.estimated_duration} minutes

Tasks in this sequence:
{tasks_text}

Success criteria:
- All tasks marked complete via TodoWrite
- Follow TDD workflow if tests involved
- Apply .cursor/rules for code style
- Commit each task with conventional commits

You have full autonomy within this task sequence. Work efficiently and update progress.
        """.strip()

        # In production, this would launch a sub-agent via Task tool
        console.print(f"[green]Sub-agent launched for {sequence_type} sequence in {task_sequence.phase_name}[/green]")
        console.print(f"[dim]Sequence context: {len(sequence_context)} characters[/dim]")
        return f"sub-agent-{task_sequence.id}"

    def orchestrate_spec_workflow(self, phases: List[TaskPhase]) -> None:
        """Execute complete Spec-Driven workflow with intelligent orchestration and monitoring."""

        # Initialize performance monitoring
        if self.config.enable_performance_monitoring:
            self.metrics.start_time = datetime.now()
            self.metrics.total_phases = len(phases)

        # Create native tasks for high-level tracking
        try:
            self.task_manager.create_tasks_from_phases(phases)
        except Exception as e:
            console.print(f"[red]Error:[/red] Failed to create native tasks: {e}")
            if self.config.enable_performance_monitoring:
                console.print("[dim]Continuing with basic execution monitoring[/dim]")

        # Build optimized execution queue
        execution_queue = self.build_execution_queue(phases)

        if self.config.enable_performance_monitoring:
            total_phases = sum(len(batch.phases) for batch in execution_queue)
            total_sequences = sum(len(batch.task_sequences) for batch in execution_queue)
            estimated_total = sum(batch.estimated_time for batch in execution_queue)

            console.print(f"[cyan]🎯 Balanced Orchestration[/cyan]")
            console.print(f"[cyan]📊 Launching {total_phases} phases + {total_sequences} task sequences[/cyan]")
            console.print(f"[cyan]⏱️  Estimated completion: {estimated_total} minutes[/cyan]")
            console.print(f"[cyan]🔧 Max parallel agents: {self.config.max_parallel_agents}[/cyan]")
            console.print()

        # Execute batches with advanced error handling and retry logic
        successful_batches = 0
        for batch_idx, batch in enumerate(execution_queue):
            try:
                success = self._execute_batch_with_retry(batch, batch_idx + 1)
                if success:
                    successful_batches += 1
                    if self.config.enable_performance_monitoring:
                        self.metrics.completed_phases += len(batch.phases)
                else:
                    if self.config.enable_performance_monitoring:
                        self.metrics.failed_phases += len(batch.phases)

            except Exception as e:
                console.print(f"[red]Critical Error in {batch.name}:[/red] {e}")
                if self.config.enable_performance_monitoring:
                    self.metrics.failed_phases += len(batch.phases)


        # Final performance report
        if self.config.enable_performance_monitoring:
            self._generate_performance_report(successful_batches, len(execution_queue))

    def _execute_batch_with_retry(self, batch: ExecutionBatch, batch_number: int) -> bool:
        """Execute a batch with error handling."""

        batch_items = len(batch.phases) + len(batch.task_sequences)

        try:
            console.print(f"[yellow]Starting {batch.name}: "
                         f"{batch_items} units, ~{batch.estimated_time}min[/yellow]")

            # Track peak parallelism
            if self.config.enable_performance_monitoring:
                self.metrics.peak_parallel_agents = max(
                    self.metrics.peak_parallel_agents, batch.parallel_count
                )

            # Execute batch
            if batch.parallel_count > 1:
                # Launch phases in parallel
                for phase in batch.phases:
                    agent_id = self.execute_phase(phase)
                    self.active_agents[agent_id] = datetime.now()

                # Launch task sequences in parallel
                for sequence in batch.task_sequences:
                    agent_id = self.execute_task_sequence(sequence)
                    self.active_agents[agent_id] = datetime.now()

                console.print(f"[green]✅ Launched {batch.parallel_count} parallel sub-agents[/green]")
            else:
                # Sequential execution
                for phase in batch.phases:
                    agent_id = self.execute_phase(phase)
                    self.active_agents[agent_id] = datetime.now()
                for sequence in batch.task_sequences:
                    agent_id = self.execute_task_sequence(sequence)
                    self.active_agents[agent_id] = datetime.now()

                console.print("[green]✅ Launched sequential execution[/green]")

            return True  # Success

        except Exception as e:
            console.print(f"[red]Error in {batch.name}:[/red] {e}")
            return False


    def _generate_performance_report(self, successful_batches: int, total_batches: int) -> None:
        """Generate a performance report for the orchestration run."""

        self.metrics.end_time = datetime.now()
        duration = (self.metrics.end_time - self.metrics.start_time).total_seconds() / 60

        console.print("\n" + "="*60)
        console.print("[bold cyan]🎯 Orchestration Performance Report[/bold cyan]")
        console.print("="*60)
        console.print(f"[green]✅ Completed:[/green] {self.metrics.completed_phases}/{self.metrics.total_phases} phases")
        console.print(f"[red]❌ Failed:[/red] {self.metrics.failed_phases} phases")
        console.print(f"[blue]📊 Batches:[/blue] {successful_batches}/{total_batches} successful")
        console.print(f"[cyan]⚡ Peak Parallelism:[/cyan] {self.metrics.peak_parallel_agents} agents")
        console.print(f"[magenta]⏱️  Total Duration:[/magenta] {duration:.1f} minutes")
        console.print("="*60)




# ===== UI CLASSES AND FUNCTIONS =====

class StepTracker:
    """Track and render hierarchical steps without emojis, similar to Claude Code tree output."""

    def __init__(self, title: str) -> None:
        self.title = title
        self.steps: List[Dict[str, str]] = []  # list of dicts: {key, label, status, detail}
        self.status_order = {"pending": 0, "running": 1, "done": 2, "error": 3, "skipped": 4}
        self._refresh_cb: Optional[Callable[[], None]] = None  # callable to trigger UI refresh

    def attach_refresh(self, cb: Callable[[], None]) -> None:
        self._refresh_cb = cb

    def add(self, key: str, label: str) -> None:
        if key not in [s["key"] for s in self.steps]:
            self.steps.append({"key": key, "label": label, "status": "pending", "detail": ""})
            self._maybe_refresh()

    def start(self, key: str, detail: str = "") -> None:
        self._update(key, status="running", detail=detail)

    def complete(self, key: str, detail: str = "") -> None:
        self._update(key, status="done", detail=detail)

    def error(self, key: str, detail: str = "") -> None:
        self._update(key, status="error", detail=detail)

    def skip(self, key: str, detail: str = "") -> None:
        self._update(key, status="skipped", detail=detail)

    def _update(self, key: str, status: str, detail: str) -> None:
        for s in self.steps:
            if s["key"] == key:
                s["status"] = status
                if detail:
                    s["detail"] = detail
                self._maybe_refresh()
                return
        # If not present, add it
        self.steps.append({"key": key, "label": key, "status": status, "detail": detail})
        self._maybe_refresh()

    def _maybe_refresh(self) -> None:
        if self._refresh_cb:
            try:
                self._refresh_cb()
            except Exception:
                pass

    def render(self) -> Tree:
        tree = Tree(f"[bold cyan]{self.title}[/bold cyan]", guide_style="grey50")
        for step in self.steps:
            label = step["label"]
            detail_text = step["detail"].strip() if step["detail"] else ""

            status = step["status"]
            if status == "done":
                symbol = "[green]●[/green]"
            elif status == "pending":
                symbol = "[green dim]○[/green dim]"
            elif status == "running":
                symbol = "[cyan]○[/cyan]"
            elif status == "error":
                symbol = "[red]●[/red]"
            elif status == "skipped":
                symbol = "[yellow]○[/yellow]"
            else:
                symbol = " "

            if status == "pending":
                if detail_text:
                    line = f"{symbol} [bright_black]{label} ({detail_text})[/bright_black]"
                else:
                    line = f"{symbol} [bright_black]{label}[/bright_black]"
            else:
                if detail_text:
                    line = f"{symbol} [white]{label}[/white] [bright_black]({detail_text})[/bright_black]"
                else:
                    line = f"{symbol} [white]{label}[/white]"

            tree.add(line)
        return tree


def get_key() -> str:
    """Get a single keypress in a cross-platform way using readchar."""
    key = readchar.readkey()

    # Arrow keys
    if key == readchar.key.UP:
        return 'up'
    if key == readchar.key.DOWN:
        return 'down'

    # Enter/Return
    if key == readchar.key.ENTER:
        return 'enter'

    # Escape
    if key == readchar.key.ESC:
        return 'escape'

    # Ctrl+C
    if key == readchar.key.CTRL_C:
        raise KeyboardInterrupt

    return str(key)


def select_with_arrows(options: Dict[str, str], prompt_text: str = "Select an option", default_key: Optional[str] = None) -> str:
    """Interactive selection using arrow keys with Rich Live display."""
    option_keys = list(options.keys())
    if default_key and default_key in option_keys:
        selected_index = option_keys.index(default_key)
    else:
        selected_index = 0

    selected_key: Optional[str] = None

    def create_selection_panel() -> Panel:
        """Create the selection panel with current selection highlighted."""
        table = Table.grid(padding=(0, 2))
        table.add_column(style="bright_cyan", justify="left", width=3)
        table.add_column(style="white", justify="left")

        for i, key in enumerate(option_keys):
            if i == selected_index:
                table.add_row("▶", f"[bright_cyan]{key}: {options[key]}[/bright_cyan]")
            else:
                table.add_row(" ", f"[white]{key}: {options[key]}[/white]")

        table.add_row("", "")
        table.add_row("", "[dim]Use ↑/↓ to navigate, Enter to select, Esc to cancel[/dim]")

        return Panel(
            table,
            title=f"[bold]{prompt_text}[/bold]",
            border_style="cyan",
            padding=(1, 2)
        )

    console.print()

    def run_selection_loop() -> None:
        nonlocal selected_key, selected_index
        with Live(create_selection_panel(), console=console, transient=True, auto_refresh=False) as live:
            while True:
                try:
                    key = get_key()
                    if key == 'up':
                        selected_index = (selected_index - 1) % len(option_keys)
                    elif key == 'down':
                        selected_index = (selected_index + 1) % len(option_keys)
                    elif key == 'enter':
                        selected_key = option_keys[selected_index]
                        break
                    elif key == 'escape':
                        console.print("\n[yellow]Selection cancelled[/yellow]")
                        raise typer.Exit(1)

                    live.update(create_selection_panel(), refresh=True)

                except KeyboardInterrupt:
                    console.print("\n[yellow]Selection cancelled[/yellow]")
                    raise typer.Exit(1)

    run_selection_loop()

    if selected_key is None:
        console.print("\n[red]Selection failed.[/red]")
        raise typer.Exit(1)

    return selected_key


console = Console()


class BannerGroup(TyperGroup):  # type: ignore[misc]
    """Custom group that shows banner before help."""

    def format_help(self, ctx: Any, formatter: Any) -> None:
        show_banner()
        super().format_help(ctx, formatter)


app = typer.Typer(
    name="specify",
    help="Claude Code setup tool for Specify spec-driven development projects",
    add_completion=False,
    invoke_without_command=True,
    cls=BannerGroup,
)


def show_banner() -> None:
    """Display the ASCII art banner."""
    banner_lines = BANNER.strip().split('\n')
    colors = ["bright_blue", "blue", "cyan", "bright_cyan", "white", "bright_white"]

    styled_banner = Text()
    for i, line in enumerate(banner_lines):
        color = colors[i % len(colors)]
        styled_banner.append(line + "\n", style=color)

    console.print(Align.center(styled_banner))
    console.print(Align.center(Text(TAGLINE, style="italic bright_yellow")))
    console.print()


@app.callback()  # type: ignore[misc]
def callback(ctx: typer.Context) -> None:
    """Show banner when no subcommand is provided."""
    if ctx.invoked_subcommand is None and "--help" not in sys.argv and "-h" not in sys.argv:
        show_banner()
        console.print(Align.center("[dim]Run 'specify --help' for usage information[/dim]"))
        console.print()


def run_command(cmd: List[str], check_return: bool = True, capture: bool = False, shell: bool = False) -> Optional[str]:
    """Run a shell command and optionally capture output."""
    try:
        if capture:
            result = subprocess.run(cmd, check=check_return, capture_output=True, text=True, shell=shell)
            return result.stdout.strip()
        else:
            subprocess.run(cmd, check=check_return, shell=shell)
            return None
    except subprocess.CalledProcessError as e:
        if check_return:
            console.print(f"[red]Error running command:[/red] {' '.join(cmd)}")
            console.print(f"[red]Exit code:[/red] {e.returncode}")
            if hasattr(e, 'stderr') and e.stderr:
                console.print(f"[red]Error output:[/red] {e.stderr}")
            raise
        return None


def check_tool_for_tracker(tool: str, install_hint: str, tracker: StepTracker) -> bool:
    """Check if a tool is installed and update tracker."""
    if tool == "claude" and CLAUDE_LOCAL_PATH.exists() and CLAUDE_LOCAL_PATH.is_file():
        tracker.complete(tool, "available")
        return True

    if shutil.which(tool):
        tracker.complete(tool, "available")
        return True
    else:
        tracker.error(tool, f"not found - {install_hint}")
        return False


def check_tool(tool: str, install_hint: str) -> bool:
    """Check if a tool is installed."""
    if tool == "claude":
        if CLAUDE_LOCAL_PATH.exists() and CLAUDE_LOCAL_PATH.is_file():
            return True

    if shutil.which(tool):
        return True
    else:
        console.print(f"[yellow]⚠️  {tool} not found[/yellow]")
        console.print(f"   Install with: [cyan]{install_hint}[/cyan]")
        return False


def is_git_repo(path: Optional[Path] = None) -> bool:
    """Check if the specified path is inside a git repository."""
    if path is None:
        path = Path.cwd()

    if not path.is_dir():
        return False

    try:
        subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            check=True,
            capture_output=True,
            cwd=path,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def init_git_repo(project_path: Path, quiet: bool = False) -> bool:
    """Initialize a git repository in the specified path."""
    original_cwd = Path.cwd()
    try:
        os.chdir(project_path)
        if not quiet:
            console.print("[cyan]Initializing git repository...[/cyan]")
        subprocess.run(["git", "init"], check=True, capture_output=True)
        subprocess.run(["git", "add", "."], check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial commit from Specify template"], check=True, capture_output=True)
        if not quiet:
            console.print("[green]✓[/green] Git repository initialized")
        return True

    except subprocess.CalledProcessError as e:
        if not quiet:
            console.print(f"[red]Error initializing git repository:[/red] {e}")
        return False
    finally:
        os.chdir(original_cwd)


def download_template_from_github(download_dir: Path, *, script_type: str = "sh", verbose: bool = True, show_progress: bool = True, client: Optional[httpx.Client] = None, debug: bool = False) -> Tuple[Path, Dict[str, Any]]:
    repo_owner = "github"
    repo_name = "spec-kit"
    if client is None:
        client = httpx.Client(verify=ssl_context)

    if verbose:
        console.print("[cyan]Fetching latest release information...[/cyan]")
    api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/releases/latest"

    try:
        response = client.get(api_url, timeout=30, follow_redirects=True)
        status = response.status_code
        if status != 200:
            msg = f"GitHub API returned {status} for {api_url}"
            if debug:
                msg += f"\nResponse headers: {response.headers}\nBody (truncated 500): {response.text[:500]}"
            raise RuntimeError(msg)
        try:
            release_data = response.json()
        except ValueError as je:
            raise RuntimeError(f"Failed to parse release JSON: {je}\nRaw (truncated 400): {response.text[:400]}")
    except Exception as e:
        console.print("[red]Error fetching release information[/red]")
        console.print(Panel(str(e), title="Fetch Error", border_style="red"))
        raise typer.Exit(1)

    # Find the template asset for Claude Code
    pattern = f"spec-kit-template-claude-{script_type}"
    matching_assets = [
        asset for asset in release_data.get("assets", [])
        if pattern in asset["name"] and asset["name"].endswith(".zip")
    ]

    if not matching_assets:
        console.print(f"[red]No matching release asset found[/red] for pattern: [bold]{pattern}[/bold]")
        asset_names = [a.get('name','?') for a in release_data.get('assets', [])]
        console.print(Panel("\n".join(asset_names) or "(no assets)", title="Available Assets", border_style="yellow"))
        raise typer.Exit(1)

    asset = matching_assets[0]
    download_url = asset["browser_download_url"]
    filename = asset["name"]
    file_size = asset["size"]

    if verbose:
        console.print(f"[cyan]Found template:[/cyan] {filename}")
        console.print(f"[cyan]Size:[/cyan] {file_size:,} bytes")
        console.print(f"[cyan]Release:[/cyan] {release_data['tag_name']}")

    # Download the file
    zip_path = download_dir / filename
    if verbose:
        console.print("[cyan]Downloading template...[/cyan]")

    try:
        with client.stream("GET", download_url, timeout=60, follow_redirects=True) as response:
            if response.status_code != 200:
                body_sample = response.text[:400]
                raise RuntimeError(f"Download failed with {response.status_code}\nHeaders: {response.headers}\nBody (truncated): {body_sample}")
            total_size = int(response.headers.get('content-length', 0))
            with open(zip_path, 'wb') as f:
                if total_size == 0:
                    for chunk in response.iter_bytes(chunk_size=8192):
                        f.write(chunk)
                else:
                    if show_progress:
                        with Progress(
                            SpinnerColumn(),
                            TextColumn("[progress.description]{task.description}"),
                            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                            console=console,
                        ) as progress:
                            task = progress.add_task("Downloading...", total=total_size)
                            downloaded = 0
                            for chunk in response.iter_bytes(chunk_size=8192):
                                f.write(chunk)
                                downloaded += len(chunk)
                                progress.update(task, completed=downloaded)
                    else:
                        for chunk in response.iter_bytes(chunk_size=8192):
                            f.write(chunk)
    except Exception as e:
        console.print("[red]Error downloading template[/red]")
        detail = str(e)
        if zip_path.exists():
            zip_path.unlink()
        console.print(Panel(detail, title="Download Error", border_style="red"))
        raise typer.Exit(1)
    if verbose:
        console.print(f"Downloaded: {filename}")
    metadata = {
        "filename": filename,
        "size": file_size,
        "release": release_data["tag_name"],
        "asset_url": download_url
    }
    return zip_path, metadata


def download_and_extract_template(project_path: Path, script_type: str, is_current_dir: bool = False, *, verbose: bool = True, tracker: Optional[StepTracker] = None, client: Optional[httpx.Client] = None, debug: bool = False, update_mode: bool = False) -> Path:
    """Download the latest release and extract it to create a new project."""
    current_dir = Path.cwd()

    if tracker:
        tracker.start("fetch", "contacting GitHub API")
    try:
        zip_path, meta = download_template_from_github(
            current_dir,
            script_type=script_type,
            verbose=verbose and tracker is None,
            show_progress=(tracker is None),
            client=client,
            debug=debug
        )
        if tracker:
            tracker.complete("fetch", f"release {meta['release']} ({meta['size']:,} bytes)")
            tracker.add("download", "Download template")
            tracker.complete("download", meta['filename'])
    except Exception as e:
        if tracker:
            tracker.error("fetch", str(e))
        else:
            if verbose:
                console.print(f"[red]Error downloading template:[/red] {e}")
        raise

    if tracker:
        tracker.add("extract", "Extract template")
        tracker.start("extract")
    elif verbose:
        console.print("Extracting template...")

    try:
        if not is_current_dir:
            project_path.mkdir(parents=True)

        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_contents = zip_ref.namelist()
            if tracker:
                tracker.start("zip-list")
                tracker.complete("zip-list", f"{len(zip_contents)} entries")
            elif verbose:
                console.print(f"[cyan]ZIP contains {len(zip_contents)} items[/cyan]")

            if is_current_dir:
                with tempfile.TemporaryDirectory() as temp_dir:
                    temp_path = Path(temp_dir)
                    zip_ref.extractall(temp_path)

                    extracted_items = list(temp_path.iterdir())
                    if tracker:
                        tracker.start("extracted-summary")
                        tracker.complete("extracted-summary", f"temp {len(extracted_items)} items")
                    elif verbose:
                        console.print(f"[cyan]Extracted {len(extracted_items)} items to temp location[/cyan]")

                    source_dir = temp_path
                    if len(extracted_items) == 1 and extracted_items[0].is_dir():
                        source_dir = extracted_items[0]
                        if tracker:
                            tracker.add("flatten", "Flatten nested directory")
                            tracker.complete("flatten")
                        elif verbose:
                            console.print("[cyan]Found nested directory structure[/cyan]")

                    updated_files = []
                    skipped_files = []

                    for item in source_dir.iterdir():
                        dest_path = project_path / item.name

                        # Check if this path should be updated
                        if not should_update_path(item.name, update_mode):
                            skipped_files.append(item.name)
                            continue

                        updated_files.append(item.name)
                        if item.is_dir():
                            if dest_path.exists():
                                if verbose and not tracker:
                                    console.print(f"[yellow]Merging directory:[/yellow] {item.name}")
                                for sub_item in item.rglob('*'):
                                    if sub_item.is_file():
                                        rel_path = sub_item.relative_to(item)
                                        # Check individual files within directories too
                                        full_rel_path = f"{item.name}/{rel_path}"
                                        if not should_update_path(full_rel_path, update_mode):
                                            continue
                                        dest_file = dest_path / rel_path
                                        dest_file.parent.mkdir(parents=True, exist_ok=True)
                                        shutil.copy2(sub_item, dest_file)
                            else:
                                shutil.copytree(item, dest_path)
                        else:
                            if dest_path.exists() and verbose and not tracker:
                                console.print(f"[yellow]Overwriting file:[/yellow] {item.name}")
                            shutil.copy2(item, dest_path)

                    if update_mode and (verbose and not tracker):
                        if updated_files:
                            console.print(f"[green]Updated:[/green] {', '.join(updated_files)}")
                        if skipped_files:
                            console.print(f"[yellow]Preserved:[/yellow] {', '.join(skipped_files)}")
                    if verbose and not tracker:
                        console.print("[cyan]Template files merged into current directory[/cyan]")
            else:
                zip_ref.extractall(project_path)

                extracted_items = list(project_path.iterdir())
                if tracker:
                    tracker.start("extracted-summary")
                    tracker.complete("extracted-summary", f"{len(extracted_items)} top-level items")
                elif verbose:
                    console.print(f"[cyan]Extracted {len(extracted_items)} items to {project_path}:[/cyan]")
                    for item in extracted_items:
                        console.print(f"  - {item.name} ({'dir' if item.is_dir() else 'file'})")

                if len(extracted_items) == 1 and extracted_items[0].is_dir():
                    nested_dir = extracted_items[0]
                    temp_move_dir = project_path.parent / f"{project_path.name}_temp"
                    shutil.move(str(nested_dir), str(temp_move_dir))
                    project_path.rmdir()
                    shutil.move(str(temp_move_dir), str(project_path))
                    if tracker:
                        tracker.add("flatten", "Flatten nested directory")
                        tracker.complete("flatten")
                    elif verbose:
                        console.print("[cyan]Flattened nested directory structure[/cyan]")

    except Exception as e:
        if tracker:
            tracker.error("extract", str(e))
        else:
            if verbose:
                console.print(f"[red]Error extracting template:[/red] {e}")
                if debug:
                    console.print(Panel(str(e), title="Extraction Error", border_style="red"))
        if not is_current_dir and project_path.exists():
            shutil.rmtree(project_path)
        raise typer.Exit(1)
    else:
        if tracker:
            tracker.complete("extract")
    finally:
        if tracker:
            tracker.add("cleanup", "Remove temporary archive")
        if zip_path.exists():
            zip_path.unlink()
            if tracker:
                tracker.complete("cleanup")
            elif verbose:
                console.print(f"Cleaned up: {zip_path.name}")

    return project_path


def ensure_executable_scripts(project_path: Path, tracker: Optional[StepTracker] = None) -> None:
    """Ensure POSIX .sh scripts under .specify/scripts (recursively) have execute bits (no-op on Windows)."""
    if os.name == "nt":
        return  # Windows: skip silently
    scripts_root = project_path / ".specify" / "scripts"
    if not scripts_root.is_dir():
        return
    failures: List[str] = []
    updated = 0
    for script in scripts_root.rglob("*.sh"):
        try:
            if script.is_symlink() or not script.is_file():
                continue
            try:
                with script.open("rb") as f:
                    first_bytes = f.read(2)
                    if first_bytes != b"#!":
                        continue
            except Exception:
                continue
            st = script.stat()
            mode = st.st_mode
            if mode & 0o111:
                continue
            new_mode = mode
            if mode & 0o400:
                new_mode |= 0o100
            if mode & 0o040:
                new_mode |= 0o010
            if mode & 0o004:
                new_mode |= 0o001
            if not (new_mode & 0o100):
                new_mode |= 0o100
            os.chmod(script, new_mode)
            updated += 1
        except Exception as e:
            failures.append(f"{script.relative_to(scripts_root)}: {e}")
    if tracker:
        detail = f"{updated} updated" + (f", {len(failures)} failed" if failures else "")
        tracker.add("chmod", "Set script permissions recursively")
        (tracker.error if failures else tracker.complete)("chmod", detail)
    else:
        if updated:
            console.print(f"[cyan]Updated execute permissions on {updated} script(s) recursively[/cyan]")
        if failures:
            console.print("[yellow]Some scripts could not be updated:[/yellow]")
            for failure in failures:
                console.print(f"  - {failure}")


# ===== CLI COMMANDS =====

@app.command()  # type: ignore[misc]
def init(
    project_name: Optional[str] = typer.Argument(None, help="Name for your new project directory (optional if using --here)"),
    script_type: Optional[str] = typer.Option(None, "--script", help="Script type to use: sh or ps"),
    ignore_agent_tools: bool = typer.Option(False, "--ignore-agent-tools", help="Skip checks for Claude Code CLI"),
    no_git: bool = typer.Option(False, "--no-git", help="Skip git repository initialization"),
    here: bool = typer.Option(False, "--here", help="Initialize project in the current directory instead of creating a new one"),
    skip_tls: bool = typer.Option(False, "--skip-tls", help="Skip SSL/TLS verification (not recommended)"),
    debug: bool = typer.Option(False, "--debug", help="Show verbose diagnostic output for network and extraction failures"),
) -> None:
    """Initialize a new Claude Code Specify project from the latest template."""
    show_banner()

    # Validate arguments
    if here and project_name:
        console.print("[red]Error:[/red] Cannot specify both project name and --here flag")
        raise typer.Exit(1)

    if not here and not project_name:
        console.print("[red]Error:[/red] Must specify either a project name or use --here flag")
        raise typer.Exit(1)

    # Determine project directory
    if here:
        project_name = Path.cwd().name
        project_path = Path.cwd()

        existing_items = list(project_path.iterdir())
        if existing_items:
            console.print(f"[yellow]Warning:[/yellow] Current directory is not empty ({len(existing_items)} items)")
            console.print("[yellow]Template files will be merged with existing content and may overwrite existing files[/yellow]")

            response = typer.confirm("Do you want to continue?")
            if not response:
                console.print("[yellow]Operation cancelled[/yellow]")
                raise typer.Exit(0)
    else:
        assert project_name is not None  # mypy: we know this is not None from validation above
        project_path = Path(project_name).resolve()
        if project_path.exists():
            console.print(f"[red]Error:[/red] Directory '{project_name}' already exists")
            raise typer.Exit(1)

    console.print(Panel.fit(
        "[bold cyan]Specify Project Setup[/bold cyan]\n"
        f"{'Initializing in current directory:' if here else 'Creating new project:'} [green]{project_path.name}[/green]"
        + (f"\n[dim]Path: {project_path}[/dim]" if here else ""),
        border_style="cyan"
    ))

    # Check git only if we might need it
    git_available = True
    if not no_git:
        git_available = check_tool("git", "https://git-scm.com/downloads")
        if not git_available:
            console.print("[yellow]Git not found - will skip repository initialization[/yellow]")

    # Using Claude Code as the only supported assistant

    # Check Claude Code CLI unless ignored
    if not ignore_agent_tools:
        if not check_tool("claude", "Install from: https://docs.anthropic.com/en/docs/claude-code/setup"):
            console.print("[red]Error:[/red] Claude Code CLI is required for Specify projects")
            console.print("[yellow]Tip:[/yellow] Use --ignore-agent-tools to skip this check")
            raise typer.Exit(1)

    # Determine script type
    if script_type:
        if script_type not in SCRIPT_TYPE_CHOICES:
            console.print(f"[red]Error:[/red] Invalid script type '{script_type}'. Choose from: {', '.join(SCRIPT_TYPE_CHOICES.keys())}")
            raise typer.Exit(1)
        selected_script = script_type
    else:
        default_script = "ps" if os.name == "nt" else "sh"
        if sys.stdin.isatty():
            selected_script = select_with_arrows(SCRIPT_TYPE_CHOICES, "Choose script type (or press Enter)", default_script)
        else:
            selected_script = default_script

    console.print(f"[cyan]Script type:[/cyan] {selected_script}")

    # Download and set up project
    tracker = StepTracker("Initialize Specify Project")
    tracker.add("precheck", "Check required tools")
    tracker.complete("precheck", "ok")
    tracker.add("script-select", "Select script type")
    tracker.complete("script-select", selected_script)
    for key, label in [
        ("fetch", "Fetch latest release"),
        ("download", "Download template"),
        ("extract", "Extract template"),
        ("zip-list", "Archive contents"),
        ("extracted-summary", "Extraction summary"),
        ("chmod", "Ensure scripts executable"),
        ("cleanup", "Cleanup"),
        ("git", "Initialize git repository"),
        ("final", "Finalize")
    ]:
        tracker.add(key, label)

    with Live(tracker.render(), console=console, refresh_per_second=8, transient=True) as live:
        tracker.attach_refresh(lambda: live.update(tracker.render()))
        try:
            verify = not skip_tls
            local_ssl_context = ssl_context if verify else False
            local_client = httpx.Client(verify=local_ssl_context)

            download_and_extract_template(project_path, selected_script, here, verbose=False, tracker=tracker, client=local_client, debug=debug)

            ensure_executable_scripts(project_path, tracker=tracker)

            if not no_git:
                tracker.start("git")
                if is_git_repo(project_path):
                    tracker.complete("git", "existing repo detected")
                elif git_available:
                    if init_git_repo(project_path, quiet=True):
                        tracker.complete("git", "initialized")
                    else:
                        tracker.error("git", "init failed")
                else:
                    tracker.skip("git", "git not available")
            else:
                tracker.skip("git", "--no-git flag")

            tracker.complete("final", "project ready")
        except Exception as e:
            tracker.error("final", str(e))
            console.print(Panel(f"Initialization failed: {e}", title="Failure", border_style="red"))
            if debug:
                _env_pairs = [
                    ("Python", sys.version.split()[0]),
                    ("Platform", sys.platform),
                    ("CWD", str(Path.cwd())),
                ]
                _label_width = max(len(k) for k, _ in _env_pairs)
                env_lines = [f"{k.ljust(_label_width)} → [bright_black]{v}[/bright_black]" for k, v in _env_pairs]
                console.print(Panel("\n".join(env_lines), title="Debug Environment", border_style="magenta"))
            if not here and project_path.exists():
                shutil.rmtree(project_path)
            raise typer.Exit(1)

    console.print(tracker.render())
    console.print("\n[bold green]Project ready.[/bold green]")

    # Next steps
    steps_lines = []
    if not here:
        steps_lines.append(f"1. [bold green]cd {project_name}[/bold green]")
        step_num = 2
    else:
        steps_lines.append("1. You're already in the project directory!")
        step_num = 2

    steps_lines.append(f"{step_num}. Open in Visual Studio Code and start using / commands with Claude Code")
    steps_lines.append("   - Type / in any file to see available commands")
    steps_lines.append("   - Use /specify to create specifications")
    steps_lines.append("   - Use Claude Code plan mode to create implementation plans (see templates/README-planning.md)")
    steps_lines.append("   - Use /tasks to generate tasks")

    step_num += 1
    steps_lines.append(f"{step_num}. Update [bold magenta]CONSTITUTION.md[/bold magenta] with your project's non-negotiable principles")

    step_num += 1
    steps_lines.append(f"{step_num}. Review documentation in [bold cyan]templates/[/bold cyan] directory:")
    steps_lines.append("   - [bold cyan]templates/README-planning.md[/bold cyan]: Claude Code plan mode workflow")
    steps_lines.append("   - [bold cyan]templates/prompts/plan-prompt.md[/bold cyan]: Planning prompt templates")

    steps_panel = Panel("\n".join(steps_lines), title="Next steps", border_style="cyan", padding=(1,2))
    console.print()
    console.print(steps_panel)


@app.command()  # type: ignore[misc]
def update(
    script_type: Optional[str] = typer.Option(None, "--script", help="Script type to use: sh or ps"),
    ignore_agent_tools: bool = typer.Option(False, "--ignore-agent-tools", help="Skip checks for Claude Code CLI"),
    skip_tls: bool = typer.Option(False, "--skip-tls", help="Skip SSL/TLS verification (not recommended)"),
    debug: bool = typer.Option(False, "--debug", help="Show verbose diagnostic output for network and extraction failures"),
) -> None:
    """Update Claude Code Specify infrastructure while preserving user content."""
    show_banner()

    project_path = Path.cwd()
    project_name = project_path.name

    console.print(Panel.fit(
        "[bold cyan]Specify Project Update[/bold cyan]\n"
        f"Updating infrastructure in: [green]{project_name}[/green]\n"
        "[dim]User content (CONSTITUTION.md, specs/, etc.) will be preserved[/dim]",
        border_style="cyan"
    ))

    # Using Claude Code as the only supported assistant

    # Check Claude Code CLI unless ignored
    if not ignore_agent_tools:
        if not check_tool("claude", "Install from: https://docs.anthropic.com/en/docs/claude-code/setup"):
            console.print("[red]Error:[/red] Claude Code CLI is required for Specify projects")
            console.print("[yellow]Tip:[/yellow] Use --ignore-agent-tools to skip this check")
            raise typer.Exit(1)

    # Determine script type
    if script_type:
        if script_type not in SCRIPT_TYPE_CHOICES:
            console.print(f"[red]Error:[/red] Invalid script type '{script_type}'. Choose from: {', '.join(SCRIPT_TYPE_CHOICES.keys())}")
            raise typer.Exit(1)
        selected_script = script_type
    else:
        default_script = "ps" if os.name == "nt" else "sh"
        if sys.stdin.isatty():
            selected_script = select_with_arrows(SCRIPT_TYPE_CHOICES, "Choose script type (or press Enter)", default_script)
        else:
            selected_script = default_script

    console.print(f"[cyan]Script type:[/cyan] {selected_script}")

    # Update infrastructure
    tracker = StepTracker("Update Specify Infrastructure")
    tracker.add("precheck", "Check required tools")
    tracker.complete("precheck", "ok")
    tracker.add("script-select", "Select script type")
    tracker.complete("script-select", selected_script)
    for key, label in [
        ("fetch", "Fetch latest release"),
        ("download", "Download template"),
        ("extract", "Update infrastructure"),
        ("zip-list", "Archive contents"),
        ("extracted-summary", "Update summary"),
        ("chmod", "Ensure scripts executable"),
        ("cleanup", "Cleanup"),
        ("final", "Finalize")
    ]:
        tracker.add(key, label)

    with Live(tracker.render(), console=console, refresh_per_second=8, transient=True) as live:
        tracker.attach_refresh(lambda: live.update(tracker.render()))
        try:
            verify = not skip_tls
            local_ssl_context = ssl_context if verify else False
            local_client = httpx.Client(verify=local_ssl_context)

            download_and_extract_template(project_path, selected_script, is_current_dir=True, verbose=False, tracker=tracker, client=local_client, debug=debug, update_mode=True)

            ensure_executable_scripts(project_path, tracker=tracker)

            tracker.complete("final", "infrastructure updated")
        except Exception as e:
            tracker.error("final", str(e))
            console.print(f"\n[red]Update failed:[/red] {e}")
            if debug:
                env_lines = [
                    f"Working Directory: {Path.cwd()}",
                    f"Project Path: {project_path}",
                    f"AI Assistant: Claude Code",
                    f"Script Type: {selected_script}",
                    f"Error: {str(e)}"
                ]
                console.print(Panel("\n".join(env_lines), title="Debug Environment", border_style="magenta"))
            raise typer.Exit(1)

    console.print(tracker.render())
    console.print("\n[bold green]Infrastructure updated successfully.[/bold green]")
    console.print("[dim]User content has been preserved during the update[/dim]")


@app.command()  # type: ignore[misc]
def check() -> None:
    """Check that all required tools are installed."""
    show_banner()
    console.print("[bold]Checking for installed tools...[/bold]\n")

    tracker = StepTracker("Check Available Tools")

    tracker.add("git", "Git version control")
    tracker.add("claude", "Claude Code CLI")

    git_ok = check_tool_for_tracker("git", "https://git-scm.com/downloads", tracker)
    claude_ok = check_tool_for_tracker("claude", "https://docs.anthropic.com/en/docs/claude-code/setup", tracker)

    console.print(tracker.render())

    console.print("\n[bold green]Claude Code Specify CLI is ready to use![/bold green]")

    if not git_ok:
        console.print("[dim]Tip: Install git for repository management[/dim]")
    if not claude_ok:
        console.print("[dim]Tip: Install Claude Code CLI for the best experience[/dim]")




@app.command()  # type: ignore[misc]
def tasks(
    _context: Optional[str] = typer.Argument(None, help="Context for task generation (feature name, description, etc.)"),
    max_parallel: int = typer.Option(10, "--max-parallel", help="Maximum parallel sub-agents (1-10)"),
    no_monitoring: bool = typer.Option(False, "--no-monitoring", help="Disable performance monitoring")
) -> None:
    """Generate and launch native Claude Code tasks with balanced orchestration and monitoring."""

    import subprocess
    import json

    # Validate configuration
    if not (1 <= max_parallel <= 10):
        console.print("[red]Error:[/red] max-parallel must be between 1 and 10 (Claude Code limit)")
        raise typer.Exit(1)

    # Create orchestration configuration
    config = OrchestrationConfig(
        max_parallel_agents=max_parallel,
        enable_performance_monitoring=not no_monitoring
    )

    # Run prerequisite check
    try:
        result = subprocess.run(
            ["./scripts/bash/check-task-prerequisites.sh", "--json"],
            capture_output=True,
            text=True,
            check=True
        )
        prereq_data = json.loads(result.stdout)

    except subprocess.CalledProcessError as e:
        console.print("[red]Error:[/red] Prerequisite check failed")
        console.print(f"[dim]{e.stderr if e.stderr else 'Unknown error'}[/dim]")
        raise typer.Exit(1)

    except json.JSONDecodeError as e:
        console.print(f"[red]Error:[/red] Failed to parse prerequisite output: {e}")
        raise typer.Exit(1)

    feature_dir = prereq_data["FEATURE_DIR"]
    available_docs = prereq_data["AVAILABLE_DOCS"]

    console.print(Panel.fit(
        "[bold cyan]Balanced Task Orchestration[/bold cyan]\n"
        f"Feature: [green]{Path(feature_dir).name}[/green]\n"
        f"Max Parallel: [blue]{config.max_parallel_agents}[/blue] | "
        f"Monitoring: [cyan]{'On' if config.enable_performance_monitoring else 'Off'}[/cyan]\n"
        f"Available docs: [dim]{', '.join(available_docs)}[/dim]",
        border_style="cyan"
    ))

    # Load implementation plan
    plan_path = f"{feature_dir}/plan.md"
    try:
        with open(plan_path, 'r') as f:
            plan_content = f.read()
        console.print(f"[green]✓[/green] Loaded implementation plan ({len(plan_content)} characters)")
    except FileNotFoundError:
        console.print(f"[red]Error:[/red] No plan.md found at {plan_path}")
        console.print("[dim]Use Claude Code plan mode to generate implementation plan (see templates/README-planning.md for instructions)[/dim]")
        raise typer.Exit(1)

    # Initialize components with advanced configuration
    processor = PlanProcessor()
    task_manager = NativeTaskManager()
    orchestrator = PhaseOrchestrator(task_manager, config)

    # Parse plan into phases
    with console.status("[blue]Parsing implementation plan with advanced scheduling..."):
        try:
            phases = processor.parse_plan_to_phases(plan_content, available_docs)
            total_tasks = sum(len(phase.tasks) for phase in phases)
            total_duration = sum(phase.estimated_duration for phase in phases)

            console.print(f"[green]✓[/green] Generated {len(phases)} phases with {total_tasks} tasks")
            console.print(f"[dim]Estimated total duration: {total_duration} minutes[/dim]")

        except Exception as e:
            console.print(f"[red]Error:[/red] Failed to parse plan: {e}")
            raise typer.Exit(1)

    # Show enhanced phase summary
    console.print(f"\n[bold]Phase Summary (balanced strategy):[/bold]")
    for phase in phases:
        parallel_count = sum(1 for task in phase.tasks if task.parallel)
        sequential_count = len(phase.tasks) - parallel_count

        console.print(f"  📋 Phase {phase.id}: [cyan]{phase.name}[/cyan]")
        console.print(f"     ⏱️  {phase.estimated_duration}min | 🎯 {phase.priority_boost:.1f}x priority")
        console.print(f"     📝 {len(phase.tasks)} tasks ({parallel_count} parallel, {sequential_count} sequential)")

        if phase.dependencies:
            deps_str = ", ".join(phase.dependencies)
            console.print(f"     🔗 Depends on: {deps_str}")
        console.print()

    # Ask for confirmation with configuration details
    confirmation_text = f"🚀 Launch balanced orchestration?"
    if not typer.confirm(f"\n{confirmation_text}"):
        console.print("[yellow]Operation cancelled[/yellow]")
        return

    # Launch orchestration with advanced features
    console.print(f"\n[bold cyan]🎯 Launching Advanced Orchestration[/bold cyan]")

    try:
        orchestrator.orchestrate_spec_workflow(phases)

        console.print("\n[bold green]✅ Balanced orchestration launched successfully![/bold green]")
        console.print("📊 Monitor progress via Claude Code's native TodoWrite interface")
        console.print("⚡ Task-level parallelism with intelligent scheduling is now active")
        if config.enable_performance_monitoring:
            console.print("📈 Performance monitoring is enabled")
        console.print("\n[dim]Use 'specify task status' to check progress[/dim]")

    except Exception as e:
        console.print(f"[red]Error:[/red] Failed to launch orchestration: {e}")
        raise typer.Exit(1)


def main() -> None:
    app()


if __name__ == "__main__":
    main()