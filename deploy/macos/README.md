# macOS local runtime

The production layout keeps one MCP process on the Mac so the same server owns NetEase session
state and the optional playback tools. The LaunchAgent binds only to `127.0.0.1`; an independently
restartable HTTPS tunnel may publish that loopback endpoint.

The installer enables both the Mac-local tools and the native iPhone Listen Together tools inside
that one process. iPhone control uses a separately persisted controller account to join or host a room
with the iPhone's different daily account. Both sessions remain in the same SQLite database and
runtime; the preferred path lets the iPhone host and passes its official invitation to
`join_mobile_netease_player`, and no phone companion service is installed.

Install or refresh the local runtime:

```bash
python3 deploy/macos/install_local_runtime.py
```

Re-run with `--public-url https://music.example.com` after assigning the tunnel hostname. The
installer preserves the existing access token, OAuth password, SQLite data, and logs. It copies the
four dependencies from the source virtual environment that passed the test suite, rather than
depending on a package-index request during installation. It writes secrets only to a mode-`0600`
JSON file outside Git, strips all proxy variables before server startup, and keeps the runtime in
read-only mode by default.

The installer also writes `~/.codex/mcp-helpers/netease_music_header.py`. Codex frontend and CLI can
share a loopback MCP entry with `http_headers_helper` set to that no-space executable path. The helper
reads the existing mode-`0600` runtime config and emits only the authorization header at process
runtime, so the access token is not duplicated in `~/.codex/config.toml` and local Codex traffic
never depends on the public Worker or a system proxy.

The installed LaunchAgent is `com.example.netease-music-mcp-safe`. A Cloudflare tunnel uses a
separate label and token so stopping either transport does not stop the MCP process.

After creating a separate remotely managed tunnel and assigning its public hostname to
`http://127.0.0.1:3462`, copy the Dashboard's tunnel install command, then run:

```bash
python3 deploy/macos/install_cloudflare_tunnel.py \
  --public-url https://YOUR-HOSTNAME \
  --token-from-clipboard
```

The transport LaunchAgent is `com.example.netease-music-mcp-safe-tunnel`. It strips proxy environment
variables, uses direct QUIC required by Workers VPC, pins two directly reachable DNS resolvers,
and keeps its token in a mode-`0600` file outside Git. The direct precheck verifies DNS, UDP/QUIC,
TCP/HTTP2, and Cloudflare API reachability. It remains a transport for the same MCP, not a second
API or MCP service.
