import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CardPageSkeleton, WorkspacePageSkeleton } from "./page_skeleton";

describe("page skeletons", () => {
  it.each([
    ["CardPageSkeleton", CardPageSkeleton],
    ["WorkspacePageSkeleton", WorkspacePageSkeleton],
  ])("%s announces that the page is loading", (_name, PageSkeleton) => {
    render(<PageSkeleton />);

    expect(screen.getByRole("status", { name: "Loading" })).toBeInTheDocument();
  });
});
