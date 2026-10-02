/**
 * The library and upload screens, tested on the behaviour that goes wrong
 * quietly: a failed load that looks like an empty library, a duplicate that
 * looks like a new upload, an oversized file that starts uploading anyway.
 */

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = {
  listContent: vi.fn(),
  uploadPdf: vi.fn(),
  uploadResearchPaper: vi.fn(),
  uploadVideo: vi.fn(),
  pasteText: vi.fn(),
  addFromUrl: vi.fn(),
  addFromYoutube: vi.fn(),
};
vi.mock("./api", async () => {
  const real = await vi.importActual("./api");
  return {
    ...real,
    listContent: (...a) => api.listContent(...a),
    uploadPdf: (...a) => api.uploadPdf(...a),
    uploadResearchPaper: (...a) => api.uploadResearchPaper(...a),
    uploadVideo: (...a) => api.uploadVideo(...a),
    pasteText: (...a) => api.pasteText(...a),
    addFromUrl: (...a) => api.addFromUrl(...a),
    addFromYoutube: (...a) => api.addFromYoutube(...a),
  };
});

import LibraryPage from "./LibraryPage";
import UploadPage from "./UploadPage";

const draw = (ui) => render(<MemoryRouter>{ui}</MemoryRouter>);

beforeEach(() => {
  for (const fn of Object.values(api)) fn.mockReset();
});

const doc = (over = {}) => ({
  content_id: "c1",
  title: "Induction",
  content_type: "pdf",
  status: "ready",
  warnings: [],
  chunk_count: 4,
  created_at: "2026-09-01T00:00:00Z",
  ...over,
});

describe("the library", () => {
  it("shows a failed load as a failure, never as an empty library", async () => {
    // "No documents" during a network error would tell someone their work was
    // gone. The two states need different copy and different actions.
    api.listContent.mockRejectedValue(new Error("network"));
    draw(<LibraryPage />);

    expect(await screen.findByText(/could not load your documents/i)).toBeTruthy();
    expect(screen.queryByText(/nothing here yet/i)).toBeNull();
    expect(screen.getByText(/your documents are safe/i)).toBeTruthy();
  });

  it("can retry after a failure", async () => {
    const user = userEvent.setup();
    api.listContent.mockRejectedValueOnce(new Error("network"));
    api.listContent.mockResolvedValueOnce({ data: [doc()] });
    draw(<LibraryPage />);

    await user.click(await screen.findByRole("button", { name: /try again/i }));
    expect(await screen.findByText("Induction")).toBeTruthy();
  });

  it("shows a genuinely empty library as empty, with the way forward", async () => {
    api.listContent.mockResolvedValue({ data: [] });
    draw(<LibraryPage />);
    expect(await screen.findByText(/nothing here yet/i)).toBeTruthy();
    expect(screen.getByRole("link", { name: /add your first document/i })).toBeTruthy();
  });

  it("lists newest first", async () => {
    api.listContent.mockResolvedValue({
      data: [
        doc({ content_id: "a", title: "Oldest", created_at: "2026-01-01T00:00:00Z" }),
        doc({ content_id: "b", title: "Newest", created_at: "2026-09-01T00:00:00Z" }),
      ],
    });
    draw(<LibraryPage />);
    await screen.findByText("Newest");
    const titles = screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
    expect(titles).toEqual(["Newest", "Oldest"]);
  });

  it("links a ready document into a study session by id", async () => {
    api.listContent.mockResolvedValue({ data: [doc({ content_id: "abc 123" })] });
    draw(<LibraryPage />);
    const link = await screen.findByRole("link", { name: /start session/i });
    // Encoded, so an id with odd characters cannot break out of the query string.
    expect(link.getAttribute("href")).toBe("/study?content=abc%20123");
  });

  it("does not offer to start a session on a document that is not ready", async () => {
    api.listContent.mockResolvedValue({
      data: [
        doc({ content_id: "p", title: "Processing one", status: "processing" }),
        doc({ content_id: "f", title: "Failed one", status: "failed" }),
      ],
    });
    draw(<LibraryPage />);
    await screen.findByText("Processing one");

    expect(screen.queryByRole("link", { name: /start session/i })).toBeNull();
    expect(screen.getByText(/still processing/i)).toBeTruthy();
    expect(screen.getByText(/could not be processed/i)).toBeTruthy();
  });

  it("shows a document's language warning in words", async () => {
    api.listContent.mockResolvedValue({
      data: [doc({ warnings: ["urdu_content_reduced_accuracy"] })],
    });
    draw(<LibraryPage />);
    expect(await screen.findByText(/this document is in urdu/i)).toBeTruthy();
  });
});

describe("adding a document", () => {
  it("does not start an upload for a file that is obviously too big", async () => {
    const user = userEvent.setup();
    draw(<UploadPage />);

    const big = new File(["x"], "huge.pdf", { type: "application/pdf" });
    Object.defineProperty(big, "size", { value: 26 * 1024 * 1024 });
    await user.upload(screen.getByLabelText(/^file/i), big);
    await user.click(screen.getByRole("button", { name: /add document/i }));

    expect(api.uploadPdf).not.toHaveBeenCalled();
    expect(await screen.findByText(/limit is 25/i)).toBeTruthy();
  });

  it("does not start an upload for the wrong kind of file", async () => {
    const user = userEvent.setup({ applyAccept: false });
    draw(<UploadPage />);

    await user.upload(screen.getByLabelText(/^file/i), new File(["x"], "notes.docx"));
    await user.click(screen.getByRole("button", { name: /add document/i }));

    expect(api.uploadPdf).not.toHaveBeenCalled();
    expect(await screen.findByText(/does not look like a PDF/i)).toBeTruthy();
  });

  it("uploads a valid PDF and confirms it", async () => {
    const user = userEvent.setup();
    api.uploadPdf.mockResolvedValue({ data: doc({ content_id: "new1", title: "Handbook" }) });
    draw(<UploadPage />);

    await user.upload(screen.getByLabelText(/^file/i), new File(["%PDF-1.4"], "handbook.pdf"));
    await user.click(screen.getByRole("button", { name: /add document/i }));

    expect(await screen.findByText(/ready to study/i)).toBeTruthy();
    expect(screen.getByRole("link", { name: /start a session/i }).getAttribute("href")).toBe(
      "/study?content=new1"
    );
  });

  it("reports an identical upload as already existing, not as new", async () => {
    // Saying "Added" would be wrong - nothing was created - and an error would
    // be worse. It is neither.
    const user = userEvent.setup();
    api.uploadPdf.mockResolvedValue({ data: doc({ duplicate_of_existing: true }) });
    draw(<UploadPage />);

    await user.upload(screen.getByLabelText(/^file/i), new File(["%PDF-1.4"], "a.pdf"));
    await user.click(screen.getByRole("button", { name: /add document/i }));

    expect(await screen.findByText(/you already have this/i)).toBeTruthy();
    expect(screen.queryByText(/ready to study/i)).toBeNull();
  });

  it("shows the document's warnings at the moment it is added", async () => {
    const user = userEvent.setup();
    api.pasteText.mockResolvedValue({
      data: doc({ warnings: ["non_english_content"], title: "Notes" }),
    });
    draw(<UploadPage />);

    await user.click(screen.getByRole("tab", { name: /paste text/i }));
    await user.type(screen.getByLabelText(/^title/i), "Notes");
    await user.type(screen.getByLabelText(/^text/i), "x".repeat(60));
    await user.click(screen.getByRole("button", { name: /add document/i }));

    expect(await screen.findByText(/worth knowing before you start/i)).toBeTruthy();
    expect(screen.getByText(/not in english/i)).toBeTruthy();
  });

  it("shows the server's own message when it refuses", async () => {
    const user = userEvent.setup();
    api.uploadPdf.mockRejectedValue({
      response: { status: 400, data: { detail: "That PDF has no readable text." } },
    });
    draw(<UploadPage />);

    await user.upload(screen.getByLabelText(/^file/i), new File(["%PDF-1.4"], "scan.pdf"));
    await user.click(screen.getByRole("button", { name: /add document/i }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toMatch(/no readable text/i);
  });

  it("says nothing when the learner cancels", async () => {
    const user = userEvent.setup();
    api.uploadPdf.mockRejectedValue({ code: "ERR_CANCELED" });
    draw(<UploadPage />);

    await user.upload(screen.getByLabelText(/^file/i), new File(["%PDF-1.4"], "a.pdf"));
    await user.click(screen.getByRole("button", { name: /add document/i }));

    await waitFor(() => expect(api.uploadPdf).toHaveBeenCalled());
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("offers Cancel only while something is in flight", async () => {
    const user = userEvent.setup();
    let release;
    api.uploadPdf.mockReturnValue(new Promise((resolve) => (release = resolve)));
    draw(<UploadPage />);

    expect(screen.queryByRole("button", { name: /cancel/i })).toBeNull();
    await user.upload(screen.getByLabelText(/^file/i), new File(["%PDF-1.4"], "a.pdf"));
    await user.click(screen.getByRole("button", { name: /add document/i }));

    expect(await screen.findByRole("button", { name: /cancel/i })).toBeTruthy();
    release({ data: doc() });
    await waitFor(() => expect(screen.queryByRole("button", { name: /cancel/i })).toBeNull());
  });

  it("validates a YouTube link before sending it", async () => {
    const user = userEvent.setup();
    draw(<UploadPage />);

    await user.click(screen.getByRole("tab", { name: /youtube/i }));
    await user.type(screen.getByLabelText(/web address/i), "https://vimeo.com/1");
    await user.click(screen.getByRole("button", { name: /add document/i }));

    expect(api.addFromYoutube).not.toHaveBeenCalled();
    expect(await screen.findByText(/not a YouTube link/i)).toBeTruthy();
  });

  it("tells the learner up front that a video takes a while", async () => {
    const user = userEvent.setup();
    draw(<UploadPage />);
    await user.click(screen.getByRole("tab", { name: /video file/i }));
    expect(screen.getByText(/several minutes/i)).toBeTruthy();
  });
});

describe("the method tabs", () => {
  it("marks exactly one tab selected, and links it to its panel", () => {
    draw(<UploadPage />);
    const tabs = screen.getAllByRole("tab");
    expect(tabs).toHaveLength(6);
    expect(tabs.filter((t) => t.getAttribute("aria-selected") === "true")).toHaveLength(1);
    const panel = screen.getByRole("tabpanel");
    expect(panel.getAttribute("aria-labelledby")).toBe(
      tabs.find((t) => t.getAttribute("aria-selected") === "true").id
    );
  });

  it("clears a previous error when switching method", async () => {
    const user = userEvent.setup();
    draw(<UploadPage />);
    await user.click(screen.getByRole("button", { name: /add document/i }));
    expect(await screen.findByText(/choose a pdf/i)).toBeTruthy();

    await user.click(screen.getByRole("tab", { name: /web page/i }));
    expect(screen.queryByText(/choose a pdf/i)).toBeNull();
  });
});

describe("adding a document: live validation, not only on submit", () => {
  it("flags an oversized file the moment it is chosen, before clicking Add document", async () => {
    const user = userEvent.setup();
    draw(<UploadPage />);

    const big = new File(["x"], "huge.pdf", { type: "application/pdf" });
    Object.defineProperty(big, "size", { value: 26 * 1024 * 1024 });
    await user.upload(screen.getByLabelText(/^file/i), big);

    expect(await screen.findByText(/limit is 25/i)).toBeTruthy();
    expect(api.uploadPdf).not.toHaveBeenCalled();
  });

  it("flags a malformed web address as soon as the field is left, before submitting", async () => {
    const user = userEvent.setup();
    draw(<UploadPage />);

    await user.click(screen.getByRole("tab", { name: /web page/i }));
    await user.type(screen.getByLabelText(/web address/i), "not a url");
    await user.tab();

    expect(await screen.findByText(/does not look like a web address|enter a web address/i)).toBeTruthy();
    expect(api.addFromUrl).not.toHaveBeenCalled();
  });

  it("shows nothing for a field that has not been reached yet", () => {
    draw(<UploadPage />);

    expect(screen.queryByText(/choose a pdf to upload/i)).not.toBeInTheDocument();
  });
});
