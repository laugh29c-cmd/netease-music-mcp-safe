const ORIGIN_URL = "http://127.0.0.1:3462";

export default {
  async fetch(request, env) {
    const incoming = new URL(request.url);
    const upstream = new URL(incoming.pathname + incoming.search, ORIGIN_URL);
    const forwarded = new Request(upstream, request);
    return env.NETEASE_MCP_VPC.fetch(forwarded);
  },
};
