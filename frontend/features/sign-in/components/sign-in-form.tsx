"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { useRequestMagicLink } from "../api/use-request-magic-link";
import { signInEmailSchema, type SignInEmailInput } from "../types";

export function SignInForm() {
  const [submittedEmail, setSubmittedEmail] = useState<string | null>(null);
  const { mutate, isPending, error } = useRequestMagicLink();

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<SignInEmailInput>({
    resolver: zodResolver(signInEmailSchema),
  });

  const onSubmit = handleSubmit(({ email }) => {
    mutate(email, { onSuccess: () => setSubmittedEmail(email) });
  });

  if (submittedEmail) {
    return (
      <div role="status" className="text-center">
        <h2 className="text-lg font-semibold text-zinc-950 dark:text-zinc-50">
          Check your email
        </h2>
        <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
          If {submittedEmail} has an account, we&rsquo;ve sent a sign-in link to it.
          The link expires in 15 minutes.
        </p>
      </div>
    );
  }

  return (
    <form onSubmit={onSubmit} className="flex w-full flex-col gap-4" noValidate>
      <div className="flex flex-col gap-1.5">
        <label htmlFor="email" className="text-sm font-medium text-zinc-950 dark:text-zinc-50">
          Work email
        </label>
        <input
          id="email"
          type="email"
          autoComplete="email"
          placeholder="you@company.com"
          aria-invalid={errors.email ? "true" : "false"}
          aria-describedby={errors.email ? "email-error" : undefined}
          className="rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-950 dark:border-zinc-700 dark:bg-black dark:text-zinc-50"
          {...register("email")}
        />
        {errors.email && (
          <p id="email-error" role="alert" className="text-sm text-red-600">
            {errors.email.message}
          </p>
        )}
      </div>

      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error.message}
        </p>
      )}

      <button
        type="submit"
        disabled={isPending}
        className="rounded-full bg-foreground px-5 py-2.5 text-sm font-medium text-background transition-colors hover:bg-[#383838] disabled:opacity-50 dark:hover:bg-[#ccc]"
      >
        {isPending ? "Sending…" : "Send Magic Link"}
      </button>
    </form>
  );
}
