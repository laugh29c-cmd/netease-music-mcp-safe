# Connect Codex after deployment

The Codex app, Codex CLI, and Codex IDE extension share their user-level MCP configuration. For the
single Mac-hosted runtime installed by `deploy/macos/install_local_runtime.py`, add a Streamable
HTTP server with:

- URL: `http://127.0.0.1:3462/mcp`
- HTTP headers helper: `~/.codex/mcp-helpers/netease_music_header.py`

The helper is installed mode `0700`, reads the existing mode-`0600` runtime config, and returns the
bearer header only when Codex starts a request. Do not duplicate the literal token in Codex config.

Equivalent project-scoped configuration:

```toml
[mcp_servers.netease_music]
url = "http://127.0.0.1:3462/mcp"
http_headers_helper = "/Users/YOU/.codex/mcp-helpers/netease_music_header.py"
default_tools_approval_mode = "writes"
tool_timeout_sec = 30
```

Restart the client after saving, then use `/mcp` to confirm the server is connected.

The Codex frontend and shared Codex CLI read the same user-level registration. ChatGPT Work on the
web does not read local Codex configuration, so connect it separately as a private developer-mode
plugin to the runtime's public HTTPS ingress. The two ingress paths terminate at the same server
process and SQLite database. With `MCP_MAC_PLAYBACK_ENABLED=true`, both expose the same optional Mac
playback tools. With `MCP_MOBILE_PLAYBACK_ENABLED=true`, both also expose the same optional iPhone
tools. A separately persisted controller account in that same process joins or hosts NetEase's native
Listen Together room for the iPhone's different daily account; it is not a second MCP service. NetEase HTTPS
requests and the Cloudflare Tunnel use direct network paths that ignore proxy environment variables.

For specified playback, call `search_song` first and pass one returned numeric ID to
`play_song(song_id)`. The server constructs only the fixed NetEase Web desktop-play payload, Base64
encodes it into the `orpheus://` URL scheme, and targets the official Mac client. Its response distinguishes the requested ID from the best-effort
playing/paused state readback; it does not claim the current track ID was verified when the client
does not expose it.

## Connect ChatGPT Work on the web

Configure `MCP_PUBLIC_URL` and `MCP_OAUTH_PASSWORD` on the server first. Then in ChatGPT:

1. Open **Settings → Security and login** and enable **Developer mode**.
2. Open **Settings → Plugins**, select the plus button, and create a developer-mode app.
3. Enter the deployed public URL, for example
   `https://your-service.example.com/mcp`, and choose OAuth/discovered
   authentication. A `workers.dev` URL is sufficient; a user-owned domain is not required.
4. Complete the browser authorization page with `MCP_OAUTH_PASSWORD`.

If the server is later changed from read-only to write mode, refresh the app's tool definitions,
disconnect it, and reconnect it. Existing refresh tokens retain their original read-only scope and
must not be silently upgraded. The new authorization page will explicitly request write access.
Enabling Mac playback adds the separate `mac.playback` scope, so refresh and reconnect once after
that change as well. Enabling iPhone playback advertises `mobile.playback`; refresh and reconnect
once. Existing private ChatGPT Apps can retain their original default scope list after a tool
refresh. On a combined Mac+iPhone runtime, version 5.5.0 accepts an already granted
`mac.playback` scope as a compatibility playback scope for the iPhone tools. Read-only tokens and
mobile-only deployments still require explicit `mobile.playback`. On first use, run
`start_mobile_controller_qr_login` and scan with a NetEase account different from the daily account
on the iPhone, then call `check_mobile_controller_qr_login`. The preferred phone flow is to start
Listen Together on the iPhone's daily account, share its official invitation, and pass that URL to
`join_mobile_netease_player`; the controller account then joins the phone's active room before
sending commands. `start_mobile_netease_player` remains the controller-hosted compatibility path.
A same-account self-invite is rejected because it cannot produce a separately connected participant.

After deploying session management, reconnect once so the app can receive the `netease.session`
scope. Run `start_netease_qr_login`; its MCP result includes text with a direct NetEase HTTPS
`qr_url` plus a PNG image content block, so the client does not need to turn the text payload into
an image itself. Scan and confirm it in the NetEase App, then call `check_netease_qr_login` with the
returned `login_id`. The resulting Cookie is stored only on the server and is never returned to the
client.

Also refresh, disconnect, and reconnect after deploying new tools or changing their input schema;
otherwise ChatGPT may continue using a cached tool list from the previous deployment.

All write tools execute in one call after server-side validation. There is no `preview_operation`
tool and no public `preview_token` parameter. Old clients that still send a `preview_token` are
temporarily accepted; the server ignores the value and does not run the old approval flow.

Every write tool exposes an optional `idempotency_key`. Codex can generate one stable UUID or
other 8-100 character key for a single intended action and reuse it only when retrying that same
action. ChatGPT's JSON-RPC request ID is not guaranteed to remain stable across a semantic retry, so
the server cannot automatically deduplicate every client retry. Never reuse one key for a later
intentional operation.

Cover uploads use ChatGPT's top-level file parameter support; attach a PNG or JPEG instead of
providing an image URL. If the removed preview fields or other stale schemas still appear, refresh
the action definitions, disconnect and reconnect the app, and open a new chat if necessary.

Hosted Work cannot read a local helper or environment variable, so do not add a static
`Authorization` header to a plugin manifest. OAuth remains the Web Chat authentication boundary;
the bearer helper is only for local Codex clients.
