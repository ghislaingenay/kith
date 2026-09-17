import { z } from "zod";

const envSchema = z.object({
  // Defaults to the local backend so `pnpm build`/`pnpm dev` work without
  // extra setup outside docker-compose (which sets this explicitly, see
  // infra/docker-compose.yml); staging/production must still override it.
  NEXT_PUBLIC_API_URL: z.string().url().default("http://localhost:8000/api/v1"),
});

export const env = envSchema.parse({
  NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
});
