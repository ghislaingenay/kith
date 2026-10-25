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
        className="rounded-md px-3 py-2 text-left text-sm text-sidebar-foreground/80 transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground disabled:opacity-50"
      >
        {isPending ? "Signing out…" : "Sign out"}
      </button>
      {error && (
        <p role="alert" className="px-3 text-xs text-destructive">
          {error.message}
        </p>
      )}
    </div>
  );
}
