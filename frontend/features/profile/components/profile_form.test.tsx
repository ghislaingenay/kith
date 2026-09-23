import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api_client";
import { server } from "@/test/mocks/server";
import { renderWithProviders } from "@/test/render_with_providers";

import { uploadAvatar } from "../api/upload_avatar";

import type { Profile } from "../types";
import { ProfileForm } from "./profile_form";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh }),
}));

// jsdom's FormData/File can't be sent through Node's fetch, so the upload
// call is mocked here; its real multipart request is covered by
// api/upload_avatar.test.ts, which runs in the node environment.
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

  it("shows the current avatar image", () => {
    renderForm({ name: "Jane Doe", avatar_url: AVATAR_URL });

    expect(screen.getByRole("img", { name: "Jane Doe" })).toHaveAttribute(
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
  it("saves the trimmed name, confirms it, and refreshes the shell", async () => {
    const bodies = mockProfileUpdate();
    const user = userEvent.setup();
    renderForm({ name: "Jane" });

    const nameInput = screen.getByLabelText("Name");
    await user.clear(nameInput);
    await user.type(nameInput, "  Janet Doe  ");
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByRole("status")).toHaveTextContent("Profile saved");
    expect(bodies).toEqual([{ name: "Janet Doe" }]);
    expect(screen.getByRole("heading", { name: "Janet Doe" })).toBeInTheDocument();
    expect(refresh).toHaveBeenCalled();
  });

  it("clears the name when the field is emptied, falling back to the email", async () => {
    const bodies = mockProfileUpdate();
    const user = userEvent.setup();
    renderForm({ name: "Jane" });

    await user.clear(screen.getByLabelText("Name"));
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByRole("status")).toHaveTextContent("Profile saved");
    expect(bodies).toEqual([{ name: null }]);
    expect(screen.getByRole("heading", { name: EMAIL })).toBeInTheDocument();
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

const NEW_AVATAR_URL = "https://cdn.example.com/user/u1/avatar/avatar.png?signature=new";
const MAX_AVATAR_BYTES = 2 * 1024 * 1024;

function pngFile(name = "me.png", size = 1024) {
  return new File([new Uint8Array(size)], name, { type: "image/png" });
}

/** Logs the avatar upload and the name save in one sequence, so a test can
 * assert the upload happens before the name is saved. */
function mockAvatarSave() {
  const calls: string[] = [];
  vi.mocked(uploadAvatar).mockImplementation(async () => {
    calls.push("avatar");
    return { email: EMAIL, name: null, avatar_url: NEW_AVATAR_URL };
  });
  server.use(
    http.patch(`${API_URL}/users/me/profile`, async ({ request }) => {
      const body = (await request.json()) as { name: string | null };
      calls.push("profile");
      return HttpResponse.json({
        email: EMAIL,
        name: body.name,
        avatar_url: NEW_AVATAR_URL,
      });
    }),
  );
  return calls;
}

describe("ProfileForm avatar", () => {
  afterEach(() => {
    vi.mocked(uploadAvatar).mockReset();
  });

  it("keeps showing the current avatar while a new file is picked, before saving", async () => {
    const user = userEvent.setup();
    renderForm({ name: "Jane", avatar_url: AVATAR_URL });

    await user.upload(screen.getByLabelText("Avatar"), pngFile());

    expect(screen.getByRole("img", { name: "Jane" })).toHaveAttribute("src", AVATAR_URL);
  });

  it("uploads the chosen image, then saves the name, and shows the new avatar", async () => {
    const calls = mockAvatarSave();
    const user = userEvent.setup();
    renderForm({ name: "Jane" });

    await user.upload(screen.getByLabelText("Avatar"), pngFile());
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByRole("status")).toHaveTextContent("Profile saved");
    expect(calls).toEqual(["avatar", "profile"]);
    expect(vi.mocked(uploadAvatar).mock.calls[0][0].name).toBe("me.png");
    expect(screen.getByRole("img", { name: "Jane" })).toHaveAttribute(
      "src",
      NEW_AVATAR_URL,
    );
  });

  it("rejects a file that is not a JPEG or PNG without calling the API", async () => {
    const calls = mockAvatarSave();
    const user = userEvent.setup({ applyAccept: false });
    renderForm({ name: "Jane" });

    const gif = new File(["GIF89a"], "me.gif", { type: "image/gif" });
    await user.upload(screen.getByLabelText("Avatar"), gif);
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Avatar must be a JPEG or PNG image.",
    );
    expect(calls).toEqual([]);
  });

  it("rejects an image over 2 MB without calling the API", async () => {
    const calls = mockAvatarSave();
    const user = userEvent.setup();
    renderForm({ name: "Jane" });

    await user.upload(
      screen.getByLabelText("Avatar"),
      pngFile("big.png", MAX_AVATAR_BYTES + 1),
    );
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Avatar image must be 2 MB or smaller.",
    );
    expect(calls).toEqual([]);
  });

  it("shows the server's message and does not save the name when the upload fails", async () => {
    const calls: string[] = [];
    vi.mocked(uploadAvatar).mockRejectedValue(
      new ApiError(422, "Avatar image is empty."),
    );
    server.use(
      http.patch(`${API_URL}/users/me/profile`, () => {
        calls.push("profile");
        return HttpResponse.json({ email: EMAIL, name: "Jane", avatar_url: null });
      }),
    );
    const user = userEvent.setup();
    renderForm({ name: "Jane" });

    await user.upload(screen.getByLabelText("Avatar"), pngFile());
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Avatar image is empty.");
    expect(calls).toEqual([]);
  });
});
