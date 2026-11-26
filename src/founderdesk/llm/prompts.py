"""Find and sort prompt versions for a given task.

Scans the ``prompts`` directory for files matching ``<task>_v<n>.md`` and returns
them sorted by version number (ascending).
"""

import re
from pathlib import Path

PROMPTS_DIR = Path("prompts")
_VERSION_RE = re.compile(r"^(.+)_v(\d+)\.md$")


def list_versions(task: str) -> list[Path]:
    """Return prompt files for ``task`` sorted by version number, newest last."""
    if not PROMPTS_DIR.is_dir():
        return []
    found: list[tuple[int, Path]] = []
    for path in PROMPTS_DIR.iterdir():
        if not path.is_file():
            continue
        match = _VERSION_RE.match(path.name)
        if match and match.group(1) == task:
            found.append((int(match.group(2)), path))
    found.sort(key=lambda item: item[0])
    return [path for _, path in found]


def latest_version(task: str) -> Path | None:
    """Return the newest prompt file for ``task``, or ``None`` if none exists."""
    versions = list_versions(task)
    return versions[-1] if versions else None
