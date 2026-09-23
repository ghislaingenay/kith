import { z } from "zod";

const envSchema = z.object({
  // Exposed to the browser; used by Client Components.
  // Defaults to the local backend so `pnpm build`/`pnpm dev` work without
  // extra setup outside docker-compose (which sets this explicitly, see
  // infra/docker-compose.yml); staging/production must still override it.
  NEXT_PUBLIC_API_URL: z.string().url().default("http://localhost:8000"),
  // Server-only; used by Server Components / Route Handlers (never sent to the browser).
  BACKEND_URL: z.string().url().default("http://localhost:8000"),
  // Server-only; browser-facing origin for building absolute redirect URLs.
  // `request.url`'s origin follows the dev server's `--hostname` (0.0.0.0
  // in docker-compose), not the Host header, so it can't be used directly.
  APP_URL: z.string().url().default("http://localhost:3000"),
});

export const env = envSchema.parse({
  NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
  BACKEND_URL: process.env.BACKEND_URL,
  APP_URL: process.env.APP_URL,
});
