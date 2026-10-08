import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { server } from "@/test/mocks/server";

import { SearchPanel } from "./search_panel";

vi.mock("react-pdf", () => import("@/test/stub_react_pdf"));

const navigation = vi.hoisted(() => ({
  url: "",
  push: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(navigation.url),
  usePathname: () => "/w/acme",
  useRouter: () => ({ push: navigation.push }),
}));

const API_URL = "http://localhost:8000/api/v1";
const TENANT_ID = "0b8e6f0e-6f6e-4c1c-9d55-4a0a4a3b1a10";

function apiResult(overrides = {}) {
  return {
    chunk_id: "c1",
    document_id: "d1",
    document_name: "report.pdf",
    document_status: "ready",
    page_number: 4,
    text: "Line one of the passage\nline two",
    highlights: ["the <mark>cat</mark> sat"],
    ...overrides,
  };
}

function mockSearch(results = [apiResult()], degraded = false) {
  const seen: { queries: string[]; tenantIds: (string | null)[] } = {
    queries: [],
    tenantIds: [],
  };
  server.use(
    http.post(`${API_URL}/search`, async ({ request }) => {
      seen.queries.push(((await request.json()) as { query: string }).query);
      seen.tenantIds.push(request.headers.get("x-tenant-id"));
      return HttpResponse.json({ degraded, results });
    }),
  );
  return seen;
}

function renderPanel(client = new QueryClient({ defaultOptions: { queries: { retry: false } } })) {
  render(
    <QueryClientProvider client={client}>
      <SearchPanel tenantId={TENANT_ID} />
    </QueryClientProvider>,
  );
  return client;
}

beforeEach(() => {
  navigation.url = "";
  navigation.push.mockReset();
});

describe("SearchPanel", () => {
  it("shows the placeholder and no Ask AI button or chips", () => {
    renderPanel();
    expect(screen.getByPlaceholderText("Search documents…")).toBeInTheDocument();
    expect(screen.queryByText(/ask ai/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("puts the Query in the URL on Enter", async () => {
    renderPanel();
    await userEvent.type(screen.getByRole("searchbox"), "cat food{Enter}");
    expect(navigation.push).toHaveBeenCalledWith("/w/acme?q=cat+food&type=search");
  });

  it("does nothing for an empty or whitespace Query", async () => {
    const seen = mockSearch();
    renderPanel();
    await userEvent.type(screen.getByRole("searchbox"), "   {Enter}");
    expect(navigation.push).not.toHaveBeenCalled();
    expect(seen.queries).toEqual([]);
  });

  it("runs the Search from the URL and pre-fills the box", async () => {
    navigation.url = "q=cat&type=search";
    const seen = mockSearch();
    renderPanel();

    expect(screen.getByRole("searchbox")).toHaveValue("cat");
    expect(await screen.findByText("report.pdf")).toBeInTheDocument();
    expect(seen.queries).toEqual(["cat"]);
    expect(seen.tenantIds).toEqual([TENANT_ID]);
  });

  it("ignores a q without type=search", () => {
    navigation.url = "q=cat";
    const seen = mockSearch();
    renderPanel();
    expect(seen.queries).toEqual([]);
  });

  it("lists Document name, page and highlighted words as elements", async () => {
    navigation.url = "q=cat&type=search";
    mockSearch();
    renderPanel();

    const row = (await screen.findByText("report.pdf")).closest("li")!;
    expect(row).toHaveTextContent("Page 4");
    expect(row.querySelector("mark")).toHaveTextContent("cat");
    expect(row).toHaveTextContent("the cat sat");
  });

  it("never injects HTML from a passage", async () => {
    navigation.url = "q=x&type=search";
    mockSearch([apiResult({ highlights: ["&lt;img src=x onerror=alert(1)&gt; <mark>x</mark>"] })]);
    renderPanel();

    const row = (await screen.findByText("report.pdf")).closest("li")!;
    expect(row.querySelector("img")).toBeNull();
    expect(row).toHaveTextContent("<img src=x onerror=alert(1)>");
  });

  it("shows the opening lines plain when nothing is highlighted", async () => {
    navigation.url = "q=one&type=search";
    mockSearch([apiResult({ highlights: [] })]);
    renderPanel();

    const row = (await screen.findByText("report.pdf")).closest("li")!;
    expect(row).toHaveTextContent("Line one of the passage");
    expect(row.querySelector("mark")).toBeNull();
  });

  it("notes quietly that only keyword matches are shown when degraded", async () => {
    navigation.url = "q=cat&type=search";
    mockSearch([apiResult()], true);
    renderPanel();
    expect(await screen.findByText("Showing keyword matches only")).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Search results" })).toBeInTheDocument();
  });

  it("shows no keyword-only note when the Search is not degraded", async () => {
    navigation.url = "q=cat&type=search";
    mockSearch();
    renderPanel();
    await screen.findByRole("list", { name: "Search results" });
    expect(screen.queryByText(/keyword matches only/i)).not.toBeInTheDocument();
  });

  it("opens the Document preview at the row's page and closes back to the results", async () => {
    navigation.url = "q=cat&type=search";
    const seen = mockSearch([
      apiResult({ chunk_id: "c0", document_id: "d0", document_name: "other.pdf", page_number: 1 }),
      apiResult({ page_number: 2 }),
    ]);
    server.use(
      http.get(`${API_URL}/documents/d1/file-url`, () =>
        HttpResponse.json({
          url: "http://localhost:9000/kith-dev/report.pdf?signature=abc",
          expires_in: 300,
        }),
      ),
    );
    renderPanel();

    await userEvent.click(await screen.findByRole("button", { name: /report\.pdf/ }));

    expect(await screen.findByRole("dialog", { name: "report.pdf" })).toBeInTheDocument();
    expect(await screen.findByText("PDF page 2")).toBeInTheDocument();

    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Search results" })).toBeInTheDocument();
    expect(seen.queries).toEqual(["cat"]);
    expect(navigation.push).not.toHaveBeenCalled();
  });

  it("shows skeleton rows while loading", async () => {
    navigation.url = "q=cat&type=search";
    server.use(http.post(`${API_URL}/search`, () => new Promise(() => {})));
    renderPanel();
    expect(await screen.findByRole("status", { name: "Searching" })).toBeInTheDocument();
  });

  it("says when no passage matches", async () => {
    navigation.url = "q=zebra&type=search";
    mockSearch([]);
    renderPanel();
    expect(await screen.findByText("No passages match “zebra”.")).toBeInTheDocument();
  });

  it("offers a Retry on 503 that keeps the Query", async () => {
    navigation.url = "q=cat&type=search";
    let calls = 0;
    server.use(
      http.post(`${API_URL}/search`, () =>
        ++calls === 1
          ? HttpResponse.json({ message: "down" }, { status: 503 })
          : HttpResponse.json({ degraded: false, results: [apiResult()] }),
      ),
    );
    renderPanel();

    expect(await screen.findByText("Search is unavailable right now.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("report.pdf")).toBeInTheDocument();
    expect(screen.getByRole("searchbox")).toHaveValue("cat");
  });

  it("explains a 429", async () => {
    navigation.url = "q=cat&type=search";
    server.use(
      http.post(`${API_URL}/search`, () =>
        HttpResponse.json({ message: "slow down" }, { status: 429 }),
      ),
    );
    renderPanel();
    expect(await screen.findByText(/searching too fast/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
  });

  it("serves a repeated Query from the cache, per Tenant", async () => {
    navigation.url = "q=cat&type=search";
    const seen = mockSearch();
    const client = renderPanel();
    await screen.findByText("report.pdf");

    expect(client.getQueryData(["search", TENANT_ID, "cat"])).toBeDefined();
    expect(seen.queries).toHaveLength(1);
  });
});
