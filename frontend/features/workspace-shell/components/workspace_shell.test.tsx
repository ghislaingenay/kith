import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TooltipProvider } from "@/components/ui/tooltip";
import { server } from "@/test/mocks/server";
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
const TENANT_ID = "6f1c2a3b-4d5e-4f60-8a7b-9c0d1e2f3a4b";
const BALANCE_URL = "http://localhost:8000/api/v1/credit-balance";
const TOOLTIP =
  "Each Ask uses credits for the text the AI reads and writes, about 4 for a typical Ask. 1 credit = 1,000 tokens. Search is free.";

beforeEach(() => {
  serveBalance({ credits: 142, tokens: 142_310, is_low: false, is_exhausted: false });
});

function serveBalance(balance: {
  credits: number;
  tokens: number;
  is_low: boolean;
  is_exhausted: boolean;
}) {
  const seen = { tenantIds: [] as (string | null)[] };
  server.use(
    http.get(BALANCE_URL, ({ request }) => {
      seen.tenantIds.push(request.headers.get("x-tenant-id"));
      return HttpResponse.json(balance);
    }),
  );
  return seen;
}

function renderShell(
  profile: { name: string | null; avatar_url: string | null },
  role: "owner" | "admin" | "member" | "viewer" = "member",
) {
  return renderWithProviders(
    <TooltipProvider>
      <WorkspaceShell
        tenantId={TENANT_ID}
        tenantName="Acme"
        tenantSlug="acme"
        role={role}
        profile={{ email: EMAIL, ...profile }}
      >
        <p>page content</p>
      </WorkspaceShell>
    </TooltipProvider>,
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

  describe("Credit Balance", () => {
    it("shows the Tenant's credits left, asked for with its Tenant header", async () => {
      const seen = serveBalance({
        credits: 142,
        tokens: 142_310,
        is_low: false,
        is_exhausted: false,
      });
      renderShell({ name: "Jane", avatar_url: null });

      const balance = await screen.findByText("142 credits left");
      expect(balance).toHaveAttribute("data-balance", "normal");
      expect(seen.tenantIds).toEqual([TENANT_ID]);
    });

    it("shows a skeleton until the balance arrives", async () => {
      renderShell({ name: "Jane", avatar_url: null });

      expect(screen.getByRole("status", { name: "Loading credits" })).toBeInTheDocument();
      await screen.findByText("142 credits left");
      expect(
        screen.queryByRole("status", { name: "Loading credits" }),
      ).not.toBeInTheDocument();
    });

    it("explains what credits are in a tooltip", async () => {
      const user = userEvent.setup();
      renderShell({ name: "Jane", avatar_url: null });

      await user.hover(await screen.findByText("142 credits left"));

      expect(await screen.findByRole("tooltip")).toHaveTextContent(TOOLTIP);
    });

    it("marks the balance as low below the threshold", async () => {
      serveBalance({ credits: 12, tokens: 12_400, is_low: true, is_exhausted: false });
      renderShell({ name: "Jane", avatar_url: null });

      expect(await screen.findByText("12 credits left")).toHaveAttribute(
        "data-balance",
        "low",
      );
    });

    it("says there are no credits left once the balance is exhausted", async () => {
      serveBalance({ credits: -1, tokens: -600, is_low: true, is_exhausted: true });
      renderShell({ name: "Jane", avatar_url: null });

      expect(await screen.findByText("No credits left")).toHaveAttribute(
        "data-balance",
        "exhausted",
      );
    });

    it("says 1 credit, not 1 credits", async () => {
      serveBalance({ credits: 1, tokens: 1_200, is_low: true, is_exhausted: false });
      renderShell({ name: "Jane", avatar_url: null });

      expect(await screen.findByText("1 credit left")).toBeInTheDocument();
    });

    it("shows nothing to a Viewer and does not ask for the balance", async () => {
      const seen = serveBalance({
        credits: 142,
        tokens: 142_310,
        is_low: false,
        is_exhausted: false,
      });
      renderShell({ name: "Jane", avatar_url: null }, "viewer");

      await waitFor(() => expect(screen.getByText("Jane")).toBeInTheDocument());
      expect(screen.queryByText(/credits? left/)).not.toBeInTheDocument();
      expect(seen.tenantIds).toEqual([]);
    });
  });
});
