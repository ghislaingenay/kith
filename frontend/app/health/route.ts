/** The container's health check (frontend/Dockerfile) calls this on
 * localhost; the public `/health` goes to the API (infra/Caddyfile). Its own
 * path keeps health checks out of Sentry's traces (config/sentry.ts). */
export function GET(): Response {
  return Response.json({ status: "ok" });
}
