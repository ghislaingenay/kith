# Production image: Next.js standalone output, run as the non-root `node`
# user. Development does not use this file (infra/docker-compose.yml runs
# `next dev` on a plain node image).

FROM node:22.22-alpine AS deps
WORKDIR /app
RUN corepack enable && corepack prepare pnpm@8.6.12 --activate
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

FROM deps AS build
# Baked into the browser bundle at build time, so they are build arguments,
# not runtime env. NEXT_PUBLIC_API_URL is the site's own origin in
# production: Caddy routes /api/* to the API.
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_ASK_SHOW_SOURCES=true
ARG NEXT_PUBLIC_ASK_CITATION_MARKERS=true
# Sentry (config/sentry.ts): an empty DSN turns it off. GIT_SHA is the commit
# the image is built from, so events carry the release.
ARG NEXT_PUBLIC_SENTRY_DSN=
ARG NEXT_PUBLIC_SENTRY_ENVIRONMENT=production
ARG NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE=0.1
ARG GIT_SHA
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_ASK_SHOW_SOURCES=$NEXT_PUBLIC_ASK_SHOW_SOURCES \
    NEXT_PUBLIC_ASK_CITATION_MARKERS=$NEXT_PUBLIC_ASK_CITATION_MARKERS \
    NEXT_PUBLIC_SENTRY_DSN=$NEXT_PUBLIC_SENTRY_DSN \
    NEXT_PUBLIC_SENTRY_ENVIRONMENT=$NEXT_PUBLIC_SENTRY_ENVIRONMENT \
    NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE=$NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE \
    NEXT_PUBLIC_SENTRY_RELEASE=$GIT_SHA \
    NEXT_TELEMETRY_DISABLED=1
RUN test -n "$NEXT_PUBLIC_API_URL" || { echo "NEXT_PUBLIC_API_URL build argument is required" >&2; exit 1; }
COPY . .
RUN pnpm run build

FROM node:22.22-alpine AS runtime
WORKDIR /app
# HOSTNAME: Docker sets it to the container id, and the standalone server
# binds to it, so it is reset to listen on every interface.
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000
COPY --from=build --chown=node:node /app/.next/standalone ./
COPY --from=build --chown=node:node /app/.next/static ./.next/static
COPY --from=build --chown=node:node /app/public ./public
USER node
EXPOSE 3000
# Node's own fetch, so the image needs no curl/wget. /health (app/health)
# answers without calling the API, so this checks the frontend alone, and
# Sentry never traces it.
HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=3 \
    CMD ["node", "-e", "fetch('http://localhost:3000/health').then((r) => process.exit(r.ok ? 0 : 1), () => process.exit(1))"]
CMD ["node", "server.js"]
