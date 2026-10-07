import { QueryClient } from "@tanstack/react-query";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { server } from "@/test/mocks/server";
import { renderWithProviders } from "@/test/render_with_providers";

import { UploadScreen } from "./upload_screen";
import { UploadsLibrary } from "./uploads_library";

const API_URL = "http://localhost:8000/api/v1";
const STORAGE_URL = "https://storage.example.com/pending/t1/u1?signature=abc";
const TENANT_ID = "0b8e6f0e-6f6e-4c1c-9d55-4a0a4a3b1a10";
const UPLOAD_ID = "5a2f7d10-3c1e-4e59-8f0b-1d2c3b4a5e6f";
const DOCUMENT_ID = "9c1d2e3f-4a5b-4c6d-8e7f-0a1b2c3d4e5f";
const MAX_BYTES = 20 * 1024 * 1024;

function pdfFile(name = "report.pdf", size = 1024) {
  return new File([new Uint8Array(size)], name, { type: "application/pdf" });
}

type Seen = {
  init?: { tenantId: string | null; body: Record<string, unknown> };
  put?: { contentType: string | null; checksum: string | null; bytes: number };
  finalized: number;
};

function mockUploadApi(): Seen {
  const seen: Seen = { finalized: 0 };
  server.use(
    http.post(`${API_URL}/uploads/init`, async ({ request }) => {
      seen.init = {
        tenantId: request.headers.get("x-tenant-id"),
        body: (await request.json()) as Record<string, unknown>,
      };
      return HttpResponse.json(
        {
          upload_id: UPLOAD_ID,
          url: STORAGE_URL,
          method: "PUT",
          headers: {
            "Content-Type": "application/pdf",
            "x-amz-checksum-sha256": "checksum-from-server",
          },
          expires_in: 600,
        },
        { status: 201 },
      );
    }),
    http.put(STORAGE_URL, async ({ request }) => {
      seen.put = {
        contentType: request.headers.get("content-type"),
        checksum: request.headers.get("x-amz-checksum-sha256"),
        bytes: (await request.arrayBuffer()).byteLength,
      };
      return new HttpResponse(null, { status: 200 });
    }),
    http.post(`${API_URL}/uploads/${UPLOAD_ID}/finalize`, () => {
      seen.finalized += 1;
      return HttpResponse.json({
        id: DOCUMENT_ID,
        name: "report.pdf",
        size_bytes: 1024,
        page_count: 3,
        content_hash: "a".repeat(64),
        ingestion_status: "uploaded",
      });
    }),
  );
  return seen;
}

async function choose(file: File) {
  const user = userEvent.setup({ applyAccept: false });
  renderWithProviders(<UploadScreen tenantId={TENANT_ID} />);
  await user.upload(screen.getByLabelText("PDF file"), file);
}

describe("UploadScreen", () => {
  it("invalidates the Tenant's Search queries after a successful upload", async () => {
    mockUploadApi();
    const client = new QueryClient();
    client.setQueryData(["search", TENANT_ID, "cat"], { degraded: false, results: [] });
    client.setQueryData(["search", "other-tenant", "cat"], { degraded: false, results: [] });
    const user = userEvent.setup({ applyAccept: false });
    renderWithProviders(<UploadScreen tenantId={TENANT_ID} />, client);

    await user.upload(screen.getByLabelText("PDF file"), pdfFile());

    await waitFor(() =>
      expect(client.getQueryState(["search", TENANT_ID, "cat"])?.isInvalidated).toBe(true),
    );
    expect(client.getQueryState(["search", "other-tenant", "cat"])?.isInvalidated).toBe(false);
  });

  it("tells the person what can be uploaded", () => {
    renderWithProviders(<UploadScreen tenantId={TENANT_ID} />);

    expect(screen.getByText("PDF, up to 20 MB")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Select File" })).toBeInTheDocument();
  });

  describe("one PDF at a time", () => {
    it("only lets the person pick a single file", () => {
      renderWithProviders(<UploadScreen tenantId={TENANT_ID} />);

      expect(screen.getByLabelText("PDF file")).not.toHaveAttribute("multiple");
    });

    it("refuses several files at once without calling the API", async () => {
      // No handlers registered: an unexpected request would fail the test.
      renderWithProviders(<UploadScreen tenantId={TENANT_ID} />);

      fireEvent.change(screen.getByLabelText("PDF file"), {
        target: { files: [pdfFile("a.pdf"), pdfFile("b.pdf")] },
      });

      expect(await screen.findByRole("alert")).toHaveTextContent(
        "Upload one PDF at a time.",
      );
      expect(screen.queryByText("a.pdf")).not.toBeInTheDocument();
      expect(screen.queryByText("b.pdf")).not.toBeInTheDocument();
    });

    it("cannot pick another file while one is uploading, then can again", async () => {
      const seen = mockUploadApi();
      let releaseStorage: () => void = () => {};
      const storageHeld = new Promise<void>((resolve) => {
        releaseStorage = resolve;
      });
      server.use(
        http.put(STORAGE_URL, async () => {
          await storageHeld;
          return new HttpResponse(null, { status: 200 });
        }),
      );

      await choose(pdfFile("first.pdf"));

      expect(await screen.findByText("Uploading…")).toBeInTheDocument();
      expect(screen.getByLabelText("PDF file")).toBeDisabled();
      expect(screen.getByRole("button", { name: "Select File" })).toBeDisabled();

      releaseStorage();

      expect(await screen.findByText("Accepted")).toBeInTheDocument();
      await waitFor(() => expect(screen.getByLabelText("PDF file")).toBeEnabled());
      expect(seen.finalized).toBe(1);
    });
  });

  it("shows a chosen PDF as accepted once it has been uploaded and finalized", async () => {
    const seen = mockUploadApi();

    await choose(pdfFile("report.pdf"));

    expect(await screen.findByText("Accepted")).toBeInTheDocument();
    expect(screen.getByText("report.pdf")).toBeInTheDocument();
    expect(seen.finalized).toBe(1);
  });

  it("asks the API to start the upload for this Tenant, describing the file", async () => {
    const seen = mockUploadApi();

    await choose(pdfFile("report.pdf", 2048));
    await screen.findByText("Accepted");

    expect(seen.init?.tenantId).toBe(TENANT_ID);
    expect(seen.init?.body).toMatchObject({
      filename: "report.pdf",
      size: 2048,
      content_type: "application/pdf",
    });
    // SHA-256 of 2048 zero bytes, from an independent source (sha256sum).
    expect(seen.init?.body.sha256).toBe(
      "e5a00aa9991ac8a5ee3109844d84a55583bd20572ad3ffcd42792f3c36b183ad",
    );
  });

  it("sends the file straight to storage with the headers the API asked for", async () => {
    const seen = mockUploadApi();

    await choose(pdfFile("report.pdf", 2048));
    await screen.findByText("Accepted");

    expect(seen.put).toEqual({
      contentType: "application/pdf",
      checksum: "checksum-from-server",
      bytes: 2048,
    });
  });

  it("makes the library list the new Document as soon as the upload is accepted", async () => {
    const seen = mockUploadApi();
    server.use(
      http.get(`${API_URL}/documents`, () =>
        HttpResponse.json(
          seen.finalized === 0
            ? []
            : [
                {
                  id: DOCUMENT_ID,
                  name: "report.pdf",
                  size_bytes: 1024,
                  uploader: "Jane Doe",
                  created_at: "2026-09-01T12:00:00Z",
                  ingestion_status: "uploaded",
                  ingestion_stage: null,
                  pages_extracted: null,
                  page_count: 3,
                },
              ],
        ),
      ),
      http.get(`${API_URL}/documents/summary`, () =>
        HttpResponse.json({ in_progress: 0, failed: 0 }),
      ),
    );
    const user = userEvent.setup({ applyAccept: false });
    renderWithProviders(
      <>
        <UploadScreen tenantId={TENANT_ID} />
        <UploadsLibrary tenantId={TENANT_ID} />
      </>,
    );
    await screen.findByText("No documents yet");

    await user.upload(screen.getByLabelText("PDF file"), pdfFile("report.pdf"));

    const table = await screen.findByRole("table");
    expect(within(table).getByText("report.pdf")).toBeInTheDocument();
  });

  it("shows the API's reason when it refuses the file", async () => {
    server.use(
      http.post(`${API_URL}/uploads/init`, () =>
        HttpResponse.json(
          { error: "Invalid upload", message: "File must be 20 MB or smaller." },
          { status: 422 },
        ),
      ),
    );

    await choose(pdfFile());

    expect(await screen.findByRole("alert")).toHaveTextContent("File must be 20 MB or smaller.");
    expect(screen.queryByText("Accepted")).not.toBeInTheDocument();
  });

  it("refuses a file that is not a PDF without calling the API", async () => {
    // No handlers registered: an unexpected request would fail the test.
    await choose(new File(["hello"], "notes.txt", { type: "text/plain" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Only PDF files can be uploaded.");
  });

  it("refuses a file over 20 MB without calling the API", async () => {
    await choose(pdfFile("big.pdf", MAX_BYTES + 1));

    expect(await screen.findByRole("alert")).toHaveTextContent("File must be 20 MB or smaller.");
  });

  describe("a file the API refuses", () => {
    const refusals = [
      {
        stage: "start",
        status: 409,
        error: "Duplicate document",
        message: '"budget.pdf" was already uploaded by Jane Doe.',
      },
      {
        stage: "finalize",
        status: 422,
        error: "Upload refused",
        message: "The PDF is password-protected. Remove the password and try again.",
      },
      {
        stage: "finalize",
        status: 422,
        error: "Upload refused",
        message: "The PDF could not be read. It may be damaged.",
      },
      {
        stage: "finalize",
        status: 422,
        error: "Upload refused",
        message:
          "The PDF has 101 pages; the limit is 100 pages per file. Split it and upload the parts.",
      },
      {
        stage: "finalize",
        status: 422,
        error: "Upload refused",
        message: "The file arrived corrupt. Please try uploading it again.",
      },
      {
        stage: "start",
        status: 409,
        error: "Limit reached",
        message:
          "Your workspace has reached its limit of 20 documents. Delete a document to upload another.",
      },
      {
        stage: "start",
        status: 409,
        error: "Limit reached",
        message:
          "This file would take your workspace over its storage limit of 100 MB. Delete a document to make room.",
      },
      {
        stage: "finalize",
        status: 409,
        error: "Limit reached",
        message:
          "Your workspace has reached its limit of 20 documents. Delete a document to upload another.",
      },
      {
        stage: "start",
        status: 429,
        error: "Too many uploads",
        message: "You already have 5 uploads in progress. Wait for one to finish, then try again.",
      },
      {
        stage: "start",
        status: 429,
        error: "Too many uploads",
        message: "You have started too many uploads this hour. Try again in 12 minutes.",
      },
    ] as const;

    it.each(refusals)(
      "shows the reason on that file: $message",
      async ({ stage, status, error, message }) => {
        mockUploadApi();
        const refusal = () => HttpResponse.json({ error, message }, { status });
        server.use(
          stage === "start"
            ? http.post(`${API_URL}/uploads/init`, refusal)
            : http.post(`${API_URL}/uploads/${UPLOAD_ID}/finalize`, refusal),
        );

        await choose(pdfFile("report.pdf"));

        const row = (await screen.findByText("report.pdf")).closest("li");
        expect(row).not.toBeNull();
        expect(await within(row as HTMLElement).findByRole("alert")).toHaveTextContent(message);
        expect(screen.queryByText("Accepted")).not.toBeInTheDocument();
      },
    );
  });
});
