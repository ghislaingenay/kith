---
status: deferred
date: 2026-10-25
---

# Cloudflare in front; the VPS accepts web traffic only from Cloudflare

Deferred: Kith launches with no CDN or WAF in front of the VPS. Pre-launch there is no attack to stop, and the one concrete abuse risk, a bot requesting Magic Links for many different emails, is closed in the app with a per-IP rate limit. Even a DNS-only move to Cloudflare was dropped: sign-in is passwordless, so a Resend SPF/DKIM record lost in the move would lock every User out, and a switch-on procedure written now would be stale by the time it is used. Revisit just before promoting the site publicly, or at the first sign of abuse, and do it fully in one go.

When revisited, the design worked out on 2026-10-25 is: Cloudflare Free with the proxy on for the apex and `www`, the VPS and Hostinger firewalls allowing 80/443 only from Cloudflare's published IP ranges (otherwise anyone with the server IP skips Cloudflare), and Caddy serving a Cloudflare Origin CA certificate with SSL mode Full (strict), since Let's Encrypt can no longer reach it directly.

## Considered options

- **Cloudflare Tunnel.** Closes 80/443 completely and needs no IP allowlist, but adds a `cloudflared` service and secret, changes Caddy more, and ties the deploy harder to Cloudflare.
- **Pro plan.** Not needed for prevention; upgrading later changes no app code.
- **DNS on Cloudflare now, proxy off.** Rejected for the reasons above.
- **AWS CloudFront in front of S3.** Rejected outright: S3 objects are served through short-lived presigned URLs, so a CDN adds AWS setup and a signing key for almost no gain.

## Consequences

- The app's per-IP limit relies on Caddy being the only hop: Caddy trusts no upstream and sets `X-Forwarded-For` to the real peer. Any proxy added in front of Caddy must, in the same change, add it to `trusted_proxies` and pass the real client IP upstream, or every visitor shares the proxy's IP and its rate limit.
- When proxied: Bot Fight Mode stays off (on Free it cannot be skipped per path and may challenge `/api` calls, Ask streams and the Sentry uptime check); the Origin CA certificate is not trusted by browsers, so records must stay proxied; Cloudflare gives up after 125 s with no response from the origin, which Ask streams are well inside.
