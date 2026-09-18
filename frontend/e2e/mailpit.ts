const MAILPIT_URL = process.env.MAILPIT_URL ?? "http://localhost:8025";

interface MailpitSearchResult {
  messages: { ID: string }[];
}

interface MailpitMessage {
  Text: string;
}

/** Polls Mailpit's REST API for the most recent email sent to `email` and
 * pulls the magic-link URL out of its plaintext body (see
 * `auth/service.py`'s `link = f"{verify_url}?token={token}&email={...}"`).
 * The compose stack's Mailpit ships with no auth needed locally, so this is
 * the same "check your email" step a real user would do by hand. */
export async function findMagicLinkFor(
  email: string,
  { timeoutMs = 10_000, pollIntervalMs = 500 }: { timeoutMs?: number; pollIntervalMs?: number } = {},
): Promise<string> {
  const deadline = Date.now() + timeoutMs;

  while (Date.now() < deadline) {
    const searchResponse = await fetch(
      `${MAILPIT_URL}/api/v1/search?query=${encodeURIComponent(`to:${email}`)}`,
    );
    const { messages }: MailpitSearchResult = await searchResponse.json();

    if (messages.length > 0) {
      const messageResponse = await fetch(`${MAILPIT_URL}/api/v1/message/${messages[0].ID}`);
      const message: MailpitMessage = await messageResponse.json();
      const match = message.Text.match(/https?:\/\/\S+\/verify\?token=\S+/);
      if (match) {
        return match[0];
      }
    }

    await new Promise((resolve) => setTimeout(resolve, pollIntervalMs));
  }

  throw new Error(`Timed out waiting for a magic-link email to ${email}`);
}
