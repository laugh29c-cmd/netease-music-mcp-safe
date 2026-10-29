import base64
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    path = ROOT / "deploy" / "macos" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"test_{name}", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class MacDeployTests(unittest.TestCase):
    def test_cloudflare_token_identity_and_clipboard_command_are_bounded(self):
        module = load_script("install_cloudflare_tunnel")
        account_id = "1" * 32
        tunnel_id = "00000000-0000-4000-8000-000000000001"
        payload = json.dumps({"a": account_id, "t": tunnel_id, "s": "x" * 48})
        token = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
        self.assertEqual(
            module._token_metadata(token),
            {"account_id": account_id, "tunnel_id": tunnel_id},
        )
        copied = subprocess.CompletedProcess(
            ["pbpaste"], 0, f"cloudflared service install {token}\n", ""
        )
        with mock.patch.object(module.subprocess, "run", return_value=copied):
            self.assertEqual(module._read_clipboard_token(), token)

    def test_direct_exec_strips_proxy_environment(self):
        module = load_script("direct_exec")
        environment = {
            "HOME": "/Users/test",
            "HTTP_PROXY": "http://127.0.0.1:7890",
            "https_proxy": "http://127.0.0.1:7890",
        }
        with mock.patch.object(module.sys, "argv", ["direct_exec.py", "/bin/tool", "x"]), mock.patch.dict(
            module.os.environ, environment, clear=True
        ), mock.patch.object(module.os, "execve") as execve:
            module.main()
        executable, arguments, child_environment = execve.call_args.args
        self.assertEqual(executable, "/bin/tool")
        self.assertEqual(arguments, ["/bin/tool", "x"])
        self.assertEqual(child_environment["HOME"], "/Users/test")
        self.assertNotIn("HTTP_PROXY", child_environment)
        self.assertNotIn("https_proxy", child_environment)

    def test_runtime_launcher_preserves_virtualenv_symlink(self):
        module = load_script("runtime_launcher")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            python = root / "python"
            python.symlink_to(sys.executable)
            server = root / "server.py"
            server.write_text("pass\n", encoding="utf-8")
            config = root / "runtime.json"
            config.write_text(
                json.dumps(
                    {
                        "environment": {"MCP_PUBLIC_URL": ""},
                        "python": str(python),
                        "secrets": {"MCP_OAUTH_PASSWORD": "hidden"},
                        "server": str(server),
                        "working_directory": str(root),
                    }
                ),
                encoding="utf-8",
            )
            config.chmod(0o600)
            with mock.patch.object(module.sys, "argv", ["runtime_launcher.py", str(config)]), mock.patch.object(
                module.os, "chdir"
            ), mock.patch.object(module.os, "execve") as execve:
                module.main()
        executable, arguments, child_environment = execve.call_args.args
        self.assertEqual(executable, str(python.absolute()))
        self.assertEqual(arguments[0], str(python.absolute()))
        self.assertNotIn("MCP_OAUTH_PASSWORD", child_environment)

    def test_tunnel_uses_direct_quic_for_workers_vpc(self):
        module = load_script("install_cloudflare_tunnel")
        self.assertEqual(module.TUNNEL_PROTOCOL, "quic")
        self.assertEqual(
            module.DIRECT_DNS_RESOLVERS,
            ("223.5.5.5:53", "114.114.114.114:53"),
        )


if __name__ == "__main__":
    unittest.main()
