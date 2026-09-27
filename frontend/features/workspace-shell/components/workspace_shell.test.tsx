import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test/render_with_providers";

import { WorkspaceShell } from "./workspace_shell";

const { usePathnameMock } = vi.hoisted(() => ({
  usePathnameMock: vi.fn(() => "/w/acme/uploads"),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  usePathname: usePathnameMock,
}));

afterEach(() => {
  usePathnameMock.mockReturnValue("/w/acme/uploads");
});

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

  it("links to Home within the workspace", () => {
    renderShell({ name: "Jane", avatar_url: null });

    expect(screen.getByRole("link", { name: "Home" })).toHaveAttribute(
      "href",
      "/w/acme",
    );
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

  it("marks Home as the active section on the workspace root, not Uploads or Settings", () => {
    usePathnameMock.mockReturnValue("/w/acme");
    renderShell({ name: "Jane", avatar_url: null });

    expect(screen.getByRole("link", { name: "Home" })).toHaveAttribute(
      "data-active",
      "true",
    );
    expect(screen.getByRole("link", { name: "Uploads" })).toHaveAttribute(
      "data-active",
      "false",
    );
    expect(screen.getByRole("link", { name: "Settings" })).toHaveAttribute(
      "data-active",
      "false",
    );
  });

  it("marks Uploads as the active section while browsing uploads, not Home", () => {
    usePathnameMock.mockReturnValue("/w/acme/uploads");
    renderShell({ name: "Jane", avatar_url: null });

    expect(screen.getByRole("link", { name: "Uploads" })).toHaveAttribute(
      "data-active",
      "true",
    );
    expect(screen.getByRole("link", { name: "Home" })).toHaveAttribute(
      "data-active",
      "false",
    );
  });

  it("marks Settings as the active section while browsing settings, not Home", () => {
    usePathnameMock.mockReturnValue("/w/acme/settings");
    renderShell({ name: "Jane", avatar_url: null });

    expect(screen.getByRole("link", { name: "Settings" })).toHaveAttribute(
      "data-active",
      "true",
    );
    expect(screen.getByRole("link", { name: "Home" })).toHaveAttribute(
      "data-active",
      "false",
    );
  });
});
