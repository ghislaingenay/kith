import { fireEvent, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api_client";
import { setImageLoadOutcome } from "@/test/stub_image_loading";
import { renderWithProviders } from "@/test/render_with_providers";

import { uploadAvatar } from "../api/upload_avatar";
import { useProfile } from "../api/use_profile";
import type { Profile } from "../types";
import { AvatarEditor } from "./avatar_editor";

// jsdom's FormData/File can't be sent through Node's fetch, so the upload
// call is mocked here; its real multipart request is covered by
// api/upload_avatar.test.ts, which runs in the node environment.
vi.mock("../api/upload_avatar", () => ({ uploadAvatar: vi.fn() }));

const EMAIL = "jane@example.com";
const AVATAR_URL = "https://cdn.example.com/user/u1/avatar/avatar.png?signature=abc";
const NEW_AVATAR_URL = "https://cdn.example.com/user/u1/avatar/avatar.png?signature=new";
const MAX_AVATAR_BYTES = 2 * 1024 * 1024;

function renderEditor(overrides: Partial<Profile> = {}) {
  const profile: Profile = { email: EMAIL, name: "Jane", avatar_url: null, ...overrides };
  // Reads through the shared cache like the real page, so a saved avatar
  // flows back into the editor.
  function Editor() {
    return <AvatarEditor profile={useProfile(profile)} />;
  }
  return renderWithProviders(<Editor />);
}

async function openDialog() {
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Change profile photo" }));
  return { user, dialog: await screen.findByRole("dialog", { name: "Profile photo" }) };
}

function pngFile(name = "me.png", size = 1024) {
  return new File([new Uint8Array(size)], name, { type: "image/png" });
}

function mockUploadSuccess() {
  vi.mocked(uploadAvatar).mockResolvedValue({
    email: EMAIL,
    name: "Jane",
    avatar_url: NEW_AVATAR_URL,
  });
}

afterEach(() => {
  vi.mocked(uploadAvatar).mockReset();
});

describe("AvatarEditor", () => {
  it("shows the current avatar, with an edit button over it", async () => {
    renderEditor({ avatar_url: AVATAR_URL });

    expect(screen.getByRole("button", { name: "Change profile photo" })).toBeInTheDocument();
    expect(await screen.findByRole("img", { name: "Jane" })).toHaveAttribute("src", AVATAR_URL);
  });

  it("opens a dialog with the same image enlarged", async () => {
    renderEditor({ avatar_url: AVATAR_URL });

    const { dialog } = await openDialog();

    expect(await within(dialog).findByRole("img", { name: "Jane" })).toHaveAttribute(
      "src",
      AVATAR_URL,
    );
    expect(within(dialog).queryByText("No profile photo yet.")).not.toBeInTheDocument();
  });

  it("says there is no photo when the person never set one", async () => {
    renderEditor({ avatar_url: null });

    const { dialog } = await openDialog();

    expect(within(dialog).getByText("No profile photo yet.")).toBeInTheDocument();
    expect(within(dialog).queryByRole("img")).not.toBeInTheDocument();
  });

  it("says there is no photo when the stored image can no longer be loaded", async () => {
    setImageLoadOutcome("error");
    renderEditor({ avatar_url: AVATAR_URL });

    const { dialog } = await openDialog();

    expect(await within(dialog).findByText("No profile photo yet.")).toBeInTheDocument();
    expect(within(dialog).queryByRole("img")).not.toBeInTheDocument();
  });

  it("closes without changing anything", async () => {
    renderEditor({ avatar_url: AVATAR_URL });
    const { user, dialog } = await openDialog();

    await user.click(within(dialog).getByRole("button", { name: "Close" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(uploadAvatar).not.toHaveBeenCalled();
  });

  it("uploads a chosen image at once and shows the new one", async () => {
    mockUploadSuccess();
    renderEditor({ avatar_url: null });
    const { user, dialog } = await openDialog();

    await user.upload(within(dialog).getByLabelText("Profile photo file"), pngFile());

    expect(await within(dialog).findByRole("status")).toHaveTextContent("Photo updated");
    expect(vi.mocked(uploadAvatar).mock.calls[0][0].name).toBe("me.png");
    expect(await within(dialog).findByRole("img", { name: "Jane" })).toHaveAttribute(
      "src",
      NEW_AVATAR_URL,
    );
    expect(within(dialog).queryByText("No profile photo yet.")).not.toBeInTheDocument();
  });

  it("uploads an image dropped onto the drop zone", async () => {
    mockUploadSuccess();
    renderEditor({ avatar_url: null });
    const { dialog } = await openDialog();

    const dropZone = within(dialog).getByText("Drag an image here, or").parentElement!;
    fireEvent.drop(dropZone, { dataTransfer: { files: [pngFile("dropped.png")] } });

    expect(await within(dialog).findByRole("status")).toHaveTextContent("Photo updated");
    expect(vi.mocked(uploadAvatar).mock.calls[0][0].name).toBe("dropped.png");
  });

  it("rejects a file that is not a JPEG or PNG without calling the API", async () => {
    const user = userEvent.setup({ applyAccept: false });
    renderEditor();
    await user.click(screen.getByRole("button", { name: "Change profile photo" }));
    const dialog = await screen.findByRole("dialog");

    const gif = new File(["GIF89a"], "me.gif", { type: "image/gif" });
    await user.upload(within(dialog).getByLabelText("Profile photo file"), gif);

    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "Avatar must be a JPEG or PNG image.",
    );
    expect(uploadAvatar).not.toHaveBeenCalled();
  });

  it("rejects an image over 2 MB without calling the API", async () => {
    renderEditor();
    const { user, dialog } = await openDialog();

    await user.upload(
      within(dialog).getByLabelText("Profile photo file"),
      pngFile("big.png", MAX_AVATAR_BYTES + 1),
    );

    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "Avatar image must be 2 MB or smaller.",
    );
    expect(uploadAvatar).not.toHaveBeenCalled();
  });

  it("shows the server's message when the upload fails, keeping the current image", async () => {
    vi.mocked(uploadAvatar).mockRejectedValue(new ApiError(422, "Avatar image is empty."));
    renderEditor({ avatar_url: AVATAR_URL });
    const { user, dialog } = await openDialog();

    await user.upload(within(dialog).getByLabelText("Profile photo file"), pngFile());

    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "Avatar image is empty.",
    );
    expect(within(dialog).queryByRole("status")).not.toBeInTheDocument();
    expect(await within(dialog).findByRole("img", { name: "Jane" })).toHaveAttribute(
      "src",
      AVATAR_URL,
    );
  });
});
