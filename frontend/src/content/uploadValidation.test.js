import { describe, expect, it } from "vitest";

import {
  MAX_PDF_BYTES,
  MAX_TEXT_CHARS,
  MAX_VIDEO_BYTES,
  MIN_TEXT_CHARS,
  describeUploadError,
  validatePastedText,
  validatePdfFile,
  validateTitle,
  validateVideoFile,
  validateWebUrl,
  validateYoutubeUrl,
} from "./uploadValidation";

const fileOf = (name, size) => ({ name, size });

describe("the limits mirror the backend", () => {
  it("matches backend/app/content/validation.py", () => {
    // If validation.py changes a limit, this is the reminder to change the
    // client. A client that allows more than the server wastes a long upload;
    // one that allows less refuses a file the server would have accepted.
    expect(MAX_PDF_BYTES).toBe(25 * 1024 * 1024);
    expect(MAX_VIDEO_BYTES).toBe(200 * 1024 * 1024);
    expect(MAX_TEXT_CHARS).toBe(500_000);
    expect(MIN_TEXT_CHARS).toBe(50);
  });
});

describe("PDF files", () => {
  it("accepts a normal PDF, whatever the case of the extension", () => {
    expect(validatePdfFile(fileOf("report.pdf", 1000))).toBeNull();
    expect(validatePdfFile(fileOf("REPORT.PDF", 1000))).toBeNull();
  });

  it("accepts a file exactly at the limit and refuses one byte over", () => {
    expect(validatePdfFile(fileOf("a.pdf", MAX_PDF_BYTES))).toBeNull();
    expect(validatePdfFile(fileOf("a.pdf", MAX_PDF_BYTES + 1))).toMatch(/limit is 25/i);
  });

  it("refuses the wrong kind of file before sending it", () => {
    expect(validatePdfFile(fileOf("notes.docx", 1000))).toMatch(/PDF/);
    expect(validatePdfFile(fileOf("noextension", 1000))).toBeTruthy();
  });

  it("says an empty file is empty, rather than blaming its size", () => {
    expect(validatePdfFile(fileOf("a.pdf", 0))).toMatch(/empty/i);
  });

  it("asks for a file when there is none", () => {
    expect(validatePdfFile(null)).toBeTruthy();
  });
});

describe("video files", () => {
  it.each(["a.mp4", "a.MOV", "a.webm", "a.mkv", "a.avi", "a.m4v"])("accepts %s", (name) => {
    expect(validateVideoFile(fileOf(name, 1000))).toBeNull();
  });

  it("refuses a PDF picked in the video tab", () => {
    expect(validateVideoFile(fileOf("a.pdf", 1000))).toBeTruthy();
  });

  it("refuses over 200 MB with the size in the message", () => {
    expect(validateVideoFile(fileOf("a.mp4", MAX_VIDEO_BYTES + 1))).toMatch(/200/);
  });
});

describe("pasted text", () => {
  it("counts the way the server does - after trimming", () => {
    const padded = " ".repeat(200) + "x".repeat(MIN_TEXT_CHARS - 1) + " ".repeat(200);
    expect(validatePastedText(padded)).toMatch(/at least/i);
    expect(validatePastedText("x".repeat(MIN_TEXT_CHARS))).toBeNull();
  });

  it("enforces the upper limit", () => {
    expect(validatePastedText("x".repeat(MAX_TEXT_CHARS))).toBeNull();
    expect(validatePastedText("x".repeat(MAX_TEXT_CHARS + 1))).toMatch(/limit/i);
  });

  it("asks for text when the box is empty", () => {
    expect(validatePastedText("")).toBeTruthy();
    expect(validatePastedText(undefined)).toBeTruthy();
  });

  it("needs a title", () => {
    expect(validateTitle("Induction")).toBeNull();
    expect(validateTitle("   ")).toBeTruthy();
    expect(validateTitle("x".repeat(201))).toBeTruthy();
  });
});

describe("web addresses", () => {
  it("accepts http and https", () => {
    expect(validateWebUrl("https://example.com/a?b=1")).toBeNull();
    expect(validateWebUrl("http://example.com")).toBeNull();
  });

  it("catches the common mistakes with advice, not just a refusal", () => {
    expect(validateWebUrl("example.com")).toMatch(/https:\/\//);
    expect(validateWebUrl("not a url")).toBeTruthy();
    expect(validateWebUrl("")).toBeTruthy();
  });

  it("refuses schemes that are not web addresses", () => {
    expect(validateWebUrl("javascript:alert(1)")).toBeTruthy();
    expect(validateWebUrl("file:///etc/passwd")).toBeTruthy();
    expect(validateWebUrl("ftp://example.com")).toBeTruthy();
  });
});

describe("YouTube addresses", () => {
  it.each([
    "https://www.youtube.com/watch?v=abc",
    "https://youtu.be/abc",
    "https://m.youtube.com/watch?v=abc",
  ])("accepts %s", (u) => {
    expect(validateYoutubeUrl(u)).toBeNull();
  });

  it("refuses other sites", () => {
    expect(validateYoutubeUrl("https://vimeo.com/123")).toMatch(/YouTube/);
  });

  it("is not fooled by youtube appearing elsewhere in the address", () => {
    // Checking with .includes("youtube.com") would accept both of these.
    expect(validateYoutubeUrl("https://evil.com/youtube.com")).toBeTruthy();
    expect(validateYoutubeUrl("https://youtube.com.evil.com/watch")).toBeTruthy();
  });
});

describe("describing a failed upload", () => {
  it("shows the server's own sentence when it wrote one", () => {
    const error = { response: { status: 400, data: { detail: "The uploaded file is empty." } } };
    expect(describeUploadError(error)).toBe("The uploaded file is empty.");
  });

  it("does not print a validation-error array as if it were a message", () => {
    const error = { response: { status: 422, data: { detail: [{ loc: ["body"], msg: "x" }] } } };
    const message = describeUploadError(error);
    expect(typeof message).toBe("string");
    expect(message).not.toMatch(/loc|\[object/);
  });

  it("stays silent when the learner cancelled", () => {
    expect(describeUploadError({ code: "ERR_CANCELED" })).toBeNull();
    expect(describeUploadError({ name: "CanceledError" })).toBeNull();
  });

  it("tells apart a timeout, an expired session and an unreachable server", () => {
    const timeout = describeUploadError({ code: "ECONNABORTED" });
    const expired = describeUploadError({ response: { status: 401, data: {} } });
    const offline = describeUploadError({});
    expect(new Set([timeout, expired, offline]).size).toBe(3);
    expect(expired).toMatch(/sign in/i);
  });
});
