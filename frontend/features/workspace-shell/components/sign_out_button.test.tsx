import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it, vi } from "vitest";

import { server } from "@/test/mocks/server";
import { renderWithProviders } from "@/test/render_with_providers";

import { SignOutButton } from "./sign_out_button";

const API_URL = "http://localhost:8000/api/v1";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

describe("SignOutButton", () => {
  it("signs out through the API and returns the user to the sign-in page", async () => {
    let logoutCalls = 0;
    server.use(
      http.post(`${API_URL}/auth/logout`, () => {
        logoutCalls += 1;
        return HttpResponse.json({ message: "Signed out." });
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<SignOutButton />);

    await user.click(screen.getByRole("button", { name: "Sign out" }));

    await waitFor(() => expect(push).toHaveBeenCalledWith("/sign-in"));
    expect(logoutCalls).toBe(1);
  });

  it("stays put and says so when signing out fails", async () => {
    server.use(
      http.post(`${API_URL}/auth/logout`, () =>
        HttpResponse.json(
          { error: "Something went wrong", message: "Could not sign you out." },
          { status: 500 },
        ),
      ),
    );
    const user = userEvent.setup();
    renderWithProviders(<SignOutButton />);

    await user.click(screen.getByRole("button", { name: "Sign out" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Could not sign you out.");
    expect(push).not.toHaveBeenCalled();
  });
});
