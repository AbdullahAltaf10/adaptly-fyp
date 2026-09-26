import { describe, expect, it, vi } from "vitest";

vi.mock("../api/client", () => ({
  default: { post: vi.fn(() => Promise.resolve({ data: {} })) },
}));

import api from "../api/client";
import { startSession } from "./api";

describe("startSession", () => {
  it("sends content_id when the caller has one", () => {
    startSession("session-1", "content-1");
    expect(api.post).toHaveBeenCalledWith("/engagement/session/start", {
      session_id: "session-1",
      content_id: "content-1",
    });
  });

  it("omits content_id entirely when the caller doesn't have one yet", () => {
    startSession("session-1");
    expect(api.post).toHaveBeenCalledWith("/engagement/session/start", {
      session_id: "session-1",
    });
  });
});
