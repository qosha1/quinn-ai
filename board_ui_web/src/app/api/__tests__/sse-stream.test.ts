import { describe, it, expect } from "vitest";

// This module does not exist yet — tests must fail with a module-not-found error.
// Once GET /api/messages/stream/route is implemented these should pass.

describe("GET /api/messages/stream", () => {
  it("returns 200 with text/event-stream content-type", async () => {
    const { GET } = await import("@/app/api/messages/stream/route");
    const request = new Request("http://localhost/api/messages/stream");
    const response = await GET(request);
    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toContain("text/event-stream");
  });

  it("stream response is a ReadableStream", async () => {
    const { GET } = await import("@/app/api/messages/stream/route");
    const request = new Request("http://localhost/api/messages/stream");
    const response = await GET(request);
    expect(response.body).toBeInstanceOf(ReadableStream);
  });

  it("stream emits connected event", async () => {
    const { GET } = await import("@/app/api/messages/stream/route");
    const request = new Request("http://localhost/api/messages/stream");
    const response = await GET(request);
    const reader = response.body!.getReader();
    const decoder = new TextDecoder();
    let text = "";
    // Read up to first chunk
    const { value } = await reader.read();
    if (value) {
      text = decoder.decode(value);
    }
    reader.cancel();
    expect(text).toContain("connected");
  });
});
