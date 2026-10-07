import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { server } from "@/test/mocks/server";
import { renderWithProviders } from "@/test/render_with_providers";

import { DocumentViewerDialog } from "./document_viewer_dialog";

vi.mock("react-pdf", () => import("@/test/stub_react_pdf"));

const API_URL = "http://localhost:8000/api/v1";
const TENANT_ID = "0b8e6f0e-6f6e-4c1c-9d55-4a0a4a3b1a10";
const DOCUMENT_ID = "9c1d2e3f-4a5b-4c6d-8e7f-0a1b2c3d4e5f";
const FILE_URL = "http://localhost:9000/kith-dev/report.pdf?signature=abc";

function mockFileUrl(url = FILE_URL) {
  const seen: { tenantIds: (string | null)[] } = { tenantIds: [] };
  server.use(
    http.get(`${API_URL}/documents/${DOCUMENT_ID}/file-url`, ({ request }) => {
      seen.tenantIds.push(request.headers.get("x-tenant-id"));
      return HttpResponse.json({ url, expires_in: 300 });
    }),
  );
  return seen;
}

function Harness({ initialPage }: { initialPage?: number }) {
  const [open, setOpen] = useState(true);
  return (
    <DocumentViewerDialog
      tenantId={TENANT_ID}
      documentId={DOCUMENT_ID}
      documentName="report.pdf"
      initialPage={initialPage}
      open={open}
      onOpenChange={setOpen}
    />
  );
}

describe("DocumentViewerDialog", () => {
  it("shows the Document's name and its first page of the real file", async () => {
    const seen = mockFileUrl();

    renderWithProviders(<Harness />);

    expect(
      await screen.findByRole("dialog", { name: "report.pdf" }),
    ).toBeInTheDocument();
    expect(await screen.findByText("PDF page 1")).toBeInTheDocument();
    expect(screen.getByText("Page 1 of 3")).toBeInTheDocument();
    expect(seen.tenantIds).toEqual([TENANT_ID]);
  });

  it("starts at the page it is given", async () => {
    mockFileUrl();

    renderWithProviders(<Harness initialPage={2} />);

    expect(await screen.findByText("PDF page 2")).toBeInTheDocument();
    expect(screen.getByText("Page 2 of 3")).toBeInTheDocument();
  });

  it("steps one page at a time and stops at both ends", async () => {
    mockFileUrl();
    const user = userEvent.setup();
    renderWithProviders(<Harness />);
    await screen.findByText("PDF page 1");
    const previous = screen.getByRole("button", { name: "Previous page" });
    const next = screen.getByRole("button", { name: "Next page" });

    expect(previous).toBeDisabled();
    expect(next).toBeEnabled();

    await user.click(next);
    expect(screen.getByText("PDF page 2")).toBeInTheDocument();
    expect(screen.getByText("Page 2 of 3")).toBeInTheDocument();
    expect(previous).toBeEnabled();

    await user.click(next);
    expect(screen.getByText("Page 3 of 3")).toBeInTheDocument();
    expect(next).toBeDisabled();

    await user.click(previous);
    expect(screen.getByText("Page 2 of 3")).toBeInTheDocument();
  });

  it("opens the full document in a new tab", async () => {
    mockFileUrl();
    renderWithProviders(<Harness />);

    const link = await screen.findByRole("link", {
      name: "Open full document",
    });

    expect(link).toHaveAttribute("href", FILE_URL);
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", expect.stringContaining("noopener"));
  });

  it("shows a loading state while the link is being fetched", async () => {
    server.use(
      http.get(`${API_URL}/documents/${DOCUMENT_ID}/file-url`, async () => {
        await new Promise(() => {});
      }),
    );

    renderWithProviders(<Harness />);

    expect(await screen.findByText("Loading document…")).toBeInTheDocument();
  });

  it("says so when the link cannot be fetched", async () => {
    server.use(
      http.get(`${API_URL}/documents/${DOCUMENT_ID}/file-url`, () =>
        HttpResponse.json(
          { error: "Document not found", message: "gone" },
          { status: 404 },
        ),
      ),
    );

    renderWithProviders(<Harness />);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Could not load the document.",
    );
    expect(
      screen.queryByRole("link", { name: "Open full document" }),
    ).not.toBeInTheDocument();
  });

  it("says so when the PDF cannot be loaded", async () => {
    mockFileUrl("http://localhost:9000/kith-dev/broken.pdf");

    renderWithProviders(<Harness />);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Could not load the document.",
    );
    expect(screen.queryByText("PDF page 1")).not.toBeInTheDocument();
  });

  it("asks for nothing while closed", async () => {
    const seen = mockFileUrl();

    renderWithProviders(
      <DocumentViewerDialog
        tenantId={TENANT_ID}
        documentId={DOCUMENT_ID}
        documentName="report.pdf"
        open={false}
        onOpenChange={() => {}}
      />,
    );

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(seen.tenantIds).toEqual([]);
  });
});
