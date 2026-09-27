/**
 * The ingest calls fail in ways that look like something else: JSON sent to a
 * multipart endpoint is a 422 about a "missing field"; a hand-set Content-Type
 * drops the multipart boundary; the shared client's 20-second timeout kills a
 * video upload the server then finishes anyway. So these tests check the
 * *shape of the request*, not just that a call happened.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";

const post = vi.fn();
vi.mock("../api/client", () => ({ default: { post: (...a) => post(...a), get: vi.fn() } }));

import {
  TIMEOUT_MS,
  addFromUrl,
  addFromYoutube,
  pasteText,
  sortNewestFirst,
  uploadPdf,
  uploadResearchPaper,
  uploadVideo,
} from "./api";

beforeEach(() => {
  post.mockReset();
  post.mockResolvedValue({ data: {} });
});

const lastCall = () => post.mock.calls.at(-1);

describe("multipart, not JSON", () => {
  it("sends files as FormData under the field name the server expects", async () => {
    const file = new File(["%PDF-1.4"], "a.pdf");
    await uploadPdf(file);

    const [path, body] = lastCall();
    expect(path).toBe("/content/upload-pdf");
    expect(body).toBeInstanceOf(FormData);
    expect(body.get("file")).toBe(file);
  });

  it("does not set Content-Type by hand, which would drop the boundary", async () => {
    await uploadPdf(new File(["x"], "a.pdf"));
    const config = lastCall()[2];
    expect(config.headers?.["Content-Type"]).toBeUndefined();
    expect(config.headers?.["content-type"]).toBeUndefined();
  });

  it("sends pasted text as form fields, trimming only the title", async () => {
    await pasteText({ title: "  Induction  ", text: "  keep my spaces  " });
    const [path, body] = lastCall();
    expect(path).toBe("/content/paste-text");
    expect(body.get("title")).toBe("Induction");
    // The text is the document; whitespace inside it is not ours to alter.
    expect(body.get("text")).toBe("  keep my spaces  ");
  });

  it.each([
    ["web", addFromUrl, "/content/from-url"],
    ["youtube", addFromYoutube, "/content/from-youtube"],
  ])("sends a %s address as the `url` form field, trimmed", async (_n, fn, expectedPath) => {
    await fn("  https://example.com/x  ");
    const [path, body] = lastCall();
    expect(path).toBe(expectedPath);
    expect(body.get("url")).toBe("https://example.com/x");
  });

  it("uses the research-paper endpoint for research papers, not the PDF one", async () => {
    await uploadResearchPaper(new File(["x"], "p.pdf"));
    expect(lastCall()[0]).toBe("/content/upload-research-paper");
  });
});

describe("timeouts", () => {
  it("gives a video far longer than the shared client's 20 seconds", async () => {
    await uploadVideo(new File(["x"], "v.mp4"));
    const { timeout } = lastCall()[2];
    // Left at 20s, axios abandons the request while the server finishes
    // transcribing - the learner is told it failed and the document appears
    // in their library anyway.
    expect(timeout).toBe(TIMEOUT_MS.video);
    expect(timeout).toBeGreaterThan(20_000);
  });

  it("orders them by how long each kind of work can honestly take", () => {
    expect(TIMEOUT_MS.text).toBeLessThan(TIMEOUT_MS.pdf);
    expect(TIMEOUT_MS.pdf).toBeLessThan(TIMEOUT_MS.youtube);
    expect(TIMEOUT_MS.youtube).toBeLessThan(TIMEOUT_MS.video);
  });

  it("lets a caller override it", async () => {
    await uploadPdf(new File(["x"], "a.pdf"), { timeout: 5 });
    expect(lastCall()[2].timeout).toBe(5);
  });
});

describe("progress and cancellation", () => {
  it("reports whole-number percentages, capped at 100", async () => {
    const seen = [];
    await uploadPdf(new File(["x"], "a.pdf"), { onProgress: (p) => seen.push(p) });

    const { onUploadProgress } = lastCall()[2];
    onUploadProgress({ loaded: 1, total: 3 });
    onUploadProgress({ loaded: 3, total: 3 });
    onUploadProgress({ loaded: 5, total: 3 }); // some browsers overshoot
    expect(seen).toEqual([33, 100, 100]);
  });

  it("ignores progress events with no total instead of reporting NaN", async () => {
    const seen = [];
    await uploadPdf(new File(["x"], "a.pdf"), { onProgress: (p) => seen.push(p) });
    lastCall()[2].onUploadProgress({ loaded: 10, total: 0 });
    expect(seen).toEqual([]);
  });

  it("passes the abort signal through so Cancel actually cancels", async () => {
    const controller = new AbortController();
    await uploadPdf(new File(["x"], "a.pdf"), { signal: controller.signal });
    expect(lastCall()[2].signal).toBe(controller.signal);
  });
});

describe("ordering the library", () => {
  it("puts the newest document first", () => {
    const sorted = sortNewestFirst([
      { content_id: "old", created_at: "2026-01-01T00:00:00Z" },
      { content_id: "new", created_at: "2026-09-01T00:00:00Z" },
      { content_id: "mid", created_at: "2026-05-01T00:00:00Z" },
    ]);
    expect(sorted.map((d) => d.content_id)).toEqual(["new", "mid", "old"]);
  });

  it("sinks documents with no date instead of throwing", () => {
    const sorted = sortNewestFirst([
      { content_id: "undated" },
      { content_id: "dated", created_at: "2026-01-01T00:00:00Z" },
    ]);
    expect(sorted.map((d) => d.content_id)).toEqual(["dated", "undated"]);
  });

  it("does not mutate what it was given, and survives nothing", () => {
    const input = [{ content_id: "a", created_at: "2026-01-01T00:00:00Z" }];
    expect(sortNewestFirst(input)).not.toBe(input);
    expect(sortNewestFirst(undefined)).toEqual([]);
  });
});
