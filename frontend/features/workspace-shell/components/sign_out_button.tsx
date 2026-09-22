"use client";

import { useRouter } from "next/navigation";

import { useSignOut } from "../api/use_sign_out";

export function SignOutButton() {
  const router = useRouter();
  const { mutate, isPending, error } = useSignOut();

  return (
    <div className="flex flex-col gap-1">
      <button
        type="button"
        disabled={isPending}
        onClick={() => mutate(undefined, { onSuccess: () => router.push("/sign-in") })}
        className="rounded-md px-3 py-2 text-left text-sm text-zinc-700 transition-colors hover:bg-zinc-100 disabled:opacity-50 dark:text-zinc-300 dark:hover:bg-zinc-900"
      >
        {isPending ? "Signing out…" : "Sign out"}
      </button>
      {error && (
        <p role="alert" className="px-3 text-xs text-red-600">
          {error.message}
        </p>
      )}
    </div>
  );
}
