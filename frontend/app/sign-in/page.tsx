import { SignInForm } from "@/features/sign-in";

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

  return (
    <div className="flex flex-1 flex-col items-center justify-center bg-background px-4 py-16">
      <div className="w-full max-w-sm rounded-lg border bg-card p-8">
        <h1 className="text-xl font-semibold text-foreground">
          Sign in to Kith
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Enter your work email and we&rsquo;ll send you a link to sign in.
        </p>
        <div className="mt-6">
          <SignInForm initialError={linkError} />
        </div>
      </div>
      <p className="mt-6 max-w-sm text-center text-xs text-muted-foreground">
        By continuing, you agree to our Terms of Service and Privacy Policy.
      </p>
    </div>
  );
}
