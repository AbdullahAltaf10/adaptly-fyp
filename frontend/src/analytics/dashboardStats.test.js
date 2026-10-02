import { describe, expect, it } from "vitest";

import { computeDashboardStats } from "./dashboardStats";

const NOW = new Date("2026-09-27T12:00:00Z");

function session({ completedAt, durationSeconds = 600, contentId = "c1" }) {
  return { completed_at: completedAt, duration_seconds: durationSeconds, content_id: contentId };
}

describe("computeDashboardStats", () => {
  it("returns honest zeros/nulls for no history, not fabricated numbers", () => {
    expect(computeDashboardStats([], { now: NOW })).toEqual({
      sessionsThisWeek: 0,
      averageDurationSeconds: null,
      longestStreakDays: 0,
      documentsCovered: 0,
    });
  });

  it("counts only sessions completed within the last 7 days as this week", () => {
    const items = [
      session({ completedAt: "2026-09-27T09:00:00Z" }), // today
      session({ completedAt: "2026-09-21T09:00:00Z" }), // 6 days ago - in
      session({ completedAt: "2026-09-19T09:00:00Z" }), // 8 days ago - out
    ];

    expect(computeDashboardStats(items, { now: NOW }).sessionsThisWeek).toBe(2);
  });

  it("averages duration across every session handed in", () => {
    const items = [
      session({ completedAt: "2026-09-27T09:00:00Z", durationSeconds: 600 }),
      session({ completedAt: "2026-09-26T09:00:00Z", durationSeconds: 1200 }),
    ];

    expect(computeDashboardStats(items, { now: NOW }).averageDurationSeconds).toBe(900);
  });

  it("counts distinct documents, not sessions", () => {
    const items = [
      session({ completedAt: "2026-09-27T09:00:00Z", contentId: "c1" }),
      session({ completedAt: "2026-09-26T09:00:00Z", contentId: "c1" }),
      session({ completedAt: "2026-09-25T09:00:00Z", contentId: "c2" }),
    ];

    expect(computeDashboardStats(items, { now: NOW }).documentsCovered).toBe(2);
  });

  it("finds the longest run of consecutive calendar days", () => {
    const items = [
      session({ completedAt: "2026-09-27T09:00:00Z" }), // day 1 \
      session({ completedAt: "2026-09-26T09:00:00Z" }), // day 2  } streak of 3
      session({ completedAt: "2026-09-25T09:00:00Z" }), // day 3 /
      session({ completedAt: "2026-09-20T09:00:00Z" }), // isolated day
    ];

    expect(computeDashboardStats(items, { now: NOW }).longestStreakDays).toBe(3);
  });

  it("counts two sessions on the same day as one day, not two", () => {
    const items = [
      session({ completedAt: "2026-09-27T09:00:00Z" }),
      session({ completedAt: "2026-09-27T18:00:00Z" }),
    ];

    expect(computeDashboardStats(items, { now: NOW }).longestStreakDays).toBe(1);
  });

  it("does not require the streak to reach today", () => {
    const items = [
      session({ completedAt: "2026-09-10T09:00:00Z" }),
      session({ completedAt: "2026-09-11T09:00:00Z" }),
    ];

    expect(computeDashboardStats(items, { now: NOW }).longestStreakDays).toBe(2);
  });

  it("ignores entries with an unparseable date or missing duration rather than throwing", () => {
    const items = [
      { completed_at: "not-a-date", duration_seconds: 600, content_id: "c1" },
      { completed_at: "2026-09-27T09:00:00Z", duration_seconds: null, content_id: "c2" },
    ];

    const stats = computeDashboardStats(items, { now: NOW });
    // Item 1's date cannot be parsed, so it contributes to neither
    // this-week nor the streak, but its valid duration still counts toward
    // the average - that stat is not week-scoped. Item 2's date is valid
    // (and within the week) despite its duration being null.
    expect(stats.sessionsThisWeek).toBe(1);
    expect(stats.averageDurationSeconds).toBe(600);
    expect(stats.longestStreakDays).toBe(1);
    expect(stats.documentsCovered).toBe(2);
  });
});
