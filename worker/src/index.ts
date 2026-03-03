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

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Handle CORS preflight
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: CORS_HEADERS });
    }

    if (request.method !== "POST") {
      return Response.json({ error: "Method not allowed" }, { status: 405, headers: CORS_HEADERS });
    }

    // Auth check
    const auth = request.headers.get("Authorization");
    if (!auth || auth !== `Bearer ${env.FEEDCAST_TOKEN}`) {
      return Response.json({ error: "Unauthorized" }, { status: 401, headers: CORS_HEADERS });
    }

    // Rate limit
    if (isRateLimited()) {
      return Response.json({ error: "Rate limit exceeded (20/hour)" }, { status: 429, headers: CORS_HEADERS });
    }

    // Parse body
    let body: { url?: string; mode?: string };
    try {
      body = await request.json();
    } catch {
      return Response.json({ error: "Invalid JSON" }, { status: 400, headers: CORS_HEADERS });
    }

    const { url, mode = "auto" } = body;

    // Validate URL
    if (!url || typeof url !== "string") {
      return Response.json({ error: "Missing 'url' field" }, { status: 400, headers: CORS_HEADERS });
    }
    try {
      const parsed = new URL(url);
      if (!["http:", "https:"].includes(parsed.protocol)) {
        throw new Error("Invalid protocol");
      }
    } catch {
      return Response.json({ error: "Invalid URL (must be http/https)" }, { status: 400, headers: CORS_HEADERS });
    }

    // Validate mode
    const validModes = ["auto", "summarize", "verbatim"];
    if (!validModes.includes(mode)) {
      return Response.json({ error: `Invalid mode. Must be one of: ${validModes.join(", ")}` }, { status: 400, headers: CORS_HEADERS });
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
      return Response.json(
        { error: "Failed to trigger workflow", detail: text },
        { status: 502, headers: CORS_HEADERS },
      );
    }

    requestLog.push(Date.now());

    return Response.json(
      { status: "queued", url, mode },
      { status: 202, headers: CORS_HEADERS },
    );
  },
};
