#!/usr/bin/env python3
"""
Task completion tracking for Specify tasks.md files.

Provides functionality to parse, update, and mark tasks as complete in tasks.md files
following the Spec Kit task format.
"""

import re
from pathlib import Path
from typing import List, Optional, Tuple, Dict
from datetime import datetime


class TaskEntry:
    """Represents a single task entry from tasks.md."""

    def __init__(self, task_id: str, description: str, completed: bool = False, parallel: bool = False, line_number: int = 0):
        self.task_id = task_id
        self.description = description
        self.completed = completed
        self.parallel = parallel  # marked with [P]
        self.line_number = line_number
        self.original_line = ""

    def __repr__(self):
        return f"TaskEntry(id={self.task_id}, completed={self.completed}, desc='{self.description[:50]}...')"


class TaskParser:
    """Parser for tasks.md files following Spec Kit format."""

    # Regex to match task lines like: - [ ] T001 [P] Description
    TASK_PATTERN = re.compile(r'^- \[([x ])\] (T\d{3})(\s*\[P\])?\s*(.+)$', re.IGNORECASE)

    def __init__(self, tasks_file: Path):
        self.tasks_file = tasks_file
        self.tasks: Dict[str, TaskEntry] = {}
        self.file_lines: List[str] = []

        if self.tasks_file.exists():
            self._parse_file()

    def _parse_file(self) -> None:
        """Parse the tasks.md file and extract task entries."""
        with open(self.tasks_file, 'r', encoding='utf-8') as f:
            self.file_lines = f.readlines()

        for line_num, line in enumerate(self.file_lines):
            stripped = line.strip()
            match = self.TASK_PATTERN.match(stripped)

            if match:
                checkbox, task_id, parallel_marker, description = match.groups()
                completed = checkbox.lower() == 'x'
                parallel = parallel_marker is not None

                task = TaskEntry(
                    task_id=task_id,
                    description=description.strip(),
                    completed=completed,
                    parallel=parallel,
                    line_number=line_num
                )
                task.original_line = line
                self.tasks[task_id] = task

    def get_task(self, task_id: str) -> Optional[TaskEntry]:
        """Get a task by its ID (e.g., 'T001')."""
        return self.tasks.get(task_id.upper())

    def get_all_tasks(self) -> List[TaskEntry]:
        """Get all tasks sorted by task ID."""
        return sorted(self.tasks.values(), key=lambda t: t.task_id)

    def get_incomplete_tasks(self) -> List[TaskEntry]:
        """Get all incomplete tasks."""
        return [task for task in self.tasks.values() if not task.completed]

    def get_completed_tasks(self) -> List[TaskEntry]:
        """Get all completed tasks."""
        return [task for task in self.tasks.values() if task.completed]

    def mark_complete(self, task_id: str, commit_message: str = None) -> bool:
        """Mark a task as complete and update the file."""
        task = self.get_task(task_id)
        if not task:
            return False

        if task.completed:
            return True  # Already completed

        # Update the task object
        task.completed = True

        # Update the file line
        old_line = self.file_lines[task.line_number]
        new_line = old_line.replace('- [ ]', '- [x]', 1)

        # Add completion timestamp as a comment if not already present
        if not re.search(r'# Completed:', new_line):
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
            new_line = new_line.rstrip() + f' # Completed: {timestamp}\n'

        self.file_lines[task.line_number] = new_line

        # Write the updated file
        with open(self.tasks_file, 'w', encoding='utf-8') as f:
            f.writelines(self.file_lines)

        return True

    def mark_incomplete(self, task_id: str) -> bool:
        """Mark a task as incomplete and update the file."""
        task = self.get_task(task_id)
        if not task:
            return False

        if not task.completed:
            return True  # Already incomplete

        # Update the task object
        task.completed = False

        # Update the file line
        old_line = self.file_lines[task.line_number]
        new_line = old_line.replace('- [x]', '- [ ]', 1)

        # Remove completion timestamp if present
        new_line = re.sub(r'\s*# Completed:.*$', '\n', new_line)

        self.file_lines[task.line_number] = new_line

        # Write the updated file
        with open(self.tasks_file, 'w', encoding='utf-8') as f:
            f.writelines(self.file_lines)

        return True

    def get_progress_summary(self) -> Dict[str, int]:
        """Get a summary of task progress."""
        total = len(self.tasks)
        completed = len(self.get_completed_tasks())
        incomplete = total - completed

        return {
            'total': total,
            'completed': completed,
            'incomplete': incomplete,
            'progress_pct': round((completed / total * 100) if total > 0 else 0, 1)
        }


def find_tasks_file(start_path: Path = None) -> Optional[Path]:
    """Find the tasks.md file for the current feature branch."""
    if start_path is None:
        start_path = Path.cwd()

    try:
        # Use the same logic as the bash scripts
        import subprocess
        result = subprocess.run(
            ['git', 'rev-parse', '--show-toplevel'],
            capture_output=True,
            text=True,
            check=True,
            cwd=start_path
        )
        repo_root = Path(result.stdout.strip())

        result = subprocess.run(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            capture_output=True,
            text=True,
            check=True,
            cwd=start_path
        )
        current_branch = result.stdout.strip()

        # Check if it's a feature branch (###-feature-name format)
        if not re.match(r'^\d{3}-', current_branch):
            return None

        feature_dir = repo_root / 'specs' / current_branch
        tasks_file = feature_dir / 'tasks.md'

        return tasks_file if tasks_file.exists() else None

    except (subprocess.CalledProcessError, FileNotFoundError):
        return None