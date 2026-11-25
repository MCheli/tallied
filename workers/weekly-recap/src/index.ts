/**
 * Cloudflare Worker that emails the Tallied weekly recap every Monday.
 *
 * Tallied renders the email (GET /api/v1/recap/weekly/email, read-only API key); this worker only
 * fetches it and hands it to Cloudflare Email Routing. Setup is in docs/DEPLOYING.md.
 */
import { EmailMessage } from "cloudflare:email";

export interface Env {
  MAILER: SendEmail;
  TALLIED_API_URL: string;
  TALLIED_API_KEY: string;
  RECAP_FROM: string;
  RECAP_TO: string;
  TRIGGER_TOKEN?: string;
}

interface RecapEmail {
  subject: string;
  html: string;
  text: string;
  week_start: string;
  chart_png?: string | null; // base64 PNG, referenced from the HTML as cid:<chart_cid>
  chart_cid?: string | null;
}

/** RFC 2047 encoded-word for a subject that may contain non-ASCII (en dash, minus sign). */
function encodeHeader(value: string): string {
  return /^[\x20-\x7e]*$/.test(value) ? value : `=?UTF-8?B?${b64(value, false)}?=`;
}

/** Base64 of UTF-8; body parts are wrapped at 76 characters, a header's encoded word is not. */
function b64(value: string, wrap = true): string {
  const bytes = new TextEncoder().encode(value);
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  const out = btoa(bin);
  return wrap ? out.replace(/.{76}/g, "$&\r\n") : out;
}

export function buildMime(mail: RecapEmail, from: string, to: string, now = new Date()): string {
  const alt = `alt-${crypto.randomUUID()}`;
  const domain = from.split("@")[1];
  const alternative = [
    `--${alt}`,
    "Content-Type: text/plain; charset=UTF-8",
    "Content-Transfer-Encoding: base64",
    "",
    b64(mail.text),
    `--${alt}`,
    "Content-Type: text/html; charset=UTF-8",
    "Content-Transfer-Encoding: base64",
    "",
    b64(mail.html),
    `--${alt}--`,
  ];
  let body: string[];
  if (mail.chart_png && mail.chart_cid) {
    // multipart/related keeps the chart inline (shown where the HTML's cid: image is), not as an attachment.
    const rel = `rel-${crypto.randomUUID()}`;
    body = [
      `Content-Type: multipart/related; boundary="${rel}"`,
      "",
      `--${rel}`,
      `Content-Type: multipart/alternative; boundary="${alt}"`,
      "",
      ...alternative,
      `--${rel}`,
      'Content-Type: image/png; name="spending.png"',
      "Content-Transfer-Encoding: base64",
      `Content-ID: <${mail.chart_cid}>`,
      'Content-Disposition: inline; filename="spending.png"',
      "",
      mail.chart_png.replace(/.{76}/g, "$&\r\n"),
      `--${rel}--`,
    ];
  } else {
    body = [`Content-Type: multipart/alternative; boundary="${alt}"`, "", ...alternative];
  }
  return [
    `From: Tallied <${from}>`,
    `To: ${to}`,
    `Subject: ${encodeHeader(mail.subject)}`,
    `Date: ${now.toUTCString()}`,
    `Message-ID: <recap-${mail.week_start}-${crypto.randomUUID()}@${domain}>`,
    "MIME-Version: 1.0",
    ...body,
    "",
  ].join("\r\n");
}

async function sendRecap(env: Env): Promise<string> {
  const res = await fetch(`${env.TALLIED_API_URL}/api/v1/recap/weekly/email`, {
    headers: { "X-API-Key": env.TALLIED_API_KEY },
  });
  if (!res.ok) throw new Error(`Tallied answered ${res.status}: ${(await res.text()).slice(0, 200)}`);
  const mail = (await res.json()) as RecapEmail;
  await env.MAILER.send(new EmailMessage(env.RECAP_FROM, env.RECAP_TO, buildMime(mail, env.RECAP_FROM, env.RECAP_TO)));
  return mail.subject;
}

// Constant-time comparison: hash both sides so the lengths match, then compare every byte.
async function sameSecret(a: string, b: string): Promise<boolean> {
  const enc = new TextEncoder();
  const [x, y] = await Promise.all([a, b].map((v) => crypto.subtle.digest("SHA-256", enc.encode(v))));
  const xa = new Uint8Array(x);
  const ya = new Uint8Array(y);
  let diff = 0;
  for (let i = 0; i < xa.length; i++) diff |= xa[i] ^ ya[i];
  return diff === 0;
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    // A thrown error marks the cron run failed in the Cloudflare dashboard; nothing is swallowed.
    console.log(`sent: ${await sendRecap(env)}`);
  },

  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    // Prefer the Authorization header: a query-string token ends up in logs. ?token= still works.
    const bearer = request.headers.get("Authorization")?.replace(/^Bearer\s+/i, "");
    const presented = bearer || url.searchParams.get("token") || "";
    if (request.method !== "POST" || url.pathname !== "/send" || !env.TRIGGER_TOKEN || !(await sameSecret(presented, env.TRIGGER_TOKEN))) {
      return new Response("Not found", { status: 404 });
    }
    try {
      return new Response(`sent: ${await sendRecap(env)}\n`);
    } catch (err) {
      return new Response(`failed: ${err instanceof Error ? err.message : String(err)}\n`, { status: 502 });
    }
  },
};
