import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test/render_with_providers";
import { server } from "@/test/mocks/server";

import { OnboardingForm } from "./onboarding_form";

const API_URL = "http://localhost:8000/api/v1";
const SUGGESTED_NAME = "susan's organization";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

function renderForm() {
  return renderWithProviders(<OnboardingForm suggestedWorkspaceName={SUGGESTED_NAME} />);
}

describe("OnboardingForm", () => {
  it("pre-fills the suggested workspace name", () => {
    renderForm();

    expect(screen.getByLabelText("Workspace name")).toHaveValue(SUGGESTED_NAME);
  });

  it("rejects an empty workspace name", async () => {
    const user = userEvent.setup();
    renderForm();

    await user.clear(screen.getByLabelText("Workspace name"));
    await user.click(screen.getByRole("button", { name: /create workspace/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Enter a name for your workspace.",
    );
    expect(push).not.toHaveBeenCalled();
  });

  it("rejects a workspace name over 255 characters", async () => {
    const user = userEvent.setup();
    renderForm();

    const nameInput = screen.getByLabelText("Workspace name");
    await user.clear(nameInput);
    await user.type(nameInput, "a".repeat(256));
    await user.click(screen.getByRole("button", { name: /create workspace/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Keep it under 255 characters.",
    );
    expect(push).not.toHaveBeenCalled();
  });

  it("shows a loading state, then redirects to the new tenant on success", async () => {
    server.use(
      http.post(`${API_URL}/tenants`, async () => {
        await new Promise((resolve) => setTimeout(resolve, 20));
        return HttpResponse.json(
          {
            tenant_id: "t1",
            tenant_name: "Susan's organization",
            tenant_slug: "susans-org",
            role: "owner",
          },
          { status: 201 },
        );
      }),
    );

    const user = userEvent.setup();
    renderForm();

    const submitButton = screen.getByRole("button", { name: /create workspace/i });
    await user.click(submitButton);

    expect(await screen.findByRole("button", { name: /creating/i })).toBeDisabled();

    await waitFor(() => expect(push).toHaveBeenCalledWith("/w/susans-org"));
  });

  it("shows an error message when the request fails", async () => {
    server.use(
      http.post(`${API_URL}/tenants`, () =>
        HttpResponse.json(
          {
            error: "Something went wrong",
            message: "Something went wrong creating your workspace.",
          },
          { status: 500 },
        ),
      ),
    );

    const user = userEvent.setup();
    renderForm();

    await user.click(screen.getByRole("button", { name: /create workspace/i }));

    expect(
      await screen.findByText("Something went wrong creating your workspace."),
    ).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });
});
