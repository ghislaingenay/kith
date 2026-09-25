import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test/render_with_providers";

import { WorkspaceShell } from "./workspace_shell";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

const EMAIL = "jane@example.com";

function renderShell(profile: { name: string | null; avatar_url: string | null }) {
  return renderWithProviders(
    <WorkspaceShell
      tenantName="Acme"
      tenantSlug="acme"
      profile={{ email: EMAIL, ...profile }}
    >
      <p>page content</p>
    </WorkspaceShell>,
  );
}

describe("WorkspaceShell", () => {
  it("shows the Tenant name as plain text, not a switcher", () => {
    renderShell({ name: "Jane", avatar_url: null });

    expect(screen.getByText("Acme")).toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Acme" })).not.toBeInTheDocument();
  });

  it("links to Uploads within the workspace", () => {
    renderShell({ name: "Jane", avatar_url: null });

    expect(screen.getByRole("link", { name: "Uploads" })).toHaveAttribute(
      "href",
      "/w/acme/uploads",
    );
  });

  it("links to Settings within the workspace", () => {
    renderShell({ name: "Jane", avatar_url: null });

    expect(screen.getByRole("link", { name: "Settings" })).toHaveAttribute(
      "href",
      "/w/acme/settings",
    );
  });

  it("shows the person's name, and offers sign-out", () => {
    renderShell({ name: "Jane", avatar_url: null });

    expect(screen.getByText("Jane")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign out" })).toBeInTheDocument();
  });

  it("falls back to the email when no name is set", () => {
    renderShell({ name: null, avatar_url: null });

    expect(screen.getByText(EMAIL)).toBeInTheDocument();
  });

  it("renders the page inside the shell", () => {
    renderShell({ name: "Jane", avatar_url: null });

    expect(screen.getByRole("main")).toHaveTextContent("page content");
  });
});
