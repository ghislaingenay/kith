import { SignInScreen } from "@/features/sign-in";

const LINK_ERROR_MESSAGES: Record<string, string> = {
  "invalid-link": "That sign-in link is invalid.",
  "expired-link": "That sign-in link has expired. Links are valid for 15 minutes.",
  "session-failed": "We couldn't sign you in. Please try again.",
};

export default async function SignInPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const { error } = await searchParams;
  const linkError = error
    ? (LINK_ERROR_MESSAGES[error] ?? "Something went wrong. Please try again.")
    : null;

  return <SignInScreen linkError={linkError} />;
}
