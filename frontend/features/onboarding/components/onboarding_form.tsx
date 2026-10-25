"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { workspacePath } from "@/lib/session_identity";

import { useCreateTenant } from "../api/use_create_tenant";
import { workspaceNameSchema, type WorkspaceNameInput } from "../types";

export function OnboardingForm({
  suggestedWorkspaceName,
}: {
  readonly suggestedWorkspaceName: string;
}) {
  const router = useRouter();
  const { mutate, isPending, error } = useCreateTenant();
  // `isPending` flips back to false as soon as the mutation resolves, right
  // when `onSuccess` fires — this covers the gap between then and the
  // workspace page actually rendering, so the button doesn't flash back to
  // "Create workspace" while the router navigates.
  const [isRedirecting, setIsRedirecting] = useState(false);
  const isBusy = isPending || isRedirecting;

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<WorkspaceNameInput>({
    resolver: zodResolver(workspaceNameSchema),
    defaultValues: { name: suggestedWorkspaceName },
  });

  const onSubmit = handleSubmit(({ name }) => {
    mutate(name, {
      onSuccess: (tenant) => {
        setIsRedirecting(true);
        router.push(workspacePath(tenant.tenant_slug));
      },
    });
  });

  return (
    <form onSubmit={onSubmit} className="flex w-full flex-col gap-4" noValidate>
      <div className="flex flex-col gap-1.5">
        <label
          htmlFor="name"
          className="text-sm font-medium text-foreground"
        >
          Workspace name
        </label>
        <input
          id="name"
          type="text"
          autoComplete="organization"
          aria-invalid={errors.name ? "true" : "false"}
          aria-describedby={errors.name ? "name-error" : undefined}
          className="rounded-md border border-input bg-card px-3 py-2 text-sm text-foreground"
          {...register("name")}
        />
        {errors.name && (
          <p id="name-error" role="alert" className="text-sm text-destructive">
            {errors.name.message}
          </p>
        )}
      </div>

      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error.message}
        </p>
      )}

      <button
        type="submit"
        disabled={isBusy}
        className="rounded-md bg-primary px-5 py-2.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/85 disabled:opacity-50"
      >
        {isBusy ? "Creating…" : "Create workspace"}
      </button>
    </form>
  );
}
