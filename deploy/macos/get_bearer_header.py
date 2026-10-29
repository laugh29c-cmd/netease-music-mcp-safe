#!/usr/bin/python3
"""Return the local MCP bearer header without exposing the token in Codex config."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    config_path = (
        Path.home()
        / "Library"
        / "Application Support"
        / "NetEaseMusicMCP"
        / "config"
        / "runtime.json"
    )
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
        token = config["secrets"]["MCP_ACCESS_TOKEN"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"NetEase Music MCP token is unavailable: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    if not isinstance(token, str) or len(token) < 24:
        print("NetEase Music MCP token is invalid.", file=sys.stderr)
        raise SystemExit(1)
    print(json.dumps({"Authorization": "Bearer " + token}))


if __name__ == "__main__":
    main()
