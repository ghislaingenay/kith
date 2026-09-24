import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { setImageLoadOutcome } from "@/test/stub_image_loading";

import { UserAvatar } from "./user_avatar";

const URL_ = "https://cdn.example.com/user/u1/avatar/avatar.png?signature=abc";

function skeleton(container: HTMLElement) {
  return container.querySelector('[data-slot="skeleton"]');
}

describe("UserAvatar", () => {
  it("shows a placeholder, not the initial, while the image is being fetched", async () => {
    const { container } = render(<UserAvatar displayName="Jane" avatarUrl={URL_} />);

    expect(skeleton(container)).toBeInTheDocument();
    expect(screen.queryByText("J")).not.toBeInTheDocument();
    expect(container.firstElementChild).toHaveAttribute("aria-busy", "true");

    expect(await screen.findByRole("img", { name: "Jane" })).toHaveAttribute("src", URL_);
    expect(skeleton(container)).not.toBeInTheDocument();
    expect(container.firstElementChild).toHaveAttribute("aria-busy", "false");
  });

  it("falls back to the initial once the image fails to load", async () => {
    setImageLoadOutcome("error");
    const { container } = render(<UserAvatar displayName="Jane" avatarUrl={URL_} />);

    expect(await screen.findByText("J")).toBeInTheDocument();
    expect(skeleton(container)).not.toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("shows the initial straight away when there is no avatar to fetch", () => {
    const { container } = render(<UserAvatar displayName="Jane" avatarUrl={null} />);

    expect(screen.getByText("J")).toBeInTheDocument();
    expect(skeleton(container)).not.toBeInTheDocument();
  });

  it("shows the placeholder again when the avatar changes to a new URL", async () => {
    const { container, rerender } = render(<UserAvatar displayName="Jane" avatarUrl={URL_} />);
    await screen.findByRole("img", { name: "Jane" });

    rerender(<UserAvatar displayName="Jane" avatarUrl={`${URL_}&v=2`} />);

    expect(await screen.findByRole("img", { name: "Jane" })).toHaveAttribute(
      "src",
      `${URL_}&v=2`,
    );
    expect(skeleton(container)).not.toBeInTheDocument();
  });
});
