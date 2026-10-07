#!/usr/bin/env python3
"""PreToolUse hook: block Claude from touching the real .env file.

Inspects only the *target* of a tool call (file paths, glob/grep patterns, shell commands),
never file contents, so writing docs that mention ".env" stays possible.
Allows `.env.example`; blocks `.env`, `.env.local`, `.env*` globs, `/any/path/.env`, etc.
"""

import json
import re
import sys

# ".env" not preceded by a word char or dot, not followed by ".example" or a word char/dash.
ENV_PATTERN = re.compile(r"(?<![\w.])\.env(?!\.example\b)(?![\w-])")
TARGET_KEYS = ("file_path", "path", "notebook_path", "pattern", "glob", "command")


def main() -> None:
    payload = json.load(sys.stdin)
    tool_input = payload.get("tool_input") or {}
    targets = [str(tool_input[key]) for key in TARGET_KEYS if tool_input.get(key)]
    if any(ENV_PATTERN.search(target) for target in targets):
        json.dump(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        "Blocked by project rule: Claude must never read, edit or expose .env. "
                        "Use .env.example for variable names; the student manages .env."
                    ),
                }
            },
            sys.stdout,
        )


if __name__ == "__main__":
    main()
