import { describe, expect, it, vi } from "vitest";

vi.mock("../api/client", () => ({
  default: { get: vi.fn() },
}));

import api from "../api/client";
import {
  fetchMostRecentCompletedSession,
  fetchSessionAnalytics,
  fetchSessionHistory,
} from "./api";

describe("fetchSessionHistory", () => {
  it("calls the real session-history endpoint with default paging", async () => {
    api.get.mockResolvedValueOnce({
      data: { items: [], pagination: { limit: 20, offset: 0, returned_count: 0, total_count: 0 } },
    });

    await fetchSessionHistory();

    expect(api.get).toHaveBeenCalledWith("/api/analytics/sessions", {
      params: { limit: 20, offset: 0 },
    });
  });

  it("passes content_id through only when given one", async () => {
    api.get.mockResolvedValueOnce({
      data: { items: [], pagination: { limit: 1, offset: 0, returned_count: 0, total_count: 0 } },
    });

    await fetchSessionHistory({ limit: 1, contentId: "content-9" });

    expect(api.get).toHaveBeenCalledWith("/api/analytics/sessions", {
      params: { limit: 1, offset: 0, content_id: "content-9" },
    });
  });

  it("marks a failure as a generic server error", async () => {
    api.get.mockRejectedValueOnce(new Error("network down"));

    await expect(fetchSessionHistory()).rejects.toMatchObject({ kind: "server_error" });
  });
});

describe("fetchMostRecentCompletedSession", () => {
  it("asks for exactly one item and returns it", async () => {
    api.get.mockResolvedValueOnce({
      data: {
        items: [{ session_id: "session-latest", completed_at: "2026-08-17T09:04:20Z" }],
        pagination: { limit: 1, offset: 0, returned_count: 1, total_count: 3 },
      },
    });

    const result = await fetchMostRecentCompletedSession();

    expect(api.get).toHaveBeenCalledWith("/api/analytics/sessions", {
      params: { limit: 1, offset: 0 },
    });
    expect(result).toEqual({ session_id: "session-latest", completed_at: "2026-08-17T09:04:20Z" });
  });

  it("returns null when the learner has no completed sessions", async () => {
    api.get.mockResolvedValueOnce({
      data: { items: [], pagination: { limit: 1, offset: 0, returned_count: 0, total_count: 0 } },
    });

    const result = await fetchMostRecentCompletedSession();

    expect(result).toBeNull();
  });
});

describe("fetchSessionAnalytics", () => {
  it("reshapes the flat backend response into { overview, summary, insightReport }", async () => {
    api.get.mockResolvedValueOnce({
      data: {
        schema_version: "1.0",
        metric_version: "1.0",
        session_id: "session-1",
        user_id: "user-1",
        content_id: "content-1",
        duration_seconds: 60,
        insight_report: { status: "generated", report_text: "Nice session." },
      },
    });

    const result = await fetchSessionAnalytics("session-1");

    expect(api.get).toHaveBeenCalledWith("/api/sessions/session-1/analytics");
    expect(result).toEqual({
      overview: { session_status: "completed" },
      summary: {
        schema_version: "1.0",
        metric_version: "1.0",
        session_id: "session-1",
        user_id: "user-1",
        content_id: "content-1",
        duration_seconds: 60,
      },
      insightReport: { status: "generated", report_text: "Nice session." },
    });
  });

  it("maps a 404 to the not_found error kind", async () => {
    const err = new Error("nope");
    err.response = { status: 404, data: {} };
    api.get.mockRejectedValueOnce(err);

    await expect(fetchSessionAnalytics("missing")).rejects.toMatchObject({ kind: "not_found" });
  });

  it("maps the analytics_summary_missing 409 to the summary_missing error kind", async () => {
    const err = new Error("not ready");
    err.response = {
      status: 409,
      data: { detail: { reason_code: "analytics_summary_missing", message: "not ready" } },
    };
    api.get.mockRejectedValueOnce(err);

    await expect(fetchSessionAnalytics("session-1")).rejects.toMatchObject({
      kind: "summary_missing",
    });
  });

  it("maps every other failure to server_error", async () => {
    const err = new Error("boom");
    err.response = { status: 500, data: {} };
    api.get.mockRejectedValueOnce(err);

    await expect(fetchSessionAnalytics("session-1")).rejects.toMatchObject({
      kind: "server_error",
    });
  });
});
