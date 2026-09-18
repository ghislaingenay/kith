import { env } from "@/config/env";

/** A non-2xx response from the API, carrying the backend's `{ error,
 * message }` body (see e.g. `tenants/exception_handlers.py`) so callers can
 * branch on `status` instead of re-parsing the response themselves. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

type ApiFetchInit = Omit<RequestInit, "body"> & { body?: unknown };

/** Thin fetch wrapper for the FastAPI backend: resolves the path against
 * `NEXT_PUBLIC_API_URL`, JSON-encodes `body`, and turns a non-2xx response
 * into an `ApiError`. Works from both Server Components/Route Handlers
 * (pass a `cookie` header explicitly, per coding-standards §4.2) and Client
 * Components (pass `credentials: "include"`). */
export async function apiFetch<T = unknown>(
  path: string,
  { body, headers, ...init }: ApiFetchInit = {},
): Promise<T> {
  const response = await fetch(`${env.NEXT_PUBLIC_API_URL}${path}`, {
    ...init,
    headers: {
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      ...headers,
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (!response.ok) {
    throw new ApiError(response.status, await extractErrorMessage(response));
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

async function extractErrorMessage(response: Response): Promise<string> {
  try {
    const data: unknown = await response.json();
    if (data && typeof data === "object" && "message" in data) {
      const { message } = data as { message: unknown };
      if (typeof message === "string") {
        return message;
      }
    }
  } catch {
    // Body wasn't JSON (e.g. a 5xx from infra in front of the API) — fall
    // through to the generic message below.
  }
  return "Something went wrong. Please try again.";
}
