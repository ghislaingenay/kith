import { ApiError } from "@/lib/api_client";

/** The reason to show for a Document the API would not delete. */
export function describeDeleteFailure(error: unknown): string {
  if (error instanceof ApiError && error.status === 403) {
    return "You do not have permission to delete this document.";
  }
  if (error instanceof ApiError && error.status === 404) {
    return "It no longer exists.";
  }
  return error instanceof Error
    ? error.message
    : "Something went wrong. Please try again.";
}
