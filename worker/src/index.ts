export interface Env {
  FEEDCAST_TOKEN: string;
  GITHUB_PAT: string;
  GITHUB_REPO: string; // e.g. "tbuckworth/feedcast"
}

// Simple in-memory rate limiter (resets on worker restart)
const requestLog: number[] = [];
const RATE_LIMIT = 20;
const RATE_WINDOW_MS = 60 * 60 * 1000; // 1 hour

function isRateLimited(): boolean {
  const now = Date.now();
  // Remove old entries
  while (requestLog.length > 0 && requestLog[0] < now - RATE_WINDOW_MS) {
    requestLog.shift();
  }
  return requestLog.length >= RATE_LIMIT;
}

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, Authorization",
};

// Every refusal (4xx) is logged here, so Workers Logs shows why a request
// was turned away, not just its status.
function reply(status: number, body: object): Response {
  if (status >= 400 && status < 500) console.warn(`${status} ${JSON.stringify(body)}`);
  return Response.json(body, { status, headers: CORS_HEADERS });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Handle CORS preflight
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: CORS_HEADERS });
    }

    if (request.method !== "POST") {
      return reply(405, { error: "Method not allowed" });
    }

    // Auth check
    const auth = request.headers.get("Authorization");
    if (!auth || auth !== `Bearer ${env.FEEDCAST_TOKEN}`) {
      console.warn(`Unauthorized: ${auth ? "wrong token" : "no Authorization header"}`);
      return reply(401, { error: "Unauthorized" });
    }

    // Rate limit
    if (isRateLimited()) {
      return reply(429, {
        error: `Rate limit exceeded (${RATE_LIMIT} per ${RATE_WINDOW_MS / 60_000} minutes)`,
      });
    }

    // Parse body
    let body: { url?: string; mode?: string };
    try {
      body = await request.json();
    } catch {
      return reply(400, { error: "Invalid JSON" });
    }

    const { url, mode = "auto" } = body;

    // Validate URL
    if (!url || typeof url !== "string") {
      return reply(400, { error: "Missing 'url' field" });
    }
    try {
      const parsed = new URL(url);
      if (!["http:", "https:"].includes(parsed.protocol)) {
        throw new Error("Invalid protocol");
      }
    } catch {
      return reply(400, { error: "Invalid URL (must be http/https)" });
    }

    // Validate mode
    const validModes = ["auto", "summarize", "verbatim"];
    if (!validModes.includes(mode)) {
      return reply(400, { error: `Invalid mode. Must be one of: ${validModes.join(", ")}` });
    }

    // Trigger GitHub Actions workflow_dispatch
    const resp = await fetch(
      `https://api.github.com/repos/${env.GITHUB_REPO}/actions/workflows/update-feed.yml/dispatches`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${env.GITHUB_PAT}`,
          Accept: "application/vnd.github.v3+json",
          "User-Agent": "feedcast-worker",
        },
        body: JSON.stringify({
          ref: "main",
          inputs: { inject_url: url, inject_mode: mode },
        }),
      },
    );

    if (!resp.ok) {
      const text = await resp.text();
      console.error(`workflow_dispatch for ${url} failed: GitHub ${resp.status} ${text}`);
      return reply(502, { error: `Failed to trigger workflow (GitHub ${resp.status})`, detail: text });
    }

    requestLog.push(Date.now());
    console.log(`Queued ${url} (mode ${mode})`);

    return reply(202, { status: "queued", url, mode });
  },
};
