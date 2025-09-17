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
Specify CLI - Setup tool for Specify projects with task management

Usage:
    uv run specify.py init <project-name>
    uv run specify.py update
    uv run specify.py task complete T001
    uv run specify.py task status

Or install globally:
    uv tool install specify.py
    specify init <project-name>
    specify update
    specify task complete T001
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

# Constants
AI_CHOICES = {
    "copilot": "GitHub Copilot",
    "claude": "Claude Code",
    "gemini": "Gemini CLI",
    "cursor": "Cursor"
}
SCRIPT_TYPE_CHOICES = {"sh": "POSIX Shell (bash/zsh)", "ps": "PowerShell"}

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

# ===== TASK TRACKING CLASSES =====

class TaskEntry:
    """Represents a single task entry from tasks.md."""

    def __init__(self, task_id: str, description: str, completed: bool = False, parallel: bool = False, line_number: int = 0) -> None:
        self.task_id = task_id
        self.description = description
        self.completed = completed
        self.parallel = parallel  # marked with [P]
        self.line_number = line_number
        self.original_line = ""

    def __repr__(self) -> str:
        return f"TaskEntry(id={self.task_id}, completed={self.completed}, desc='{self.description[:50]}...')"


class TaskParser:
    """Parser for tasks.md files following Spec Kit format."""

    # Regex to match task lines like: - [ ] T001 [P] Description
    TASK_PATTERN = re.compile(r'^- \[([x ])\] (T\d{3})(\s*\[P\])?\s*(.+)$', re.IGNORECASE)

    def __init__(self, tasks_file: Path) -> None:
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

    def mark_complete(self, task_id: str, commit_message: Optional[str] = None) -> bool:
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

    def get_progress_summary(self) -> Dict[str, Union[int, float]]:
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


def find_tasks_file(start_path: Optional[Path] = None) -> Optional[Path]:
    """Find the tasks.md file for the current feature branch."""
    if start_path is None:
        start_path = Path.cwd()

    try:
        # Use the same logic as the bash scripts
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
    help="Setup tool for Specify spec-driven development projects with task management",
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


def download_template_from_github(ai_assistant: str, download_dir: Path, *, script_type: str = "sh", verbose: bool = True, show_progress: bool = True, client: Optional[httpx.Client] = None, debug: bool = False) -> Tuple[Path, Dict[str, Any]]:
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

    # Find the template asset for the specified AI assistant
    pattern = f"spec-kit-template-{ai_assistant}-{script_type}"
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


def download_and_extract_template(project_path: Path, ai_assistant: str, script_type: str, is_current_dir: bool = False, *, verbose: bool = True, tracker: Optional[StepTracker] = None, client: Optional[httpx.Client] = None, debug: bool = False, update_mode: bool = False) -> Path:
    """Download the latest release and extract it to create a new project."""
    current_dir = Path.cwd()

    if tracker:
        tracker.start("fetch", "contacting GitHub API")
    try:
        zip_path, meta = download_template_from_github(
            ai_assistant,
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
    ai_assistant: Optional[str] = typer.Option(None, "--ai", help="AI assistant to use: claude, gemini, copilot, or cursor"),
    script_type: Optional[str] = typer.Option(None, "--script", help="Script type to use: sh or ps"),
    ignore_agent_tools: bool = typer.Option(False, "--ignore-agent-tools", help="Skip checks for AI agent tools like Claude Code"),
    no_git: bool = typer.Option(False, "--no-git", help="Skip git repository initialization"),
    here: bool = typer.Option(False, "--here", help="Initialize project in the current directory instead of creating a new one"),
    skip_tls: bool = typer.Option(False, "--skip-tls", help="Skip SSL/TLS verification (not recommended)"),
    debug: bool = typer.Option(False, "--debug", help="Show verbose diagnostic output for network and extraction failures"),
) -> None:
    """Initialize a new Specify project from the latest template."""
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

    # AI assistant selection
    if ai_assistant:
        if ai_assistant not in AI_CHOICES:
            console.print(f"[red]Error:[/red] Invalid AI assistant '{ai_assistant}'. Choose from: {', '.join(AI_CHOICES.keys())}")
            raise typer.Exit(1)
        selected_ai = ai_assistant
    else:
        selected_ai = select_with_arrows(
            AI_CHOICES,
            "Choose your AI assistant:",
            "copilot"
        )

    # Check agent tools unless ignored
    if not ignore_agent_tools:
        agent_tool_missing = False
        if selected_ai == "claude":
            if not check_tool("claude", "Install from: https://docs.anthropic.com/en/docs/claude-code/setup"):
                console.print("[red]Error:[/red] Claude CLI is required for Claude Code projects")
                agent_tool_missing = True
        elif selected_ai == "gemini":
            if not check_tool("gemini", "Install from: https://github.com/google-gemini/gemini-cli"):
                console.print("[red]Error:[/red] Gemini CLI is required for Gemini projects")
                agent_tool_missing = True

        if agent_tool_missing:
            console.print("\n[red]Required AI tool is missing![/red]")
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

    console.print(f"[cyan]Selected AI assistant:[/cyan] {selected_ai}")
    console.print(f"[cyan]Selected script type:[/cyan] {selected_script}")

    # Download and set up project
    tracker = StepTracker("Initialize Specify Project")
    tracker.add("precheck", "Check required tools")
    tracker.complete("precheck", "ok")
    tracker.add("ai-select", "Select AI assistant")
    tracker.complete("ai-select", f"{selected_ai}")
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

            download_and_extract_template(project_path, selected_ai, selected_script, here, verbose=False, tracker=tracker, client=local_client, debug=debug)

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

    if selected_ai == "claude":
        steps_lines.append(f"{step_num}. Open in Visual Studio Code and start using / commands with Claude Code")
        steps_lines.append("   - Type / in any file to see available commands")
        steps_lines.append("   - Use /specify to create specifications")
        steps_lines.append("   - Use /plan to create implementation plans")
        steps_lines.append("   - Use /tasks to generate tasks")
    elif selected_ai == "gemini":
        steps_lines.append(f"{step_num}. Use / commands with Gemini CLI")
        steps_lines.append("   - Run gemini /specify to create specifications")
        steps_lines.append("   - Run gemini /plan to create implementation plans")
        steps_lines.append("   - Run gemini /tasks to generate tasks")
        steps_lines.append("   - See GEMINI.md for all available commands")
    elif selected_ai == "copilot":
        steps_lines.append(f"{step_num}. Open in Visual Studio Code and use [bold cyan]/specify[/], [bold cyan]/plan[/], [bold cyan]/tasks[/] commands with GitHub Copilot")

    step_num += 1
    steps_lines.append(f"{step_num}. Update [bold magenta]CONSTITUTION.md[/bold magenta] with your project's non-negotiable principles")

    steps_panel = Panel("\n".join(steps_lines), title="Next steps", border_style="cyan", padding=(1,2))
    console.print()
    console.print(steps_panel)


@app.command()  # type: ignore[misc]
def update(
    ai_assistant: Optional[str] = typer.Option(None, "--ai", help="AI assistant to use: claude, gemini, copilot, or cursor"),
    script_type: Optional[str] = typer.Option(None, "--script", help="Script type to use: sh or ps"),
    ignore_agent_tools: bool = typer.Option(False, "--ignore-agent-tools", help="Skip checks for AI agent tools like Claude Code"),
    skip_tls: bool = typer.Option(False, "--skip-tls", help="Skip SSL/TLS verification (not recommended)"),
    debug: bool = typer.Option(False, "--debug", help="Show verbose diagnostic output for network and extraction failures"),
) -> None:
    """Update Spec Kit infrastructure while preserving user content."""
    show_banner()

    project_path = Path.cwd()
    project_name = project_path.name

    console.print(Panel.fit(
        "[bold cyan]Specify Project Update[/bold cyan]\n"
        f"Updating infrastructure in: [green]{project_name}[/green]\n"
        "[dim]User content (CONSTITUTION.md, specs/, etc.) will be preserved[/dim]",
        border_style="cyan"
    ))

    # AI assistant selection
    if ai_assistant:
        if ai_assistant not in AI_CHOICES:
            console.print(f"[red]Error:[/red] Invalid AI assistant '{ai_assistant}'. Choose from: {', '.join(AI_CHOICES.keys())}")
            raise typer.Exit(1)
        selected_ai = ai_assistant
    else:
        selected_ai = select_with_arrows(
            AI_CHOICES,
            "Choose your AI assistant:",
            "copilot"
        )

    # Check agent tools unless ignored
    if not ignore_agent_tools:
        agent_tool_missing = False
        if selected_ai == "claude":
            if not check_tool("claude", "Install from: https://docs.anthropic.com/en/docs/claude-code/setup"):
                console.print("[red]Error:[/red] Claude CLI is required for Claude Code projects")
                agent_tool_missing = True
        elif selected_ai == "gemini":
            if not check_tool("gemini", "Install from: https://github.com/google-gemini/gemini-cli"):
                console.print("[red]Error:[/red] Gemini CLI is required for Gemini projects")
                agent_tool_missing = True

        if agent_tool_missing:
            console.print("\n[red]Required AI tool is missing![/red]")
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

    console.print(f"[cyan]Selected AI assistant:[/cyan] {selected_ai}")
    console.print(f"[cyan]Selected script type:[/cyan] {selected_script}")

    # Update infrastructure
    tracker = StepTracker("Update Specify Infrastructure")
    tracker.add("precheck", "Check required tools")
    tracker.complete("precheck", "ok")
    tracker.add("ai-select", "Select AI assistant")
    tracker.complete("ai-select", f"{selected_ai}")
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

            download_and_extract_template(project_path, selected_ai, selected_script, is_current_dir=True, verbose=False, tracker=tracker, client=local_client, debug=debug, update_mode=True)

            ensure_executable_scripts(project_path, tracker=tracker)

            tracker.complete("final", "infrastructure updated")
        except Exception as e:
            tracker.error("final", str(e))
            console.print(f"\n[red]Update failed:[/red] {e}")
            if debug:
                env_lines = [
                    f"Working Directory: {Path.cwd()}",
                    f"Project Path: {project_path}",
                    f"AI Assistant: {selected_ai}",
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
    tracker.add("gemini", "Gemini CLI")
    tracker.add("code", "VS Code (for GitHub Copilot)")
    tracker.add("cursor-agent", "Cursor IDE agent (optional)")

    git_ok = check_tool_for_tracker("git", "https://git-scm.com/downloads", tracker)
    claude_ok = check_tool_for_tracker("claude", "https://docs.anthropic.com/en/docs/claude-code/setup", tracker)
    gemini_ok = check_tool_for_tracker("gemini", "https://github.com/google-gemini/gemini-cli", tracker)
    code_ok = check_tool_for_tracker("code", "https://code.visualstudio.com/", tracker)
    if not code_ok:
        code_ok = check_tool_for_tracker("code-insiders", "https://code.visualstudio.com/insiders/", tracker)
    check_tool_for_tracker("cursor-agent", "https://cursor.sh/", tracker)

    console.print(tracker.render())

    console.print("\n[bold green]Specify CLI is ready to use![/bold green]")

    if not git_ok:
        console.print("[dim]Tip: Install git for repository management[/dim]")
    if not (claude_ok or gemini_ok):
        console.print("[dim]Tip: Install an AI assistant for the best experience[/dim]")


# Task management commands
task_app = typer.Typer(help="Manage tasks in the current feature's tasks.md file")
app.add_typer(task_app, name="task")


@task_app.command("complete")  # type: ignore[misc]
def task_complete(
    task_id: str = typer.Argument(..., help="Task ID to mark complete (e.g., T001)"),
    message: Optional[str] = typer.Option(None, "--message", "-m", help="Optional commit message describing what was completed")
) -> None:
    """Mark a task as complete in the tasks.md file."""
    tasks_file = find_tasks_file()
    if not tasks_file:
        console.print("[red]Error:[/red] No tasks.md found for current feature branch")
        console.print("[dim]Make sure you're on a feature branch (001-feature-name) and have run /tasks[/dim]")
        raise typer.Exit(1)

    parser = TaskParser(tasks_file)
    task = parser.get_task(task_id)

    if not task:
        console.print(f"[red]Error:[/red] Task '{task_id}' not found in {tasks_file.name}")
        console.print("\n[dim]Available tasks:[/dim]")
        for t in parser.get_all_tasks():
            status = "✓" if t.completed else "○"
            parallel = "[P]" if t.parallel else ""
            console.print(f"  {status} {t.task_id} {parallel} {t.description[:60]}...")
        raise typer.Exit(1)

    if task.completed:
        console.print(f"[yellow]Task {task_id} is already completed[/yellow]")
        return

    success = parser.mark_complete(task_id, message)
    if success:
        console.print(f"[green]✓[/green] Marked {task_id} as complete: [dim]{task.description}[/dim]")

        summary = parser.get_progress_summary()
        console.print(f"[dim]Progress: {summary['completed']}/{summary['total']} tasks ({summary['progress_pct']}%)[/dim]")

        if message:
            console.print(f"\n[dim]Consider committing with:[/dim] git commit -m \"{message}\"")
    else:
        console.print(f"[red]Error:[/red] Failed to mark {task_id} as complete")
        raise typer.Exit(1)


@task_app.command("status")  # type: ignore[misc]
def task_status() -> None:
    """Show status of all tasks in the current feature."""
    tasks_file = find_tasks_file()
    if not tasks_file:
        console.print("[red]Error:[/red] No tasks.md found for current feature branch")
        console.print("[dim]Make sure you're on a feature branch (001-feature-name) and have run /tasks[/dim]")
        raise typer.Exit(1)

    parser = TaskParser(tasks_file)
    all_tasks = parser.get_all_tasks()

    if not all_tasks:
        console.print(f"[yellow]No tasks found in {tasks_file.name}[/yellow]")
        return

    summary = parser.get_progress_summary()
    console.print(f"\n[bold]Task Progress:[/bold] {summary['completed']}/{summary['total']} ({summary['progress_pct']}%)")
    console.print(f"[dim]File: {tasks_file}[/dim]\n")

    incomplete = parser.get_incomplete_tasks()
    completed = parser.get_completed_tasks()

    if incomplete:
        console.print("[bold]Incomplete Tasks:[/bold]")
        for task in incomplete:
            parallel = "[cyan][P][/cyan]" if task.parallel else ""
            console.print(f"  [red]○[/red] {task.task_id} {parallel} {task.description}")
        console.print()

    if completed:
        console.print("[bold]Completed Tasks:[/bold]")
        for task in completed:
            parallel = "[cyan][P][/cyan]" if task.parallel else ""
            console.print(f"  [green]✓[/green] {task.task_id} {parallel} {task.description}")


@task_app.command("list")  # type: ignore[misc]
def task_list(
    incomplete_only: bool = typer.Option(False, "--incomplete", "-i", help="Show only incomplete tasks")
) -> None:
    """List all tasks in the current feature."""
    tasks_file = find_tasks_file()
    if not tasks_file:
        console.print("[red]Error:[/red] No tasks.md found for current feature branch")
        console.print("[dim]Make sure you're on a feature branch (001-feature-name) and have run /tasks[/dim]")
        raise typer.Exit(1)

    parser = TaskParser(tasks_file)

    if incomplete_only:
        tasks_to_show = parser.get_incomplete_tasks()
        console.print(f"\n[bold]Incomplete Tasks ({len(tasks_to_show)}):[/bold]")
    else:
        tasks_to_show = parser.get_all_tasks()
        summary = parser.get_progress_summary()
        console.print(f"\n[bold]All Tasks ({summary['completed']}/{summary['total']}):[/bold]")

    if not tasks_to_show:
        console.print("[dim]No tasks to show[/dim]")
        return

    console.print(f"[dim]File: {tasks_file}[/dim]\n")

    for task in tasks_to_show:
        status = "[green]✓[/green]" if task.completed else "[red]○[/red]"
        parallel = "[cyan][P][/cyan]" if task.parallel else ""
        console.print(f"  {status} {task.task_id} {parallel} {task.description}")


@task_app.command("uncomplete")  # type: ignore[misc]
def task_uncomplete(
    task_id: str = typer.Argument(..., help="Task ID to mark incomplete (e.g., T001)")
) -> None:
    """Mark a task as incomplete in the tasks.md file."""
    tasks_file = find_tasks_file()
    if not tasks_file:
        console.print("[red]Error:[/red] No tasks.md found for current feature branch")
        raise typer.Exit(1)

    parser = TaskParser(tasks_file)
    task = parser.get_task(task_id)

    if not task:
        console.print(f"[red]Error:[/red] Task '{task_id}' not found")
        raise typer.Exit(1)

    if not task.completed:
        console.print(f"[yellow]Task {task_id} is already incomplete[/yellow]")
        return

    success = parser.mark_incomplete(task_id)
    if success:
        console.print(f"[green]○[/green] Marked {task_id} as incomplete: [dim]{task.description}[/dim]")

        summary = parser.get_progress_summary()
        console.print(f"[dim]Progress: {summary['completed']}/{summary['total']} tasks ({summary['progress_pct']}%)[/dim]")
    else:
        console.print(f"[red]Error:[/red] Failed to mark {task_id} as incomplete")
        raise typer.Exit(1)


def main() -> None:
    app()


if __name__ == "__main__":
    main()