/**
 * Cloudflare Email Worker — receives forwarded receipts and sends them to the Tallied API.
 *
 * Setup:
 * 1. Deploy: `wrangler deploy`
 * 2. Set secret: `wrangler secret put EMAIL_WEBHOOK_SECRET`
 * 3. In Cloudflare dashboard → Email Routing → Email Workers, route receipts@yourdomain to this worker
 */

export interface Env {
  TALLIED_API_URL: string;
  EMAIL_WEBHOOK_SECRET: string;
}

export default {
  async email(message: ForwardableEmailMessage, env: Env): Promise<void> {
    const to = message.to;
    const fromEmail = message.from;
    const subject = message.headers.get("subject") || "(no subject)";

    // Read the raw email body
    const rawBody = await new Response(message.raw).text();

    // Extract forwarded-from email from common forwarding headers or body patterns
    const forwardedBy = extractForwarder(message.headers, rawBody, fromEmail);

    // Extract text content from the raw email
    const textContent = extractTextFromRaw(rawBody);

    const payload = {
      from_email: fromEmail,
      forwarded_by: forwardedBy,
      to: to,
      subject: subject,
      text: textContent,
      html: null,
    };

    const response = await fetch(`${env.TALLIED_API_URL}/api/v1/email-import/inbound`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Email-Webhook-Secret": env.EMAIL_WEBHOOK_SECRET,
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const body = await response.text();
      console.error(`Tallied API error ${response.status}: ${body}`);
    }
  },
};

function extractForwarder(
  headers: Headers,
  body: string,
  fallback: string
): string {
  // Check common forwarding headers
  const xForwardedFor = headers.get("x-forwarded-for");
  if (xForwardedFor) return xForwardedFor;

  const xOriginalFrom = headers.get("x-original-from");
  if (xOriginalFrom) return xOriginalFrom;

  // Look for "From: user@example.com" in forwarded body
  const fromMatch = body.match(
    /(?:^|\n)From:\s*(?:.*<)?([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})>?/m
  );
  if (fromMatch) return fromMatch[1];

  // The sender IS the forwarder in most cases
  return fallback;
}

function extractTextFromRaw(raw: string): string {
  // For multipart emails, try to find the text/plain part
  const boundaryMatch = raw.match(/boundary="?([^"\s;]+)"?/);
  if (boundaryMatch) {
    const boundary = boundaryMatch[1];
    const parts = raw.split(`--${boundary}`);
    for (const part of parts) {
      if (part.includes("Content-Type: text/plain")) {
        // Extract content after the double newline (header/body separator)
        const bodyStart = part.indexOf("\r\n\r\n") || part.indexOf("\n\n");
        if (bodyStart > -1) {
          return part.slice(bodyStart + 4).trim();
        }
      }
    }
  }

  // Fallback: strip headers and return everything after first blank line
  const bodyStart = raw.indexOf("\r\n\r\n") || raw.indexOf("\n\n");
  if (bodyStart > -1) {
    return raw.slice(bodyStart + 4).trim();
  }
  return raw;
}
