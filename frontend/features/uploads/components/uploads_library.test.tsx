import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it, vi } from "vitest";

import { server } from "@/test/mocks/server";
import { renderWithProviders } from "@/test/render_with_providers";

import { UploadsLibrary } from "./uploads_library";

const API_URL = "http://localhost:8000/api/v1";
const TENANT_ID = "0b8e6f0e-6f6e-4c1c-9d55-4a0a4a3b1a10";

type ApiDocument = {
  id: string;
  name: string;
  size_bytes: number;
  uploader: string;
  created_at: string;
  ingestion_status: string;
  ingestion_stage: string | null;
  pages_extracted: number | null;
  page_count: number;
};

function apiDocument(overrides: Partial<ApiDocument> = {}): ApiDocument {
  return {
    id: "9c1d2e3f-4a5b-4c6d-8e7f-0a1b2c3d4e5f",
    name: "report.pdf",
    size_bytes: 2048,
    uploader: "Jane Doe",
    created_at: "2026-09-01T12:00:00Z",
    ingestion_status: "ready",
    ingestion_stage: null,
    pages_extracted: null,
    page_count: 3,
    ...overrides,
  };
}

function mockLibraryApi(
  documents: ApiDocument[],
  summary = { in_progress: 0, failed: 0 },
) {
  const seen: { tenantIds: (string | null)[] } = { tenantIds: [] };
  server.use(
    http.get(`${API_URL}/documents`, ({ request }) => {
      seen.tenantIds.push(request.headers.get("x-tenant-id"));
      return HttpResponse.json(documents);
    }),
    http.get(`${API_URL}/documents/summary`, () => HttpResponse.json(summary)),
  );
  return seen;
}

function renderLibrary() {
  renderWithProviders(<UploadsLibrary tenantId={TENANT_ID} />);
}

describe("UploadsLibrary", () => {
  it("lists each Document with its name, size, uploader, date and status", async () => {
    const seen = mockLibraryApi([apiDocument()]);

    renderLibrary();

    const row = (await screen.findByText("report.pdf")).closest("tr")!;
    for (const header of ["Name", "Size", "Uploaded By", "Date", "Status"]) {
      expect(
        screen.getByRole("columnheader", { name: header }),
      ).toBeInTheDocument();
    }
    expect(within(row).getByText("2.0 KB")).toBeInTheDocument();
    expect(within(row).getByText("Jane Doe")).toBeInTheDocument();
    expect(within(row).getByText("Sep 1, 2026")).toBeInTheDocument();
    expect(within(row).getByText("Ready")).toBeInTheDocument();
    expect(seen.tenantIds).toEqual([TENANT_ID]);
  });

  it("does not show the removed Type and Linked Page columns", async () => {
    mockLibraryApi([apiDocument()]);

    renderLibrary();

    await screen.findByText("report.pdf");
    expect(
      screen.queryByRole("columnheader", { name: "Type" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("columnheader", { name: "Linked Page" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/PDF only/i)).not.toBeInTheDocument();
  });

  it("shows the Stage under the status and the page progress while a Document is being read", async () => {
    mockLibraryApi(
      [
        apiDocument({
          ingestion_status: "processing",
          ingestion_stage: "extracting",
          pages_extracted: 2,
          page_count: 7,
        }),
      ],
      { in_progress: 1, failed: 0 },
    );

    renderLibrary();

    const row = (await screen.findByText("report.pdf")).closest("tr")!;
    expect(within(row).getByText("Processing")).toBeInTheDocument();
    expect(within(row).getByText("Extracting")).toBeInTheDocument();
    expect(within(row).getByText("2 of 7 pages")).toBeInTheDocument();
  });

  it("hides the Stage and the page progress when the worker has not written them", async () => {
    mockLibraryApi(
      [apiDocument({ ingestion_status: "uploaded" })],
      { in_progress: 1, failed: 0 },
    );

    renderLibrary();

    const row = (await screen.findByText("report.pdf")).closest("tr")!;
    expect(within(row).getByText("Uploaded")).toBeInTheDocument();
    expect(within(row).queryByText(/extracting|chunking|embedding|indexing/i))
      .not.toBeInTheDocument();
    expect(within(row).queryByText(/pages/)).not.toBeInTheDocument();
  });

  it("warns how many files are still processing and that answers may be incomplete", async () => {
    mockLibraryApi([apiDocument({ ingestion_status: "processing" })], {
      in_progress: 2,
      failed: 0,
    });

    renderLibrary();

    const banner = await screen.findByRole("status");
    expect(banner).toHaveTextContent(
      "2 files are still processing. Answers may be incomplete for the newest ones.",
    );
    expect(banner).not.toHaveTextContent(/failed/i);
  });

  it("says 'file' for a single file still processing", async () => {
    mockLibraryApi([apiDocument({ ingestion_status: "processing" })], {
      in_progress: 1,
      failed: 0,
    });

    renderLibrary();

    expect(await screen.findByRole("status")).toHaveTextContent(
      "1 file is still processing.",
    );
  });

  it("also mentions failed Documents when there are any", async () => {
    mockLibraryApi([apiDocument({ ingestion_status: "processing" })], {
      in_progress: 2,
      failed: 1,
    });

    renderLibrary();

    expect(await screen.findByRole("status")).toHaveTextContent(
      "1 file failed to process.",
    );
  });

  it("shows the failed count even when nothing is still processing", async () => {
    mockLibraryApi([apiDocument({ ingestion_status: "failed" })], {
      in_progress: 0,
      failed: 2,
    });

    renderLibrary();

    const banner = await screen.findByRole("status");
    expect(banner).toHaveTextContent("2 files failed to process.");
    expect(banner).not.toHaveTextContent(/still processing/);
  });

  it("shows no banner when nothing is processing or failed", async () => {
    mockLibraryApi([apiDocument()]);

    renderLibrary();

    await screen.findByText("report.pdf");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("keeps refreshing while a Document is processing and stops showing it as processing once it is ready", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      let polls = 0;
      server.use(
        http.get(`${API_URL}/documents`, () => {
          polls += 1;
          return HttpResponse.json([
            apiDocument({
              ingestion_status: polls === 1 ? "processing" : "ready",
            }),
          ]);
        }),
        http.get(`${API_URL}/documents/summary`, () =>
          HttpResponse.json({ in_progress: polls <= 1 ? 1 : 0, failed: 0 }),
        ),
      );

      renderLibrary();
      expect(await screen.findByText("Processing")).toBeInTheDocument();
      expect(await screen.findByRole("status")).toBeInTheDocument();

      await vi.advanceTimersByTimeAsync(5000);

      expect(await screen.findByText("Ready")).toBeInTheDocument();
      expect(screen.queryByText("Processing")).not.toBeInTheDocument();
      await waitFor(() =>
        expect(screen.queryByRole("status")).not.toBeInTheDocument(),
      );
    } finally {
      vi.useRealTimers();
    }
  });

  it("shows an empty state when the Tenant has no Documents", async () => {
    mockLibraryApi([]);

    renderLibrary();

    expect(await screen.findByText("No documents yet")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("says so when the library cannot be loaded", async () => {
    server.use(
      http.get(`${API_URL}/documents`, () =>
        HttpResponse.json({ message: "nope" }, { status: 500 }),
      ),
      http.get(`${API_URL}/documents/summary`, () =>
        HttpResponse.json({ in_progress: 0, failed: 0 }),
      ),
    );

    renderLibrary();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "nope",
    );
  });

  describe("deleting", () => {
    const OWN_ID = "11111111-1111-4111-8111-111111111111";
    const THEIRS_ID = "22222222-2222-4222-8222-222222222222";

    /** The API's library, where each id in `forbidden` answers 403 and every
     * other delete succeeds and drops the Document from the list. */
    function mockDeletingApi(documents: ApiDocument[], forbidden: string[]) {
      let remaining = documents;
      const seen: { deleted: string[]; tenantIds: (string | null)[] } = {
        deleted: [],
        tenantIds: [],
      };
      server.use(
        http.get(`${API_URL}/documents`, () => HttpResponse.json(remaining)),
        http.get(`${API_URL}/documents/summary`, () =>
          HttpResponse.json({ in_progress: 0, failed: 0 }),
        ),
        http.delete(`${API_URL}/documents/:id`, ({ params, request }) => {
          const id = params.id as string;
          seen.deleted.push(id);
          seen.tenantIds.push(request.headers.get("x-tenant-id"));
          if (forbidden.includes(id)) {
            return HttpResponse.json(
              { error: "Forbidden", message: "Not permitted." },
              { status: 403 },
            );
          }
          remaining = remaining.filter((document) => document.id !== id);
          return new HttpResponse(null, { status: 204 });
        }),
      );
      return seen;
    }

    it("deletes the selected Documents it may and lists the ones it was refused", async () => {
      const seen = mockDeletingApi(
        [
          apiDocument({ id: OWN_ID, name: "mine.pdf" }),
          apiDocument({ id: THEIRS_ID, name: "theirs.pdf", uploader: "Sam" }),
        ],
        [THEIRS_ID],
      );
      const user = userEvent.setup();
      renderLibrary();
      await screen.findByText("mine.pdf");

      await user.click(screen.getByRole("checkbox", { name: "Select mine.pdf" }));
      await user.click(screen.getByRole("checkbox", { name: "Select theirs.pdf" }));
      await user.click(screen.getByRole("button", { name: "Delete selected (2)" }));
      await user.click(await screen.findByRole("button", { name: "Delete" }));

      const alert = await screen.findByRole("alert");
      expect(alert).toHaveTextContent("theirs.pdf");
      expect(alert).toHaveTextContent("You do not have permission to delete this document.");
      expect(alert).not.toHaveTextContent("mine.pdf");
      const table = screen.getByRole("table");
      expect(within(table).queryByText("mine.pdf")).not.toBeInTheDocument();
      expect(within(table).getByText("theirs.pdf")).toBeInTheDocument();
      expect([...seen.deleted].sort()).toEqual([OWN_ID, THEIRS_ID]);
      expect(seen.tenantIds).toEqual([TENANT_ID, TENANT_ID]);
    });

    it("deletes a single selected Document and reports no problem", async () => {
      const seen = mockDeletingApi(
        [
          apiDocument({ id: OWN_ID, name: "mine.pdf" }),
          apiDocument({ id: THEIRS_ID, name: "theirs.pdf" }),
        ],
        [],
      );
      const user = userEvent.setup();
      renderLibrary();
      await screen.findByText("mine.pdf");

      await user.click(screen.getByRole("checkbox", { name: "Select mine.pdf" }));
      await user.click(screen.getByRole("button", { name: "Delete selected (1)" }));
      await user.click(await screen.findByRole("button", { name: "Delete" }));

      await waitFor(() =>
        expect(screen.queryByText("mine.pdf")).not.toBeInTheDocument(),
      );
      expect(screen.getByText("theirs.pdf")).toBeInTheDocument();
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
      expect(seen.deleted).toEqual([OWN_ID]);
    });

    it("asks for confirmation before deleting, and keeps the Document if cancelled", async () => {
      const seen = mockDeletingApi(
        [apiDocument({ id: OWN_ID, name: "mine.pdf" })],
        [],
      );
      const user = userEvent.setup();
      renderLibrary();
      await screen.findByText("mine.pdf");

      await user.click(screen.getByRole("checkbox", { name: "Select mine.pdf" }));
      await user.click(screen.getByRole("button", { name: "Delete selected (1)" }));

      expect(await screen.findByText("Delete this document?")).toBeInTheDocument();
      await user.click(screen.getByRole("button", { name: "Cancel" }));

      expect(screen.queryByText("Delete this document?")).not.toBeInTheDocument();
      expect(screen.getByText("mine.pdf")).toBeInTheDocument();
      expect(seen.deleted).toEqual([]);
    });

    it("cannot delete until something is selected", async () => {
      mockDeletingApi([apiDocument({ id: OWN_ID, name: "mine.pdf" })], []);
      renderLibrary();
      await screen.findByText("mine.pdf");

      expect(
        screen.getByRole("button", { name: "Delete selected (0)" }),
      ).toBeDisabled();
    });
  });
});
