import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CloudflareWorkerTests(unittest.TestCase):
    def test_worker_is_transport_only_and_forwards_to_same_local_mcp(self):
        source = (ROOT / "deploy" / "cloudflare" / "worker.js").read_text()
        self.assertIn('const ORIGIN_URL = "http://127.0.0.1:3462"', source)
        self.assertIn("env.NETEASE_MCP_VPC.fetch(forwarded)", source)
        self.assertNotIn("NETEASE_COOKIE", source)
        self.assertNotIn("osascript", source)

    def test_worker_binding_targets_the_dedicated_tunnel(self):
        config = json.loads(
            (ROOT / "deploy" / "cloudflare" / "wrangler.example.jsonc").read_text()
        )
        self.assertTrue(config["workers_dev"])
        self.assertEqual(config["name"], "netease-music-mcp-edge")
        self.assertEqual(
            config["vpc_networks"],
            [
                {
                    "binding": "NETEASE_MCP_VPC",
                    "tunnel_id": "YOUR_TUNNEL_ID",
                    "remote": True,
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
