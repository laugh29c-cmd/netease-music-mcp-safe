#!/usr/bin/env python3
"""Install one fault-isolated Cloudflare Tunnel LaunchAgent for the local MCP."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import plistlib
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


LABEL = "com.example.netease-music-mcp-safe-tunnel"
DEFAULT_CLOUDFLARED = Path.home() / ".local" / "bin" / "cloudflared"
DEFAULT_INSTALL_ROOT = (
    Path.home() / "Library" / "Application Support" / "NetEaseMusicMCPTunnel"
)
DIRECT_DNS_RESOLVERS = ("223.5.5.5:53", "114.114.114.114:53")
TUNNEL_PROTOCOL = "quic"
TOKEN_PATTERN = re.compile(r"(?<![A-Za-z0-9_-])(eyJ[A-Za-z0-9_-]{80,})(?![A-Za-z0-9_-])")


def _atomic_bytes(path: Path, value: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        temporary_path.chmod(mode)
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    _atomic_bytes(
        path,
        (json.dumps(value, indent=2, sort_keys=True) + "\n").encode(),
        0o600,
    )


def _read_clipboard_token() -> str:
    result = subprocess.run(
        ["/usr/bin/pbpaste"], capture_output=True, text=True, check=True, timeout=5
    )
    clipboard = result.stdout.strip()
    match = TOKEN_PATTERN.search(clipboard)
    token = match.group(1) if match else clipboard
    if not TOKEN_PATTERN.fullmatch(token):
        raise SystemExit(
            "The clipboard does not contain a Cloudflare Tunnel token or install command."
        )
    return token


def _token_metadata(token: str) -> dict[str, str]:
    padding = "=" * (-len(token) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(token + padding))
    except (ValueError, json.JSONDecodeError):
        raise SystemExit("The Cloudflare Tunnel token is not a valid encoded payload.") from None
    account_id = payload.get("a")
    tunnel_id = payload.get("t")
    if not isinstance(account_id, str) or not isinstance(tunnel_id, str):
        raise SystemExit("The Cloudflare Tunnel token is missing account or tunnel identity.")
    return {"account_id": account_id, "tunnel_id": tunnel_id}


def install(
    source_root: Path,
    install_root: Path,
    cloudflared: Path,
    public_url: str,
    token: str,
) -> dict[str, Any]:
    if not cloudflared.is_file() or not os.access(cloudflared, os.X_OK):
        raise SystemExit(f"cloudflared is not executable: {cloudflared}")
    install_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    install_root.chmod(0o700)
    token_path = install_root / "tunnel.token"
    _atomic_bytes(token_path, (token + "\n").encode(), 0o600)
    launcher = install_root / "direct_exec.py"
    shutil.copy2(source_root / "deploy" / "macos" / "direct_exec.py", launcher)
    launcher.chmod(0o700)

    metadata = {
        **_token_metadata(token),
        "dns_resolvers": list(DIRECT_DNS_RESOLVERS),
        "origin": "http://127.0.0.1:3462",
        "protocol": TUNNEL_PROTOCOL,
        "public_url": public_url,
        "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
    }
    _atomic_json(install_root / "route.json", metadata)

    arguments = [
        "/usr/bin/python3",
        str(launcher),
        str(cloudflared),
        "tunnel",
        "--no-autoupdate",
        "--protocol",
        TUNNEL_PROTOCOL,
        "--edge-ip-version",
        "4",
        "--loglevel",
        "warn",
        "run",
    ]
    for resolver in DIRECT_DNS_RESOLVERS:
        arguments.extend(["--dns-resolver-addrs", resolver])
    arguments.extend(["--token-file", str(token_path)])
    plist = {
        "KeepAlive": True,
        "Label": LABEL,
        "ProgramArguments": arguments,
        "RunAtLoad": True,
        "StandardErrorPath": str(install_root / "stderr.log"),
        "StandardOutPath": str(install_root / "stdout.log"),
        "ThrottleInterval": 30,
        "Umask": 0o077,
    }
    launch_agents = Path.home() / "Library" / "LaunchAgents"
    plist_path = launch_agents / f"{LABEL}.plist"
    _atomic_bytes(plist_path, plistlib.dumps(plist, sort_keys=True), 0o600)

    domain = f"gui/{os.getuid()}"
    subprocess.run(
        ["/bin/launchctl", "bootout", domain, str(plist_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    subprocess.run(
        ["/bin/launchctl", "bootstrap", domain, str(plist_path)],
        capture_output=True,
        text=True,
        check=True,
    )
    subprocess.run(
        ["/bin/launchctl", "kickstart", "-k", f"{domain}/{LABEL}"],
        capture_output=True,
        text=True,
        check=True,
    )
    return {
        "account_id": metadata["account_id"],
        "dns_resolvers": metadata["dns_resolvers"],
        "install_root": str(install_root),
        "label": LABEL,
        "origin": metadata["origin"],
        "plist": str(plist_path),
        "protocol": TUNNEL_PROTOCOL,
        "public_url": public_url,
        "token_sha256": metadata["token_sha256"],
        "tunnel_id": metadata["tunnel_id"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--public-url", required=True)
    parser.add_argument("--token-from-clipboard", action="store_true")
    parser.add_argument("--token-file", type=Path)
    parser.add_argument("--cloudflared", type=Path, default=DEFAULT_CLOUDFLARED)
    parser.add_argument("--install-root", type=Path, default=DEFAULT_INSTALL_ROOT)
    parser.add_argument(
        "--source-root", type=Path, default=Path(__file__).resolve().parents[2]
    )
    arguments = parser.parse_args()
    public_url = arguments.public_url.strip().rstrip("/")
    if not public_url.startswith("https://"):
        raise SystemExit("--public-url must be an HTTPS origin")
    if arguments.token_from_clipboard == bool(arguments.token_file):
        raise SystemExit("Choose exactly one of --token-from-clipboard or --token-file.")
    if arguments.token_from_clipboard:
        token = _read_clipboard_token()
    else:
        token = arguments.token_file.expanduser().read_text(encoding="utf-8").strip()
    receipt = install(
        arguments.source_root.expanduser().resolve(),
        arguments.install_root.expanduser().resolve(),
        arguments.cloudflared.expanduser().resolve(),
        public_url,
        token,
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
