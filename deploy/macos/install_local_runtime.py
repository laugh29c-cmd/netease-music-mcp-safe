#!/usr/bin/env python3
"""Install the NetEase MCP as one isolated macOS LaunchAgent."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import plistlib
import secrets
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


LABEL = "com.example.netease-music-mcp-safe"
DEFAULT_PORT = 3462
APP_FILES = (
    "image_safety.py",
    "mac_playback.py",
    "mobile_playback.py",
    "netease_session.py",
    "persistence.py",
    "requirements.txt",
    "server.py",
)
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
DEPENDENCY_PATH_PATTERNS = (
    "PIL",
    "pillow-*.dist-info",
    "Crypto",
    "pycryptodome-*.dist-info",
    "qrcode",
    "qrcode-*.dist-info",
    "tzdata",
    "tzdata-*.dist-info",
)


def _atomic_json(path: Path, value: dict[str, Any], mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary_path.chmod(mode)
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _atomic_plist(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(fd, "wb") as handle:
            plistlib.dump(value, handle, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        temporary_path.chmod(0o600)
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _read_existing_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    return value if isinstance(value, dict) else {}


def _clean_environment() -> dict[str, str]:
    environment = dict(os.environ)
    for name in PROXY_ENVIRONMENT_NAMES:
        environment.pop(name, None)
    environment["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    return environment


def _run(
    command: list[str], *, check: bool = True, timeout: int = 120
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=check,
        capture_output=True,
        text=True,
        env=_clean_environment(),
        timeout=timeout,
    )


def _python_path(python: Path, expression: str) -> Path:
    result = _run([str(python), "-c", expression])
    return Path(result.stdout.strip()).resolve()


def _copy_verified_dependencies(source_python: Path, target_python: Path) -> None:
    source_site_packages = _python_path(
        source_python, "import sysconfig; print(sysconfig.get_paths()['purelib'])"
    )
    target_site_packages = _python_path(
        target_python, "import sysconfig; print(sysconfig.get_paths()['purelib'])"
    )
    target_site_packages.mkdir(parents=True, exist_ok=True)
    copied: set[str] = set()
    for pattern in DEPENDENCY_PATH_PATTERNS:
        matches = sorted(source_site_packages.glob(pattern))
        if not matches:
            raise SystemExit(
                f"Verified dependency {pattern} is missing from {source_site_packages}"
            )
        for source in matches:
            destination = target_site_packages / source.name
            if destination.exists():
                if destination.is_dir() and not destination.is_symlink():
                    shutil.rmtree(destination)
                else:
                    destination.unlink()
            if source.is_dir():
                shutil.copytree(source, destination, symlinks=True)
            else:
                shutil.copy2(source, destination)
            copied.add(source.name)
    _run(
        [
            str(target_python),
            "-c",
            "import Crypto, PIL, qrcode, tzdata; print('verified')",
        ]
    )
    if len(copied) < 8:
        raise SystemExit("Verified dependency copy was incomplete.")


def install(
    source_root: Path,
    install_root: Path,
    dependency_python: Path,
    port: int,
    public_url: str,
) -> dict[str, Any]:
    app_directory = install_root / "app"
    config_directory = install_root / "config"
    data_directory = install_root / "data"
    log_directory = install_root / "logs"
    virtual_environment = install_root / ".venv"
    for directory in (
        install_root,
        app_directory,
        config_directory,
        data_directory,
        log_directory,
    ):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        directory.chmod(0o700)

    for relative in APP_FILES:
        source = source_root / relative
        if not source.is_file():
            raise SystemExit(f"Required source file is missing: {source}")
        shutil.copy2(source, app_directory / relative)
    launcher = install_root / "runtime_launcher.py"
    shutil.copy2(source_root / "deploy" / "macos" / "runtime_launcher.py", launcher)
    launcher.chmod(0o700)
    helper_directory = Path.home() / ".codex" / "mcp-helpers"
    helper_directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    helper_directory.chmod(0o700)
    header_helper = helper_directory / "netease_music_header.py"
    shutil.copy2(source_root / "deploy" / "macos" / "get_bearer_header.py", header_helper)
    header_helper.chmod(0o700)

    if not (virtual_environment / "bin" / "python").is_file():
        _run([sys.executable, "-m", "venv", str(virtual_environment)])
    python = virtual_environment / "bin" / "python"
    if not dependency_python.is_file():
        raise SystemExit(
            "The tested dependency Python is missing. Run the source test setup first or pass "
            "--dependency-python."
        )
    _copy_verified_dependencies(dependency_python, python)
    freeze = _run([str(python), "-m", "pip", "freeze"]).stdout
    lock_path = install_root / "requirements.lock.txt"
    lock_path.write_text(freeze, encoding="utf-8")
    lock_path.chmod(0o600)

    config_path = config_directory / "runtime.json"
    existing = _read_existing_config(config_path)
    existing_secrets = existing.get("secrets")
    if not isinstance(existing_secrets, dict):
        existing_secrets = {}
    access_token = existing_secrets.get("MCP_ACCESS_TOKEN")
    oauth_password = existing_secrets.get("MCP_OAUTH_PASSWORD")
    if not isinstance(access_token, str) or len(access_token) < 24:
        access_token = secrets.token_urlsafe(48)
    if not isinstance(oauth_password, str) or len(oauth_password) < 24:
        oauth_password = secrets.token_urlsafe(48)
    if secrets.compare_digest(access_token, oauth_password):
        oauth_password = secrets.token_urlsafe(48)

    environment = {
        "LOG_LEVEL": "INFO",
        "MCP_DEFAULT_TIMEZONE": "Asia/Shanghai",
        "MCP_HOST": "127.0.0.1",
        "MCP_MAC_PLAYBACK_ENABLED": "true",
        "MCP_MOBILE_PLAYBACK_ENABLED": "true",
        "MCP_MAX_REQUEST_BYTES": "1048576",
        "MCP_OPERATION_RETENTION_DAYS": "90",
        "MCP_PORT": str(port),
        "MCP_PUBLIC_URL": public_url,
        "MCP_READ_ONLY": "true",
        "MCP_STORAGE_PATH": str(data_directory / "netease-music-mcp.sqlite3"),
    }
    config = {
        "environment": environment,
        "python": str(python),
        "secrets": {
            "MCP_ACCESS_TOKEN": access_token,
            "MCP_OAUTH_PASSWORD": oauth_password,
        },
        "server": str(app_directory / "server.py"),
        "working_directory": str(app_directory),
    }
    _atomic_json(config_path, config)

    home = Path.home()
    launch_agents = home / "Library" / "LaunchAgents"
    plist_path = launch_agents / f"{LABEL}.plist"
    plist = {
        "Label": LABEL,
        "LimitLoadToSessionType": "Aqua",
        "ProgramArguments": [str(python), str(launcher), str(config_path)],
        "RunAtLoad": True,
        "KeepAlive": True,
        "ProcessType": "Background",
        "StandardErrorPath": str(log_directory / "server.err.log"),
        "StandardOutPath": str(log_directory / "server.out.log"),
        "ThrottleInterval": 10,
        "Umask": 0o077,
        "WorkingDirectory": str(app_directory),
    }
    _atomic_plist(plist_path, plist)

    domain = f"gui/{os.getuid()}"
    _run(["/bin/launchctl", "bootout", domain, str(plist_path)], check=False)
    _run(["/bin/launchctl", "bootstrap", domain, str(plist_path)])
    _run(["/bin/launchctl", "kickstart", "-k", f"{domain}/{LABEL}"])

    return {
        "access_token_sha256": hashlib.sha256(access_token.encode()).hexdigest(),
        "config": str(config_path),
        "http_headers_helper": str(header_helper),
        "install_root": str(install_root),
        "label": LABEL,
        "plist": str(plist_path),
        "port": port,
        "public_url_configured": bool(public_url),
        "read_only": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
    )
    parser.add_argument(
        "--install-root",
        type=Path,
        default=Path.home() / "Library" / "Application Support" / "NetEaseMusicMCP",
    )
    parser.add_argument(
        "--dependency-python",
        type=Path,
        default=Path(__file__).resolve().parents[2] / ".venv" / "bin" / "python",
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--public-url", default="")
    arguments = parser.parse_args()
    if not 1024 <= arguments.port <= 65535:
        raise SystemExit("--port must be between 1024 and 65535")
    public_url = arguments.public_url.strip().rstrip("/")
    if public_url and not public_url.startswith("https://"):
        raise SystemExit("--public-url must be an HTTPS origin")
    receipt = install(
        arguments.source_root.expanduser().resolve(),
        arguments.install_root.expanduser().resolve(),
        arguments.dependency_python.expanduser().absolute(),
        arguments.port,
        public_url,
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
