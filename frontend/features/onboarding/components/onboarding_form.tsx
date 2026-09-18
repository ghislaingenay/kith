"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
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
      onSuccess: (tenant) => router.push(workspacePath(tenant.tenant_slug)),
    });
  });

  return (
    <form onSubmit={onSubmit} className="flex w-full flex-col gap-4" noValidate>
      <div className="flex flex-col gap-1.5">
        <label
          htmlFor="name"
          className="text-sm font-medium text-zinc-950 dark:text-zinc-50"
        >
          Workspace name
        </label>
        <input
          id="name"
          type="text"
          autoComplete="organization"
          aria-invalid={errors.name ? "true" : "false"}
          aria-describedby={errors.name ? "name-error" : undefined}
          className="rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-950 dark:border-zinc-700 dark:bg-black dark:text-zinc-50"
          {...register("name")}
        />
        {errors.name && (
          <p id="name-error" role="alert" className="text-sm text-red-600">
            {errors.name.message}
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
        {isPending ? "Creating…" : "Create workspace"}
      </button>
    </form>
  );
}
