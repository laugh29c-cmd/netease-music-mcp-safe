#!/usr/bin/env python3
"""Load a protected runtime config, remove proxy inheritance, and exec the MCP."""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path
from typing import Any


PROXY_ENVIRONMENT_NAMES = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "no_proxy",
)


def _load_config(path: Path) -> dict[str, Any]:
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise SystemExit(f"Runtime config must not be group/world accessible: {path}")
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise SystemExit("Runtime config must be a JSON object.")
    return value


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: runtime_launcher.py /path/to/runtime.json")
    config = _load_config(Path(sys.argv[1]).expanduser().resolve())
    # Keep the venv launcher path intact. Resolving its symlink would discard the
    # virtual environment and select the system site-packages at exec time.
    python = Path(str(config.get("python", ""))).expanduser().absolute()
    server = Path(str(config.get("server", ""))).resolve()
    working_directory = Path(str(config.get("working_directory", ""))).resolve()
    environment = config.get("environment")
    secrets = config.get("secrets")
    if not python.is_file() or not server.is_file() or not working_directory.is_dir():
        raise SystemExit("Runtime config references a missing executable, server, or directory.")
    if not isinstance(environment, dict) or not isinstance(secrets, dict):
        raise SystemExit("Runtime config environment and secrets must be JSON objects.")

    child_environment = dict(os.environ)
    for name in PROXY_ENVIRONMENT_NAMES:
        child_environment.pop(name, None)
    for values in (environment, secrets):
        for name, value in values.items():
            if not isinstance(name, str) or not isinstance(value, str):
                raise SystemExit("Runtime environment keys and values must be strings.")
            child_environment[name] = value
    if not child_environment.get("MCP_PUBLIC_URL"):
        child_environment.pop("MCP_PUBLIC_URL", None)
        child_environment.pop("MCP_OAUTH_PASSWORD", None)
    child_environment["PYTHONUNBUFFERED"] = "1"

    os.chdir(working_directory)
    os.execve(str(python), [str(python), str(server)], child_environment)


if __name__ == "__main__":
    main()
