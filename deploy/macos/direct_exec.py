#!/usr/bin/env python3
"""Exec a transport command without inheriting proxy environment variables."""

from __future__ import annotations

import os
import sys


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


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: direct_exec.py command [args ...]")
    environment = dict(os.environ)
    for name in PROXY_ENVIRONMENT_NAMES:
        environment.pop(name, None)
    os.execve(sys.argv[1], sys.argv[1:], environment)


if __name__ == "__main__":
    main()
