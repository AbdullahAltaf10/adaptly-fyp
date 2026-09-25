/**
 * The delivery lifecycle, which is the part of Module 4's frontend that can
 * fail without anybody noticing.
 *
 * Every intervention starts at `offered`, and Module 8 measures recovery from
 * no such status. A UI that renders an intervention and never reports it
 * leaves a full event collection and an empty dashboard, with nothing raising
 * anywhere. So these tests do not check that something appeared - they check
 * what was reported, and for the two learner-initiated types they check that
 * merely showing it is not enough.
 */

import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./api", () => ({
  reportStatus: vi.fn(() => Promise.resolve({ data: {} })),
  fetchContent: vi.fn(() =>
    Promise.resolve({
      data: {
        generated: "A simpler version.",
        original: "The original passage.",
        generator: "gemini",
        cached: false,
      },
    })
  ),
}));

import { fetchContent, reportStatus } from "./api";
import {
  ASSISTANT_HELP_PROMPT,
  BREAK_SUGGESTION,
  BULLET_SUMMARY,
  SIMPLIFY_CONTENT,
  startsRecoveryMeasurement,
} from "./constants";
import { useIntervention } from "./useIntervention";

const SESSION = "s1";

function offered(type, id = "i1") {
  return {
    intervention_id: id,
    intervention_type: type,
    reason: "Signs of difficulty.",
    reason_code: "struggling",
    chunk_id: "7",
    content_id: "c1",
  };
}

function setup(intervention) {
  return renderHook(
    ({ intervention: value }) =>
      useIntervention({ intervention: value, sessionId: SESSION }),
    { initialProps: { intervention } }
  );
}

/** Every status reported, in order. */
function reported() {
  return reportStatus.mock.calls.map(([, options]) => options.status);
}

beforeEach(() => {
  reportStatus.mockClear();
  fetchContent.mockClear();
});

describe("what gets reported", () => {
  it("reports displayed only once the text is actually in hand", async () => {
    const { result } = setup(offered(SIMPLIFY_CONTENT));

    // The fetch is still in flight, so nothing has reached the learner yet.
    expect(reported()).not.toContain("displayed");

    await waitFor(() => expect(result.current.current).not.toBeNull());
    expect(reported()).toEqual(["displayed"]);
    expect(result.current.content.generated).toBe("A simpler version.");
  });

  it("reports displayed immediately for a type with no generated text", async () => {
    const { result } = setup(offered(BREAK_SUGGESTION));
    await waitFor(() => expect(result.current.current).not.toBeNull());
    expect(fetchContent).not.toHaveBeenCalled();
    expect(reported()).toEqual(["displayed"]);
  });

  it("reports failed and shows nothing when the text cannot be generated", async () => {
    fetchContent.mockRejectedValueOnce(new Error("503"));
    const { result } = setup(offered(SIMPLIFY_CONTENT));

    await waitFor(() => expect(reported()).toContain("failed"));
    expect(result.current.current).toBeNull();
    expect(reported()).not.toContain("displayed");
  });

  it("does not report the same status twice", async () => {
    const { result, rerender } = setup(offered(SIMPLIFY_CONTENT));
    await waitFor(() => expect(result.current.current).not.toBeNull());

    rerender({ intervention: offered(SIMPLIFY_CONTENT) });
    rerender({ intervention: offered(SIMPLIFY_CONTENT) });

    expect(reported().filter((s) => s === "displayed")).toHaveLength(1);
  });
});

describe("the statuses Module 8 actually measures", () => {
  it("an automatic type is measured as soon as it is displayed", async () => {
    const { result } = setup(offered(SIMPLIFY_CONTENT));
    await waitFor(() => expect(result.current.current).not.toBeNull());

    const last = reported().at(-1);
    expect(startsRecoveryMeasurement(SIMPLIFY_CONTENT, last)).toBe(true);
  });

  it.each([BREAK_SUGGESTION, ASSISTANT_HELP_PROMPT])(
    "%s is NOT measured by being shown, only by being accepted",
    async (type) => {
      const { result } = setup(offered(type));
      await waitFor(() => expect(result.current.current).not.toBeNull());

      expect(startsRecoveryMeasurement(type, reported().at(-1))).toBe(false);

      act(() => result.current.accept());
      await waitFor(() => expect(reported()).toContain("accepted"));
      expect(startsRecoveryMeasurement(type, reported().at(-1))).toBe(true);
    }
  );

  it.each([
    [SIMPLIFY_CONTENT, "complete"],
    [BULLET_SUMMARY, "complete"],
    [BREAK_SUGGESTION, "accept"],
    [ASSISTANT_HELP_PROMPT, "accept"],
  ])(
    "every path a learner can take through %s reaches something measurable",
    async (type, action) => {
      const { result } = setup(offered(type));
      await waitFor(() => expect(result.current.current).not.toBeNull());

      act(() => result.current[action]());
      await waitFor(() =>
        expect(
          reported().some((status) => startsRecoveryMeasurement(type, status))
        ).toBe(true)
      );
    }
  );
});

describe("the learner's own actions", () => {
  it("accepting does not close it - a break is not over when it starts", async () => {
    const { result } = setup(offered(BREAK_SUGGESTION));
    await waitFor(() => expect(result.current.current).not.toBeNull());

    act(() => result.current.accept());
    await waitFor(() => expect(result.current.accepted).toBe(true));
    expect(result.current.current).not.toBeNull();

    act(() => result.current.complete());
    await waitFor(() => expect(result.current.current).toBeNull());
    expect(reported()).toEqual(["displayed", "accepted", "completed"]);
  });

  it("dismissing closes it and says so", async () => {
    const { result } = setup(offered(SIMPLIFY_CONTENT));
    await waitFor(() => expect(result.current.current).not.toBeNull());

    act(() => result.current.dismiss());
    await waitFor(() => expect(result.current.current).toBeNull());
    expect(reported()).toEqual(["displayed", "dismissed"]);
  });
});

describe("when a second intervention arrives", () => {
  /**
   * The old one is left where it is rather than auto-dismissed, because the
   * learner did not dismiss it and `dismissed` writes an outcome.
   *
   * Since #54 this no longer costs the measurement either way - `delivered_at`
   * survives a later dismissal - so this is now about the record being true
   * rather than about protecting a metric.
   */
  it("does not dismiss the one already on screen", async () => {
    const { result, rerender } = setup(offered(SIMPLIFY_CONTENT, "first"));
    await waitFor(() => expect(result.current.current).not.toBeNull());

    rerender({ intervention: offered(BREAK_SUGGESTION, "second") });
    await waitFor(() =>
      expect(result.current.current?.intervention_id).toBe("second")
    );

    expect(reported()).not.toContain("dismissed");
    const forFirst = reportStatus.mock.calls
      .filter(([id]) => id === "first")
      .map(([, options]) => options.status);
    expect(forFirst).toEqual(["displayed"]);
  });
});

describe("when reporting itself fails", () => {
  it("still advances, rather than stranding it on screen", async () => {
    const { result } = setup(offered(BREAK_SUGGESTION));
    await waitFor(() => expect(result.current.current).not.toBeNull());

    reportStatus.mockRejectedValueOnce(new Error("network"));
    act(() => result.current.dismiss());

    await waitFor(() => expect(result.current.current).toBeNull());
  });
});
