import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
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

const askFlags = vi.hoisted(() => ({ showSources: true, citationMarkers: true }));

vi.mock("@/config/env", async (importOriginal) => {
  const { env } = await importOriginal<typeof import("@/config/env")>();
  return {
    env: {
      ...env,
      get NEXT_PUBLIC_ASK_SHOW_SOURCES() {
        return askFlags.showSources;
      },
      get NEXT_PUBLIC_ASK_CITATION_MARKERS() {
        return askFlags.citationMarkers;
      },
    },
  };
});

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(navigation.url),
  usePathname: () => "/w/acme",
  useRouter: () => ({ push: navigation.push }),
}));

const API_URL = "http://localhost:8000/api/v1";
const TENANT_ID = "0b8e6f0e-6f6e-4c1c-9d55-4a0a4a3b1a10";
const NO_CREDITS_MESSAGE =
  "Acme has no credits left. Ask an Admin to request more. Search still works.";

function mockCreditBalance(overrides = {}) {
  server.use(
    http.get(`${API_URL}/credit-balance`, () =>
      HttpResponse.json({
        credits: 142,
        tokens: 142_310,
        is_low: false,
        is_exhausted: false,
        ...overrides,
      }),
    ),
  );
}

function mockExhaustedCreditBalance() {
  mockCreditBalance({ credits: -2, tokens: -1_500, is_low: true, is_exhausted: true });
}

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

function libraryDocument(id: string) {
  return {
    id,
    name: "report.pdf",
    size_bytes: 1024,
    uploader: "alice",
    created_at: "2024-01-01T00:00:00Z",
    ingestion_status: "ready",
    ingestion_stage: null,
    pages_extracted: null,
    page_count: 1,
  };
}

function mockLibrary(documents: object[] = [libraryDocument("d1")]) {
  server.use(http.get(`${API_URL}/documents`, () => HttpResponse.json(documents)));
}

function renderPanel(
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } }),
  canAsk = false,
) {
  render(
    <QueryClientProvider client={client}>
      <SearchPanel tenantId={TENANT_ID} tenantName="Acme" canAsk={canAsk} />
    </QueryClientProvider>,
  );
  return client;
}

function renderAskingPanel() {
  return renderPanel(undefined, true);
}

function citedPassage(overrides = {}) {
  return {
    n: 1,
    chunk_id: "c1",
    document_id: "d1",
    document_name: "contract.pdf",
    page_number: 7,
    text: "Payment is due within 30 days.",
    ...overrides,
  };
}

const DONE = {
  ask_id: "a1",
  status: "completed",
  credits_charged: 4,
  balance_credits: 138,
  reranked: true,
  degraded: false,
};

function serverSentEvent(event: string, data: object): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

/** Serves POST /asks as a stream the test writes to, one chunk at a time. */
function mockAskStream() {
  const encoder = new TextEncoder();
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  const stream = new ReadableStream<Uint8Array>({
    start(streamController) {
      controller = streamController;
    },
  });
  const seen: { queries: string[]; tenantIds: (string | null)[] } = {
    queries: [],
    tenantIds: [],
  };
  server.use(
    http.post(`${API_URL}/asks`, async ({ request }) => {
      seen.queries.push(((await request.json()) as { query: string }).query);
      seen.tenantIds.push(request.headers.get("x-tenant-id"));
      return new HttpResponse(stream, {
        headers: { "Content-Type": "text/event-stream" },
      });
    }),
  );
  return {
    seen,
    send: (event: string, data: object) =>
      controller.enqueue(encoder.encode(serverSentEvent(event, data))),
    end: () => controller.close(),
  };
}

function mockAsk(
  passages = [citedPassage()],
  deltas = ["Payment is due ", "in 30 days [1]."],
  done: object = DONE,
) {
  const body = [
    serverSentEvent("citations", { passages }),
    ...deltas.map((text) => serverSentEvent("answer_delta", { text })),
    serverSentEvent("done", done),
  ].join("");
  const seen = { queries: [] as string[] };
  server.use(
    http.post(`${API_URL}/asks`, async ({ request }) => {
      seen.queries.push(((await request.json()) as { query: string }).query);
      return new HttpResponse(body, { headers: { "Content-Type": "text/event-stream" } });
    }),
  );
  return seen;
}

/** Waits for the Answer to read `text`, markers included. */
async function expectAnswer(text: string) {
  await waitFor(() => expect(screen.getByLabelText("Answer")).toHaveTextContent(text));
}

/** Types the Query, clicks Ask AI and waits for the finished Answer. */
async function askAndFinish(query = "terms") {
  await userEvent.type(await screen.findByRole("searchbox"), query);
  await userEvent.click(screen.getByRole("button", { name: "Ask AI" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Ask AI" })).toBeEnabled());
  return screen.getByLabelText("Answer");
}

beforeEach(() => {
  mockLibrary();
  mockCreditBalance();
  navigation.url = "";
  navigation.push.mockReset();
  askFlags.showSources = true;
  askFlags.citationMarkers = true;
  // jsdom doesn't implement scrolling.
  Element.prototype.scrollIntoView = vi.fn();
});

describe("SearchPanel", () => {
  it("shows the placeholder and a Search button, and no Ask AI button to a Role that may not Ask", async () => {
    renderPanel();
    expect(await screen.findByPlaceholderText("Search documents…")).toBeInTheDocument();
    expect(screen.queryByText(/ask ai/i)).not.toBeInTheDocument();
    expect(screen.getAllByRole("button").map((b) => b.textContent)).toEqual(["Search"]);
  });

  it("shows an Ask AI button beside Search to a Role that may Ask", async () => {
    renderAskingPanel();
    await screen.findByRole("searchbox");
    expect(screen.getAllByRole("button").map((b) => b.textContent)).toEqual([
      "Search",
      "Ask AI",
    ]);
  });

  it("shows the workspace name and how many Documents there are to search before a Query", async () => {
    mockLibrary([libraryDocument("d1"), libraryDocument("d2"), libraryDocument("d3")]);
    renderPanel();
    expect(await screen.findByRole("heading", { level: 1, name: "Acme" })).toBeInTheDocument();
    expect(screen.getByText("Search 3 documents")).toBeInTheDocument();
  });

  it("drops the Document count hint once a Query runs", async () => {
    navigation.url = "q=cat&type=search";
    mockSearch();
    renderPanel();
    await screen.findByRole("list", { name: "Search results" });
    expect(screen.getByRole("heading", { level: 1, name: "Acme" })).toBeInTheDocument();
    expect(screen.queryByText("Search 1 document")).not.toBeInTheDocument();
  });

  it("runs the Search only when the Search button is clicked", async () => {
    renderPanel();
    await userEvent.type(await screen.findByRole("searchbox"), "cat food");
    expect(navigation.push).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(navigation.push).toHaveBeenCalledWith("/w/acme?q=cat+food&type=search");
  });

  it("hides the search box and points to the uploads when there are no Documents", async () => {
    mockLibrary([]);
    navigation.url = "q=cat&type=search";
    const seen = mockSearch();
    renderPanel();

    expect(await screen.findByRole("alert")).toHaveTextContent("No documents available");
    expect(screen.getByRole("link", { name: "Go to uploads" })).toHaveAttribute(
      "href",
      "/w/acme/uploads",
    );
    expect(screen.queryByRole("searchbox")).not.toBeInTheDocument();
    expect(seen.queries).toEqual([]);
  });

  it("puts the Query in the URL on Enter", async () => {
    renderPanel();
    await userEvent.type(await screen.findByRole("searchbox"), "cat food{Enter}");
    expect(navigation.push).toHaveBeenCalledWith("/w/acme?q=cat+food&type=search");
  });

  it("does nothing for an empty or whitespace Query", async () => {
    const seen = mockSearch();
    renderPanel();
    await userEvent.type(await screen.findByRole("searchbox"), "   {Enter}");
    expect(navigation.push).not.toHaveBeenCalled();
    expect(seen.queries).toEqual([]);
  });

  it("runs the Search from the URL and pre-fills the box", async () => {
    navigation.url = "q=cat&type=search";
    const seen = mockSearch();
    renderPanel();

    expect(await screen.findByText("report.pdf")).toBeInTheDocument();
    expect(screen.getByRole("searchbox")).toHaveValue("cat");
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

  it("says how many Documents it is searching while loading", async () => {
    navigation.url = "q=cat&type=search";
    server.use(http.post(`${API_URL}/search`, () => new Promise(() => {})));
    renderPanel();
    const loading = await screen.findByRole("status");
    expect(loading).toHaveTextContent("Searching 1 document…");
    expect(loading).toHaveAttribute("aria-live", "polite");
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

describe("SearchPanel's Ask", () => {
  it("streams the Answer, then shows its markers and Citations once it ends", async () => {
    const ask = mockAskStream();
    renderAskingPanel();
    await userEvent.type(await screen.findByRole("searchbox"), "payment terms");
    await userEvent.click(screen.getByRole("button", { name: "Ask AI" }));

    ask.send("citations", {
      passages: [citedPassage(), citedPassage({ n: 2, chunk_id: "c2", page_number: 9 })],
    });
    expect(await screen.findByLabelText("Answer")).toBeEmptyDOMElement();
    expect(screen.getByRole("status", { name: "Finding passages" })).toBeInTheDocument();

    ask.send("answer_delta", { text: "Payment is due " });
    await expectAnswer("Payment is due");

    ask.send("answer_delta", { text: "in 30 days [1]." });
    await expectAnswer("Payment is due in 30 days.");

    ask.send("done", DONE);
    ask.end();
    const citations = await screen.findByRole("list", { name: "Citations" });
    expect(within(citations).getAllByRole("listitem")).toHaveLength(1);
    expect(within(citations).getAllByRole("listitem")[0]).toHaveTextContent(
      "contract.pdfPage 7Payment is due within 30 days.",
    );
    await expectAnswer("Payment is due in 30 days [1].");
    expect(ask.seen.queries).toEqual(["payment terms"]);
    expect(ask.seen.tenantIds).toEqual([TENANT_ID]);
  });

  it("disables the Ask AI button while the Answer streams", async () => {
    const ask = mockAskStream();
    renderAskingPanel();
    await userEvent.type(await screen.findByRole("searchbox"), "payment terms");
    const button = screen.getByRole("button", { name: "Ask AI" });
    await userEvent.click(button);

    expect(button).toBeDisabled();
    ask.send("citations", { passages: [citedPassage()] });
    ask.send("answer_delta", { text: "Partly" });
    await screen.findByText("Partly");
    expect(button).toBeDisabled();

    ask.send("done", DONE);
    ask.end();
    await waitFor(() => expect(button).toBeEnabled());
  });

  it("shows passage and Answer text containing HTML as text", async () => {
    mockAsk(
      [citedPassage({ text: "<img src=x onerror=alert(1)> terms" })],
      ["<b>bold</b> answer [1]"],
    );
    renderAskingPanel();
    await userEvent.type(await screen.findByRole("searchbox"), "terms");
    await userEvent.click(screen.getByRole("button", { name: "Ask AI" }));

    const citations = await screen.findByRole("list", { name: "Citations" });
    expect(citations.querySelector("img")).toBeNull();
    expect(citations).toHaveTextContent("<img src=x onerror=alert(1)> terms");
    const answer = await screen.findByLabelText("Answer");
    expect(answer).toHaveTextContent("<b>bold</b> answer [1]");
    expect(answer.querySelector("b")).toBeNull();
  });

  it("refreshes the sidebar's Credit Balance after the Ask", async () => {
    mockAsk();
    const client = renderAskingPanel();
    await waitFor(() =>
      expect(client.getQueryData(["credit-balance", TENANT_ID])).toMatchObject({ credits: 142 }),
    );
    mockCreditBalance({ credits: 138, tokens: 138_310 });
    await userEvent.type(await screen.findByRole("searchbox"), "terms");
    await userEvent.click(screen.getByRole("button", { name: "Ask AI" }));

    await expectAnswer("Payment is due in 30 days [1].");
    await waitFor(() =>
      expect(client.getQueryData(["credit-balance", TENANT_ID])).toMatchObject({ credits: 138 }),
    );
  });

  it("never starts an Ask from the URL", async () => {
    navigation.url = "q=cat&type=search";
    mockSearch();
    const seen = mockAsk();
    renderAskingPanel();

    expect(await screen.findByText("report.pdf")).toBeInTheDocument();
    expect(seen.queries).toEqual([]);
  });

  it("does nothing for a blank Query", async () => {
    const seen = mockAsk();
    renderAskingPanel();
    await userEvent.type(await screen.findByRole("searchbox"), "   ");
    await userEvent.click(screen.getByRole("button", { name: "Ask AI" }));
    expect(seen.queries).toEqual([]);
  });

  it("says the Answer failed and cost nothing when the stream ends failed", async () => {
    mockAsk([citedPassage()], [], { ...DONE, status: "failed", credits_charged: 0 });
    renderAskingPanel();
    await userEvent.type(await screen.findByRole("searchbox"), "terms");
    await userEvent.click(screen.getByRole("button", { name: "Ask AI" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The answer failed. No credits were used. Try again.",
    );
    expect(screen.getByRole("list", { name: "Citations" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ask AI" })).toBeEnabled();
  });

  it("says a cut-off Answer was interrupted and what it cost", async () => {
    mockAsk([citedPassage()], ["Payment is due"], {
      ...DONE,
      status: "cut_off",
      credits_charged: 9,
    });
    renderAskingPanel();
    await userEvent.type(await screen.findByRole("searchbox"), "terms");
    await userEvent.click(screen.getByRole("button", { name: "Ask AI" }));

    expect(await screen.findByText("Payment is due")).toBeInTheDocument();
    expect(
      await screen.findByText(
        "The answer was interrupted. 9 credits were used for what the AI had already read and written.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("says no passages match when the Ask found none", async () => {
    mockAsk([], [], { ...DONE, status: "no_chunks", credits_charged: 0 });
    renderAskingPanel();
    await userEvent.type(await screen.findByRole("searchbox"), "terms");
    await userEvent.click(screen.getByRole("button", { name: "Ask AI" }));

    expect(
      await screen.findByText("No passages in your Documents match this."),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("Answer")).not.toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Citations" })).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows no failure or interruption note for a completed Answer", async () => {
    mockAsk();
    renderAskingPanel();
    await userEvent.type(await screen.findByRole("searchbox"), "terms");
    await userEvent.click(screen.getByRole("button", { name: "Ask AI" }));

    await expectAnswer("Payment is due in 30 days [1].");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByText(/interrupted/)).not.toBeInTheDocument();
  });

  it("explains an Ask refused because Answers are unavailable", async () => {
    server.use(
      http.post(`${API_URL}/asks`, () =>
        HttpResponse.json({ message: "down" }, { status: 503 }),
      ),
    );
    renderAskingPanel();
    await userEvent.type(await screen.findByRole("searchbox"), "terms");
    await userEvent.click(screen.getByRole("button", { name: "Ask AI" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Answers are unavailable right now.",
    );
    expect(screen.getByRole("button", { name: "Ask AI" })).toBeEnabled();
  });

  it("explains an Ask refused for asking too fast", async () => {
    server.use(
      http.post(`${API_URL}/asks`, () =>
        HttpResponse.json({ message: "slow down" }, { status: 429 }),
      ),
    );
    renderAskingPanel();
    await userEvent.type(await screen.findByRole("searchbox"), "terms");
    await userEvent.click(screen.getByRole("button", { name: "Ask AI" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/asking too fast/i);
  });

  it("moves to the top-bar layout while an Ask is shown", async () => {
    mockAsk();
    renderAskingPanel();
    expect(await screen.findByText("Search 1 document")).toBeInTheDocument();
    await userEvent.type(screen.getByRole("searchbox"), "terms");
    await userEvent.click(screen.getByRole("button", { name: "Ask AI" }));
    await expectAnswer("Payment is due in 30 days [1].");
    expect(screen.queryByText("Search 1 document")).not.toBeInTheDocument();
    // The box kept the Query through the move.
    expect(screen.getByRole("searchbox")).toHaveValue("terms");
  });

  it("leaves the Ask's Answer when a Search runs", async () => {
    mockAsk();
    renderAskingPanel();
    await userEvent.type(await screen.findByRole("searchbox"), "terms");
    await userEvent.click(screen.getByRole("button", { name: "Ask AI" }));
    await expectAnswer("Payment is due in 30 days [1].");

    await userEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(navigation.push).toHaveBeenCalledWith("/w/acme?q=terms&type=search");
    expect(screen.queryByLabelText("Answer")).not.toBeInTheDocument();
  });
});

describe("SearchPanel's Ask with no credits left", () => {
  it("disables Ask AI and says why and who to ask", async () => {
    mockExhaustedCreditBalance();
    renderAskingPanel();

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Ask AI" })).toBeDisabled(),
    );
    expect(screen.getByRole("button", { name: "Ask AI" })).toHaveAccessibleDescription(
      NO_CREDITS_MESSAGE,
    );
    expect(screen.getByText(NO_CREDITS_MESSAGE)).toBeInTheDocument();
  });

  it("still runs a Search", async () => {
    mockExhaustedCreditBalance();
    navigation.url = "q=cat&type=search";
    mockSearch();
    renderAskingPanel();

    expect(await screen.findByText("report.pdf")).toBeInTheDocument();
    expect(await screen.findByText(NO_CREDITS_MESSAGE)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(navigation.push).toHaveBeenCalledWith("/w/acme?q=cat&type=search");
  });

  it("keeps Ask AI enabled with no message while credits are left", async () => {
    renderAskingPanel();

    expect(await screen.findByRole("button", { name: "Ask AI" })).toBeEnabled();
    expect(screen.queryByText(NO_CREDITS_MESSAGE)).not.toBeInTheDocument();
  });

  it("explains an Ask refused because the credits ran out meanwhile, then disables Ask AI", async () => {
    server.use(
      http.post(`${API_URL}/asks`, () => {
        mockExhaustedCreditBalance();
        return HttpResponse.json(
          {
            type: "credits-exhausted",
            title: "No credits left",
            status: 402,
            detail: "The Credit Balance is used up. Ask an Admin to get more Credits.",
          },
          { status: 402, headers: { "Content-Type": "application/problem+json" } },
        );
      }),
    );
    renderAskingPanel();
    await userEvent.type(await screen.findByRole("searchbox"), "terms");
    await userEvent.click(screen.getByRole("button", { name: "Ask AI" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("No credits left.");
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Ask AI" })).toBeDisabled(),
    );
  });
});

describe("SearchPanel's Ask citations", () => {
  const TWO_SOURCES = [
    citedPassage(),
    citedPassage({ n: 2, chunk_id: "c2", document_id: "d2", document_name: "terms.pdf", page_number: 2 }),
  ];

  it("links a marker to its Citation card, which opens the Document at its page", async () => {
    mockAsk(TWO_SOURCES, ["Payment is due in 30 days [2]."]);
    server.use(
      http.get(`${API_URL}/documents/d2/file-url`, () =>
        HttpResponse.json({
          url: "http://localhost:9000/kith-dev/terms.pdf?signature=abc",
          expires_in: 300,
        }),
      ),
    );
    renderAskingPanel();
    const answer = await askAndFinish();

    await userEvent.click(within(answer).getByRole("link", { name: "Citation 1" }));
    const card = screen.getByRole("button", { name: /terms\.pdf/ });
    expect(Element.prototype.scrollIntoView).toHaveBeenCalledTimes(1);
    expect(vi.mocked(Element.prototype.scrollIntoView).mock.contexts[0]).toBe(card);
    expect(card).toHaveFocus();
    expect(navigation.push).not.toHaveBeenCalled();

    await userEvent.click(card);
    expect(await screen.findByRole("dialog", { name: "terms.pdf" })).toBeInTheDocument();
    expect(await screen.findByText("PDF page 2")).toBeInTheDocument();
  });

  it("shows only the Citations the finished Answer marks, renumbered from 1", async () => {
    const ask = mockAskStream();
    renderAskingPanel();
    await userEvent.type(await screen.findByRole("searchbox"), "terms");
    await userEvent.click(screen.getByRole("button", { name: "Ask AI" }));

    ask.send("citations", { passages: TWO_SOURCES });
    ask.send("answer_delta", { text: "Due in 30 days [2]." });
    // Not yet: the Answer may still mark the first one.
    await expectAnswer("Due in 30 days.");
    expect(screen.getByRole("status", { name: "Finding passages" })).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Citations" })).not.toBeInTheDocument();

    ask.send("done", DONE);
    ask.end();
    const citations = await screen.findByRole("list", { name: "Citations" });
    expect(within(citations).getAllByRole("listitem")).toHaveLength(1);
    expect(screen.queryByRole("status", { name: "Finding passages" })).not.toBeInTheDocument();
    const answer = screen.getByLabelText("Answer");
    expect(answer).toHaveTextContent("Due in 30 days [1].");
    await userEvent.click(within(answer).getByRole("link", { name: "Citation 1" }));
    const card = screen.getByRole("button", { name: /terms\.pdf/ });
    expect(card).toHaveTextContent("[1]");
    expect(card).toHaveFocus();
  });

  it("removes the markers when they are turned off, and still lists the Citations", async () => {
    askFlags.citationMarkers = false;
    mockAsk(TWO_SOURCES, ["Due in 30 days [1], or 60 [2][7]."]);
    renderAskingPanel();
    const answer = await askAndFinish();

    expect(answer).toHaveTextContent("Due in 30 days, or 60.");
    expect(within(answer).queryByRole("link")).not.toBeInTheDocument();
    expect(
      within(screen.getByRole("list", { name: "Citations" })).getAllByRole("listitem"),
    ).toHaveLength(2);
  });

  it("shows no Citations and no markers when sources are turned off", async () => {
    askFlags.showSources = false;
    mockAsk(TWO_SOURCES, ["Due in 30 days [1]."]);
    renderAskingPanel();
    const answer = await askAndFinish();

    expect(answer).toHaveTextContent("Due in 30 days.");
    expect(within(answer).queryByRole("link")).not.toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Citations" })).not.toBeInTheDocument();
  });

  it("shows no Citations placeholder while streaming when sources are turned off", async () => {
    askFlags.showSources = false;
    const ask = mockAskStream();
    renderAskingPanel();
    await userEvent.type(await screen.findByRole("searchbox"), "terms");
    await userEvent.click(screen.getByRole("button", { name: "Ask AI" }));

    expect(screen.getByRole("button", { name: "Ask AI" })).toBeDisabled();
    expect(screen.queryByRole("status", { name: "Finding passages" })).not.toBeInTheDocument();

    ask.send("citations", { passages: TWO_SOURCES });
    ask.send("answer_delta", { text: "Due in 30 days [1]." });
    ask.send("done", DONE);
    ask.end();
    await expectAnswer("Due in 30 days.");
  });

  it("shows a marker with no Citation as plain text", async () => {
    mockAsk(TWO_SOURCES, ["Due [1], or later [7]."]);
    renderAskingPanel();
    const answer = await askAndFinish();

    expect(answer).toHaveTextContent("Due [1], or later [7].");
    expect(within(answer).getAllByRole("link")).toHaveLength(1);
    expect(within(answer).getByRole("link", { name: "Citation 1" })).toBeInTheDocument();
  });
});
