import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it, vi } from "vitest";

import { server } from "@/test/mocks/server";
import { renderWithProviders } from "@/test/render_with_providers";

import { uploadAvatar } from "../api/upload_avatar";
import { useProfile } from "../api/use_profile";
import type { Profile } from "../types";
import { ProfileForm } from "./profile_form";

// jsdom's FormData/File can't go through Node's fetch; the real multipart
// request is covered by api/upload_avatar.test.ts.
vi.mock("../api/upload_avatar", () => ({ uploadAvatar: vi.fn() }));

const API_URL = "http://localhost:8000/api/v1";
const EMAIL = "jane@example.com";
const AVATAR_URL = "https://cdn.example.com/user/u1/avatar/avatar.png?signature=abc";

function renderForm(overrides: Partial<Profile> = {}) {
  const profile: Profile = { email: EMAIL, name: null, avatar_url: null, ...overrides };
  return renderWithProviders(<ProfileForm profile={profile} />);
}

describe("ProfileForm display", () => {
  it("pre-fills the current name", () => {
    renderForm({ name: "Jane Doe" });

    expect(screen.getByLabelText("Name")).toHaveValue("Jane Doe");
    expect(screen.getByRole("heading", { name: "Jane Doe" })).toBeInTheDocument();
  });

  it("falls back to the email as the displayed name when no name is set", () => {
    renderForm({ name: null });

    expect(screen.getByLabelText("Name")).toHaveValue("");
    expect(screen.getByLabelText("Name")).toHaveAttribute("placeholder", EMAIL);
    expect(screen.getByRole("heading", { name: EMAIL })).toBeInTheDocument();
  });

  it("shows the current avatar image", async () => {
    renderForm({ name: "Jane Doe", avatar_url: AVATAR_URL });

    expect(await screen.findByRole("img", { name: "Jane Doe" })).toHaveAttribute(
      "src",
      AVATAR_URL,
    );
  });

  it("shows an initial in place of an avatar when none is set", () => {
    renderForm({ name: "Jane Doe", avatar_url: null });

    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.getByText("J")).toBeInTheDocument();
  });
});

/** Captures the JSON body of every PATCH /users/me/profile and answers with
 * the profile the API would return for it. */
function mockProfileUpdate() {
  const bodies: unknown[] = [];
  server.use(
    http.patch(`${API_URL}/users/me/profile`, async ({ request }) => {
      const body = (await request.json()) as { name: string | null };
      bodies.push(body);
      return HttpResponse.json({ email: EMAIL, name: body.name, avatar_url: null });
    }),
  );
  return bodies;
}

describe("ProfileForm saving the name", () => {
  it("saves the trimmed name and confirms it", async () => {
    const bodies = mockProfileUpdate();
    const user = userEvent.setup();
    renderForm({ name: "Jane" });

    const nameInput = screen.getByLabelText("Name");
    await user.clear(nameInput);
    await user.type(nameInput, "  Janet Doe  ");
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByRole("status")).toHaveTextContent("Profile saved");
    expect(bodies).toEqual([{ name: "Janet Doe" }]);
    expect(await screen.findByRole("heading", { name: "Janet Doe" })).toBeInTheDocument();
  });

  it("writes the saved profile into the shared cache other components read", async () => {
    mockProfileUpdate();
    const user = userEvent.setup();
    const profile: Profile = { email: EMAIL, name: "Jane", avatar_url: null };
    function Sidebar() {
      return <p data-testid="sidebar">{useProfile(profile).name}</p>;
    }
    renderWithProviders(
      <>
        <Sidebar />
        <ProfileForm profile={profile} />
      </>,
    );

    const nameInput = screen.getByLabelText("Name");
    await user.clear(nameInput);
    await user.type(nameInput, "Janet");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await screen.findByRole("status");
    expect(screen.getByTestId("sidebar")).toHaveTextContent("Janet");
  });

  it("clears the name when the field is emptied, falling back to the email", async () => {
    const bodies = mockProfileUpdate();
    const user = userEvent.setup();
    renderForm({ name: "Jane" });

    await user.clear(screen.getByLabelText("Name"));
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByRole("status")).toHaveTextContent("Profile saved");
    expect(bodies).toEqual([{ name: null }]);
    expect(await screen.findByRole("heading", { name: EMAIL })).toBeInTheDocument();
  });

  it("shows a saving state while the request is in flight", async () => {
    server.use(
      http.patch(`${API_URL}/users/me/profile`, async () => {
        await new Promise((resolve) => setTimeout(resolve, 20));
        return HttpResponse.json({ email: EMAIL, name: "Jane", avatar_url: null });
      }),
    );
    const user = userEvent.setup();
    renderForm({ name: "Jane" });

    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByRole("button", { name: "Saving…" })).toBeDisabled();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Save" })).toBeEnabled(),
    );
  });

  it("rejects a name over 100 characters without calling the API", async () => {
    const bodies = mockProfileUpdate();
    const user = userEvent.setup();
    renderForm({ name: "Jane" });

    const nameInput = screen.getByLabelText("Name");
    await user.clear(nameInput);
    await user.type(nameInput, "a".repeat(101));
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Keep it under 100 characters.",
    );
    expect(bodies).toEqual([]);
  });

  it("shows the server's error message when saving fails", async () => {
    server.use(
      http.patch(`${API_URL}/users/me/profile`, () =>
        HttpResponse.json(
          { error: "Something went wrong", message: "Could not save your profile." },
          { status: 500 },
        ),
      ),
    );
    const user = userEvent.setup();
    renderForm({ name: "Jane" });

    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Could not save your profile.",
    );
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});

describe("ProfileForm avatar", () => {
  it("shows a newly uploaded avatar in the form and in the shared cache", async () => {
    const newUrl = "https://cdn.example.com/user/u1/avatar/avatar.png?signature=new";
    vi.mocked(uploadAvatar).mockResolvedValue({
      email: EMAIL,
      name: "Jane",
      avatar_url: newUrl,
    });
    const user = userEvent.setup();
    const profile: Profile = { email: EMAIL, name: "Jane", avatar_url: AVATAR_URL };
    function Sidebar() {
      return <p data-testid="sidebar">{useProfile(profile).avatar_url}</p>;
    }
    renderWithProviders(
      <>
        <Sidebar />
        <ProfileForm profile={profile} />
      </>,
    );
    expect(await screen.findByRole("img", { name: "Jane" })).toHaveAttribute("src", AVATAR_URL);

    await user.click(screen.getByRole("button", { name: "Change profile photo" }));
    const dialog = await screen.findByRole("dialog");
    await user.upload(
      within(dialog).getByLabelText("Profile photo file"),
      new File([new Uint8Array(10)], "me.png", { type: "image/png" }),
    );
    await within(dialog).findByRole("status");
    await user.click(within(dialog).getByRole("button", { name: "Close" }));

    // The thumbnail in the form, not just the dialog, and the sidebar's cache.
    expect(await screen.findByRole("img", { name: "Jane" })).toHaveAttribute("src", newUrl);
    expect(screen.getByTestId("sidebar")).toHaveTextContent(newUrl);
  });
});
