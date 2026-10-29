# Cloudflare public transport

This Worker is a transport-only HTTPS edge for the same Mac-hosted MCP process. It contains no
music, session, or playback logic. `NETEASE_MCP_VPC` binds the Worker to a dedicated Cloudflare
Tunnel and forwards every method, path, query, header, and body to `http://127.0.0.1:3462` on the
Mac.

A `workers.dev` endpoint is sufficient; a user-owned domain is optional. Workers VPC requires the
Tunnel's QUIC transport, so the macOS LaunchAgent removes proxy variables and uses explicit direct
DNS resolvers before connecting.

1. Create a remotely managed Cloudflare Tunnel dedicated to this MCP and point it at
   `http://127.0.0.1:3462`.
2. Copy `wrangler.example.jsonc` to `wrangler.jsonc`.
3. Replace `YOUR_ACCOUNT_ID` and `YOUR_TUNNEL_ID` locally. `wrangler.jsonc` is gitignored because
   those values describe a private deployment.
4. Deploy from this directory with Wrangler.
5. Verify `/health`, OAuth metadata, and one authenticated MCP tool call through the public URL.

Wrangler needs these OAuth scopes:

- `account:read`
- `user:read`
- `workers_scripts:write`
- `connectivity:admin`

Keep the Tunnel token only in the mode-`0600` local file installed by
`deploy/macos/install_cloudflare_tunnel.py`. Do not commit it or place it in Wrangler configuration.
