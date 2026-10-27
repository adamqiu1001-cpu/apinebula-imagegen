#!/usr/bin/env python3
"""Install the sibling Codex skill without copying any personal credentials."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import venv


def install(destination=None, dependencies=True):
    if sys.version_info < (3, 10):
        raise SystemExit("Python 3.10 or newer is required")
    source = Path(__file__).resolve().parent / "apinebula-imagegen"
    target = destination or Path.home() / ".agents" / "skills" / source.name
    if target.exists():
        raise SystemExit("Destination already exists. Preserve it and choose another --destination, or review an update manually.")
    shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".venv"))
    print("Skill copied to:", target, flush=True)
    if dependencies:
        venv.EnvBuilder(with_pip=True).create(target / ".venv")
        python = target / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        requirements = target / "requirements.lock"
        if not requirements.exists():
            requirements = target / "requirements.txt"
        subprocess.run([str(python), "-m", "pip", "install", "-r", str(requirements)], check=True)
        print("Python:", python)
        print("Configure key in your own terminal:")
        print('"' + str(python) + '" "' + str(target / "scripts/apinebula_image.py") + '" configure-key')
        if os.name == "nt":
            print("PowerShell: prefix the quoted command above with &")
    print("Open a new Codex conversation; invoke $apinebula-imagegen.")
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, help="Override the full skill destination folder")
    parser.add_argument("--no-deps", action="store_true", help="Copy only; install requirements separately")
    args = parser.parse_args()
    try:
        install(args.destination, not args.no_deps)
    except subprocess.CalledProcessError:
        raise SystemExit("Dependency installation failed; skill files remain. See references/setup.md to repair installation.")
