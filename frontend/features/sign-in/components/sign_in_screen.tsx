import { StackedPages } from "@/components/line_drawings";

import { SignInForm } from "./sign-in-form";

/** The sign-in page: one column on a paper-to-green gradient, with no card.
 * The form, "Check your email" and link-error states all sit under the same
 * wordmark and drawing. */
export function SignInScreen({ linkError }: { readonly linkError: string | null }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center bg-linear-to-b from-background to-glow px-4 py-16">
      <div className="flex w-full max-w-sm flex-col items-center">
        <h1 className="font-heading text-5xl font-semibold tracking-tight text-foreground">
          Kith
        </h1>
        <StackedPages className="mt-8" />
        <div className="mt-8 w-full">
          <SignInForm initialError={linkError} />
        </div>
        <p className="mt-10 text-center text-xs text-muted-foreground">
          By continuing, you agree to our Terms of Service and Privacy Policy.
        </p>
      </div>
    </div>
  );
}
