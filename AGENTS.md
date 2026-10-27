# Project instructions

This repository distributes the APINebula asynchronous image skill for Codex on macOS and Windows. Keep installation and execution portable across both platforms; use pathlib and Python subprocess argument lists, not shell-specific commands.

The skill instructions live in apinebula-imagegen/SKILL.md. Keep API and storage credentials in the user configuration directory outside this repository. Logs and task files must not expose credentials or presigned URLs. Preserve task IDs across interrupted downloads; never automatically retry a generation POST.

Run offline tests with the skill virtual environment: python -m unittest discover -s apinebula-imagegen/tests -v. Live generation and storage tests require appropriate user authorization and credentials. Distinguish offline checks from actual Windows or provider validation.

When changing dependencies, update requirements.txt and requirements.lock together. Keep the installer, README and platform setup examples consistent. Use main as the default branch; use codex/ branches and pull requests for subsequent changes.
