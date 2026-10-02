// frontend/src/intervention/useDwellFusion.test.jsx
import { act, render, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useDwellFusion } from "./useDwellFusion";
import ContentViewer from "../content/ContentViewer";

vi.mock("../engagement/webgazerSignal", () => ({
  getWebgazerSignal: vi.fn(() => null),
}));
import { getWebgazerSignal } from "../engagement/webgazerSignal";

let observers = [];
class FakeIntersectionObserver {
  constructor(callback) { this.callback = callback; this.targets = new Set(); observers.push(this); }
  observe(target) { this.targets.add(target); }
  unobserve(target) { this.targets.delete(target); }
  disconnect() { this.targets.clear(); }
}
/** Only notifies observers that actually had `.observe(element)` called on
 * them - matching real IntersectionObserver semantics, so a test can tell
 * the difference between "registered into this hook's own bookkeeping" and
 * "actually being watched by a live observer instance". */
function see(element, ratio) {
  act(() =>
    observers.forEach((o) => {
      if (o.targets.has(element)) {
        o.callback([{ target: element, intersectionRatio: ratio }]);
      }
    })
  );
}

beforeEach(() => {
  observers = [];
  vi.useFakeTimers();
  vi.stubGlobal("IntersectionObserver", FakeIntersectionObserver);
  getWebgazerSignal.mockReturnValue(null);
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("useDwellFusion", () => {
  it("behaves exactly like useDwell when no extra signals are ever available", () => {
    const { result } = renderHook(() => useDwellFusion({ enabled: true }));
    const el = document.createElement("section");
    Object.defineProperty(el, "getBoundingClientRect", {
      value: () => ({ top: 0, bottom: 100, left: 0, right: 100 }),
    });
    act(() => result.current.register("0", el));
    see(el, 0.8);
    act(() => vi.advanceTimersByTime(1000));
    expect(result.current.activeChunkId).toBe("0");
    expect(result.current.chunkId()).toBe("0");
  });

  it("reports fusionConfidence 0 and null when nothing is registered", () => {
    const { result } = renderHook(() => useDwellFusion({ enabled: true }));
    act(() => vi.advanceTimersByTime(1000));
    expect(result.current.activeChunkId).toBeNull();
    expect(result.current.fusionConfidence).toBe(0);
  });

  it("passes the getLatestLandmarks() result through to the gaze-quadrant signal without throwing when it returns null", () => {
    const getLatestLandmarks = vi.fn(() => null);
    const { result } = renderHook(() => useDwellFusion({ enabled: true, getLatestLandmarks }));
    const el = document.createElement("section");
    Object.defineProperty(el, "getBoundingClientRect", { value: () => ({ top: 0, bottom: 100, left: 0, right: 100 }) });
    act(() => result.current.register("0", el));
    see(el, 0.5);
    act(() => vi.advanceTimersByTime(1000));
    expect(getLatestLandmarks).toHaveBeenCalled();
    expect(result.current.activeChunkId).toBe("0");
  });

  it("keeps dwell accumulating across ordinary re-renders, for a chunk registered before the session was enabled", () => {
    // Reproduces the real StudySession scenario through the real
    // ContentViewer + ContentChunk (whose ref callback is memoized on
    // [onChunkRef, chunk_id] - see content/ContentViewer.jsx): chunks
    // register as soon as a document loads, regardless of whether "Start
    // session" has been clicked yet (useDwellFusion's `enabled` becomes
    // true only afterwards), and the page re-renders often afterwards
    // (each new /analyze prediction, etc.). Neither may reset dwell, and
    // neither may leave an already-registered chunk never actually observed.
    const content = {
      title: "Doc",
      chunks: [{ chunk_id: "0", order: 0, text: "Paragraph text." }],
    };

    let latestDwell = null;
    function Harness({ enabled }) {
      const dwell = useDwellFusion({ enabled });
      latestDwell = dwell;
      return <ContentViewer content={content} onChunkRef={dwell.register} />;
    }

    const { rerender } = render(<Harness enabled={false} />);

    // Learner clicks "Start session".
    rerender(<Harness enabled={true} />);

    const el = document.querySelector('[data-chunk-id="0"]');
    see(el, 0.9);
    act(() => vi.advanceTimersByTime(2000));

    // Ordinary re-renders that change nothing about this hook's own inputs -
    // must not tear down the observation or reset accumulated dwell.
    rerender(<Harness enabled={true} />);
    rerender(<Harness enabled={true} />);

    act(() => vi.advanceTimersByTime(2000));

    expect(latestDwell.activeChunkId).toBe("0");
    expect(latestDwell.seconds()).toBeGreaterThan(3);
  });

  it("tracks dwell time against the FUSED active chunk, not the inner visibility-only pick", () => {
    // "a" is the only visible chunk, so both useDwell's own internal
    // decision and the fused one agree on "a" at first, and dwell
    // accumulates for it.
    const { result } = renderHook(() => useDwellFusion({ enabled: true }));

    const a = document.createElement("section");
    const b = document.createElement("section");
    Object.defineProperty(a, "getBoundingClientRect", { value: () => ({ top: 0, bottom: 50, left: 0, right: 100 }) });
    Object.defineProperty(b, "getBoundingClientRect", { value: () => ({ top: 50, bottom: 100, left: 0, right: 100 }) });

    act(() => {
      result.current.register("a", a);
      result.current.register("b", b);
    });

    see(a, 0.5);
    see(b, 0.5);
    act(() => vi.advanceTimersByTime(3000));
    expect(result.current.activeChunkId).toBe("a");
    expect(result.current.seconds()).toBeGreaterThan(2);

    // Nothing about visibility changes - useDwell's own internal decision
    // stays "a" - but WebGazer now confidently points inside "b"'s rect,
    // so the FUSED decision switches to "b".
    getWebgazerSignal.mockReturnValue({ x: 10, y: 75, confidence: 1 });
    act(() => vi.advanceTimersByTime(1000));
    expect(result.current.activeChunkId).toBe("b");

    // seconds() must now report time on "b", which has been active for
    // only ~1s - not the several seconds "a" had already accumulated.
    expect(result.current.seconds()).toBeLessThan(1.5);
  });

  it("wires temporal hysteresis: a small tick-to-tick nudge does not flip the pick on its own", () => {
    // fusionScoring's hysteresis (exhaustively unit-tested in
    // fusionScoring.test.js) only works if this hook actually carries its
    // OWN fused pick from one tick into the next - the bug this proves
    // against is "the ref is never threaded through", which would make
    // every tick start from previousActiveChunkId=null and re-litigate the
    // tie from scratch. Both chunks are fully visible (a real case: a short
    // document with two paragraphs both on screen at once - see the live
    // bug this fixes, 2026-09-30), so visibility alone cannot break the tie
    // and WebGazer is doing all the (barely) deciding work.
    const { result } = renderHook(() => useDwellFusion({ enabled: true }));

    const a = document.createElement("section");
    const b = document.createElement("section");
    Object.defineProperty(a, "getBoundingClientRect", { value: () => ({ top: 0, bottom: 50, left: 0, right: 100 }) });
    Object.defineProperty(b, "getBoundingClientRect", { value: () => ({ top: 50, bottom: 100, left: 0, right: 100 }) });

    act(() => {
      result.current.register("a", a);
      result.current.register("b", b);
    });
    see(a, 1);
    see(b, 1);

    // Tick 1: WebGazer sits just inside "a", barely ahead of "b" (a lead of
    // ~0.019, comfortably under HYSTERESIS_MARGIN).
    getWebgazerSignal.mockReturnValue({ x: 10, y: 45, confidence: 1 });
    act(() => vi.advanceTimersByTime(1000));
    expect(result.current.activeChunkId).toBe("a");

    // Tick 2: WebGazer nudges just inside "b" instead - by the same tiny
    // margin. Without hysteresis this raw score would nominally favour "b"
    // and flip; with it, "a" (the already-active chunk) persists because
    // the lead never clears the margin.
    getWebgazerSignal.mockReturnValue({ x: 10, y: 55, confidence: 1 });
    act(() => vi.advanceTimersByTime(1000));
    expect(result.current.activeChunkId).toBe("a");

    // A genuinely confident, sustained point in "b" must still win -
    // hysteresis damps noise, it does not lock the pick forever.
    getWebgazerSignal.mockReturnValue({ x: 10, y: 90, confidence: 1 });
    act(() => vi.advanceTimersByTime(1000));
    expect(result.current.activeChunkId).toBe("b");
  });
});
