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
  const boundary = `recap-${crypto.randomUUID()}`;
  const domain = from.split("@")[1];
  return [
    `From: Tallied <${from}>`,
    `To: ${to}`,
    `Subject: ${encodeHeader(mail.subject)}`,
    `Date: ${now.toUTCString()}`,
    `Message-ID: <recap-${mail.week_start}-${crypto.randomUUID()}@${domain}>`,
    "MIME-Version: 1.0",
    `Content-Type: multipart/alternative; boundary="${boundary}"`,
    "",
    `--${boundary}`,
    "Content-Type: text/plain; charset=UTF-8",
    "Content-Transfer-Encoding: base64",
    "",
    b64(mail.text),
    `--${boundary}`,
    "Content-Type: text/html; charset=UTF-8",
    "Content-Transfer-Encoding: base64",
    "",
    b64(mail.html),
    `--${boundary}--`,
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

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    // A thrown error marks the cron run failed in the Cloudflare dashboard; nothing is swallowed.
    console.log(`sent: ${await sendRecap(env)}`);
  },

  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (request.method !== "POST" || url.pathname !== "/send" || !env.TRIGGER_TOKEN || url.searchParams.get("token") !== env.TRIGGER_TOKEN) {
      return new Response("Not found", { status: 404 });
    }
    try {
      return new Response(`sent: ${await sendRecap(env)}\n`);
    } catch (err) {
      return new Response(`failed: ${err instanceof Error ? err.message : String(err)}\n`, { status: 502 });
    }
  },
};
