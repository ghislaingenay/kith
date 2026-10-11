import { describe, expect, it } from "vitest";

import { parseServerSentEvents } from "./parse_server_sent_events";

function streamOf(...chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
}

async function collect(stream: ReadableStream<Uint8Array>) {
  const events = [];
  for await (const event of parseServerSentEvents(stream)) events.push(event);
  return events;
}

describe("parseServerSentEvents", () => {
  it("yields each event's name and data in order", async () => {
    const events = await collect(
      streamOf('event: citations\ndata: {"passages":[]}\n\nevent: done\ndata: {}\n\n'),
    );
    expect(events).toEqual([
      { event: "citations", data: '{"passages":[]}' },
      { event: "done", data: "{}" },
    ]);
  });

  it("joins an event split across chunks, even inside a character", async () => {
    const bytes = new TextEncoder().encode('event: answer_delta\ndata: {"text":"é"}\n\n');
    const split = bytes.length - 6;
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(bytes.slice(0, split));
        controller.enqueue(bytes.slice(split));
        controller.close();
      },
    });

    expect(await collect(stream)).toEqual([
      { event: "answer_delta", data: '{"text":"é"}' },
    ]);
  });

  it("reads CRLF line endings", async () => {
    expect(await collect(streamOf("event: done\r\ndata: {}\r\n\r\n"))).toEqual([
      { event: "done", data: "{}" },
    ]);
  });

  it("drops an unfinished event at the end of the stream", async () => {
    expect(await collect(streamOf("event: done\ndata: {"))).toEqual([]);
  });
});
