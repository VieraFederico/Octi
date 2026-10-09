"""Configuration is read in exactly one place (spec BR-002, VC-007c).

A narrow text scan (a lint), not a proof: it catches the usual `os.environ` / `os.getenv` spellings.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCANNED = [ROOT / "services", ROOT / "scripts", ROOT / "ui", ROOT / "app.py"]
ALLOWED = {ROOT / "services" / "settings.py"}
ENVIRON_READ = re.compile(r"\bos\.environ\b|\bos\.getenv\b|\bgetenv\(")


def python_files() -> list[Path]:
    files: list[Path] = []
    for target in SCANNED:
        if target.is_file():
            files.append(target)
        elif target.is_dir():
            files.extend(target.rglob("*.py"))
    return files


def test_only_the_settings_module_reads_the_environment() -> None:
    """VC-007c: os.environ / os.getenv appear only in services/settings.py."""
    offenders = [
        str(path.relative_to(ROOT))
        for path in python_files()
        if path not in ALLOWED and ENVIRON_READ.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []
