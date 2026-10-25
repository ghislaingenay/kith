import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it, vi } from "vitest";

import { server } from "@/test/mocks/server";
import { renderWithProviders } from "@/test/render_with_providers";

import { SignInScreen } from "./sign_in_screen";

const API_URL = "http://localhost:8000/api/v1";

const replace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
}));

function renderScreen(linkError: string | null = null) {
  return renderWithProviders(<SignInScreen linkError={linkError} />);
}

describe("SignInScreen", () => {
  it("shows the wordmark and the email form, with a decorative drawing", async () => {
    const { container } = renderScreen();

    expect(screen.getByRole("heading", { level: 1, name: "Kith" })).toBeInTheDocument();
    expect(screen.getByLabelText("Work email")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send Magic Link" })).toBeInTheDocument();

    const drawings = container.querySelectorAll("svg");
    expect(drawings.length).toBeGreaterThan(0);
    drawings.forEach((svg) => expect(svg).toHaveAttribute("aria-hidden", "true"));
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("keeps the form's validation message", async () => {
    const user = userEvent.setup();
    renderScreen();

    await user.click(screen.getByRole("button", { name: "Send Magic Link" }));

    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });

  it("swaps the form for 'Check your email' under the same wordmark", async () => {
    server.use(
      http.post(`${API_URL}/auth/magic-link`, () =>
        HttpResponse.json({ message: "If that email has an account, a link is on its way." }),
      ),
    );
    const user = userEvent.setup();
    renderScreen();

    await user.type(screen.getByLabelText("Work email"), "jane@example.com");
    await user.click(screen.getByRole("button", { name: "Send Magic Link" }));

    expect(await screen.findByRole("status")).toHaveTextContent("Check your email");
    expect(screen.getByRole("heading", { level: 1, name: "Kith" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Work email")).not.toBeInTheDocument();
  });

  it("shows a link error in the same layout, with a way back to the form", async () => {
    const user = userEvent.setup();
    renderScreen("That sign-in link has expired. Links are valid for 15 minutes.");

    expect(screen.getByRole("alert")).toHaveTextContent("That sign-in link has expired.");
    expect(screen.getByRole("heading", { level: 1, name: "Kith" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Back to login" }));

    expect(replace).toHaveBeenCalledWith("/sign-in");
    expect(screen.getByLabelText("Work email")).toBeInTheDocument();
  });
});
