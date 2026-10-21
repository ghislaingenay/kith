import { z } from "zod";

// An on/off flag spelled "true" or "false", on unless set.
const flag = z
  .enum(["true", "false"])
  .default("true")
  .transform((value) => value === "true");

// An unset GitHub variable reaches the image build as an empty string, so
// empty means unset.
const unsetIfEmpty = (value: unknown) => (value === "" ? undefined : value);

const envSchema = z.object({
  // Exposed to the browser; used by Client Components.
  // Defaults to the local backend so `pnpm build`/`pnpm dev` work without
  // extra setup outside docker-compose (which sets this explicitly, see
  // infra/docker-compose.yml); staging/production must still override it.
  NEXT_PUBLIC_API_URL: z.string().url().default("http://localhost:8000"),
  // Exposed to the browser. Off hides an Answer's source cards and its `[n]`
  // markers; `NEXT_PUBLIC_ASK_CITATION_MARKERS` off hides only the markers.
  NEXT_PUBLIC_ASK_SHOW_SOURCES: flag,
  NEXT_PUBLIC_ASK_CITATION_MARKERS: flag,
  // Exposed to the browser, and read by the server too (config/sentry.ts).
  // Baked in at build time by frontend/Dockerfile. An empty DSN, or the
  // `local` environment, leaves Sentry off.
  NEXT_PUBLIC_SENTRY_DSN: z.preprocess(unsetIfEmpty, z.string().default("")),
  NEXT_PUBLIC_SENTRY_ENVIRONMENT: z.preprocess(
    unsetIfEmpty,
    z.string().default("local"),
  ),
  NEXT_PUBLIC_SENTRY_RELEASE: z.preprocess(unsetIfEmpty, z.string().optional()),
  NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE: z.preprocess(
    unsetIfEmpty,
    z.coerce.number().min(0).max(1).default(0.1),
  ),
  // Server-only; used by Server Components / Route Handlers (never sent to the browser).
  BACKEND_URL: z.string().url().default("http://localhost:8000"),
  // Server-only; browser-facing origin for building absolute redirect URLs.
  // `request.url`'s origin follows the dev server's `--hostname` (0.0.0.0
  // in docker-compose), not the Host header, so it can't be used directly.
  APP_URL: z.string().url().default("http://localhost:3000"),
});

// Each NEXT_PUBLIC_ variable is read by its full name so Next inlines it into
// the browser bundle.
export const env = envSchema.parse({
  NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
  NEXT_PUBLIC_ASK_SHOW_SOURCES: process.env.NEXT_PUBLIC_ASK_SHOW_SOURCES,
  NEXT_PUBLIC_ASK_CITATION_MARKERS: process.env.NEXT_PUBLIC_ASK_CITATION_MARKERS,
  NEXT_PUBLIC_SENTRY_DSN: process.env.NEXT_PUBLIC_SENTRY_DSN,
  NEXT_PUBLIC_SENTRY_ENVIRONMENT: process.env.NEXT_PUBLIC_SENTRY_ENVIRONMENT,
  NEXT_PUBLIC_SENTRY_RELEASE: process.env.NEXT_PUBLIC_SENTRY_RELEASE,
  NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE:
    process.env.NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE,
  BACKEND_URL: process.env.BACKEND_URL,
  APP_URL: process.env.APP_URL,
});
