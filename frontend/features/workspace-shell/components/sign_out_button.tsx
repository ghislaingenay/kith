"use client";

import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { useSignOut } from "../api/use_sign_out";

export function SignOutButton() {
  const router = useRouter();
  const { mutate, isPending } = useSignOut();

  // A failed sign-out has no place on screen, so it gets a toast in fixed
  // words; the backend's message is never shown.
  const signOut = () =>
    mutate(undefined, {
      onSuccess: () => router.push("/sign-in"),
      onError: () => toast.error(SIGN_OUT_FAILED),
    });

  return (
    <button
      type="button"
      disabled={isPending}
      onClick={signOut}
      className="rounded-md px-3 py-2 text-left text-sm text-sidebar-foreground/80 transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground disabled:opacity-50"
    >
      {isPending ? "Signing out…" : "Sign out"}
    </button>
  );
}

const SIGN_OUT_FAILED = "We couldn't sign you out. Please try again.";
