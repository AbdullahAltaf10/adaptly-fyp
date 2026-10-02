import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useParagraphPopup } from "./useParagraphPopup";

function fakeIntervention(overrides = {}) {
  return {
    current: null,
    content: null,
    loading: false,
    accepted: false,
    accept: vi.fn(),
    complete: vi.fn(),
    dismiss: vi.fn(),
    ...overrides,
  };
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("useParagraphPopup", () => {
  it("does not close while the learner stays on the SAME paragraph, however long", () => {
    const intervention = fakeIntervention({ current: { intervention_id: "i1", chunk_id: "3" } });
    renderHook(
      ({ activeChunkId }) => useParagraphPopup({ intervention, activeChunkId }),
      { initialProps: { activeChunkId: "3" } }
    );
    act(() => vi.advanceTimersByTime(60_000));
    expect(intervention.complete).not.toHaveBeenCalled();
  });

  it("closes once a different chunk has been active continuously for the confirm window", () => {
    const intervention = fakeIntervention({ current: { intervention_id: "i1", chunk_id: "3" } });
    const { rerender } = renderHook(
      ({ activeChunkId }) => useParagraphPopup({ intervention, activeChunkId }),
      { initialProps: { activeChunkId: "3" } }
    );
    rerender({ activeChunkId: "4" });
    act(() => vi.advanceTimersByTime(2999));
    expect(intervention.complete).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(2));
    expect(intervention.complete).toHaveBeenCalledTimes(1);
  });

  it("cancels the close if the learner returns before the confirm window elapses", () => {
    const intervention = fakeIntervention({ current: { intervention_id: "i1", chunk_id: "3" } });
    const { rerender } = renderHook(
      ({ activeChunkId }) => useParagraphPopup({ intervention, activeChunkId }),
      { initialProps: { activeChunkId: "3" } }
    );
    rerender({ activeChunkId: "4" });
    act(() => vi.advanceTimersByTime(2000));
    rerender({ activeChunkId: "3" }); // back before the 3s window elapsed
    act(() => vi.advanceTimersByTime(2000));
    expect(intervention.complete).not.toHaveBeenCalled();
  });

  it("restarts the confirm window on a second, later departure rather than crediting the earlier one", () => {
    const intervention = fakeIntervention({ current: { intervention_id: "i1", chunk_id: "3" } });
    const { rerender } = renderHook(
      ({ activeChunkId }) => useParagraphPopup({ intervention, activeChunkId }),
      { initialProps: { activeChunkId: "3" } }
    );
    rerender({ activeChunkId: "4" });
    act(() => vi.advanceTimersByTime(2000));
    rerender({ activeChunkId: "3" });
    rerender({ activeChunkId: "5" });
    act(() => vi.advanceTimersByTime(2000));
    expect(intervention.complete).not.toHaveBeenCalled(); // only 2s since the second departure
    act(() => vi.advanceTimersByTime(1000));
    expect(intervention.complete).toHaveBeenCalledTimes(1);
  });

  it("treats activeChunkId becoming null the same as a paragraph change", () => {
    const intervention = fakeIntervention({ current: { intervention_id: "i1", chunk_id: "3" } });
    const { rerender } = renderHook(
      ({ activeChunkId }) => useParagraphPopup({ intervention, activeChunkId }),
      { initialProps: { activeChunkId: "3" } }
    );
    rerender({ activeChunkId: null });
    act(() => vi.advanceTimersByTime(3000));
    expect(intervention.complete).toHaveBeenCalledTimes(1);
  });

  it("does nothing when there is no current intervention", () => {
    const intervention = fakeIntervention({ current: null });
    renderHook(
      ({ activeChunkId }) => useParagraphPopup({ intervention, activeChunkId }),
      { initialProps: { activeChunkId: "3" } }
    );
    act(() => vi.advanceTimersByTime(10_000));
    expect(intervention.complete).not.toHaveBeenCalled();
  });

  it("exposes a collapsed flag that toggles independently of the close timer", () => {
    const intervention = fakeIntervention({ current: { intervention_id: "i1", chunk_id: "3" } });
    const { result, rerender } = renderHook(
      ({ activeChunkId }) => useParagraphPopup({ intervention, activeChunkId }),
      { initialProps: { activeChunkId: "3" } }
    );
    expect(result.current.collapsed).toBe(false);
    act(() => result.current.toggleCollapsed());
    expect(result.current.collapsed).toBe(true);

    rerender({ activeChunkId: "4" });
    act(() => vi.advanceTimersByTime(3000));
    expect(intervention.complete).toHaveBeenCalledTimes(1); // collapsing never pauses the timer
  });
});
