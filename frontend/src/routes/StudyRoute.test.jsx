/**
 * `/study` is where Module 2 (a document), Module 3 (the camera) and Module 4
 * (support that needs to know the active chunk) meet. The one thing this route
 * does is hand `StudySession` the right `contentId`, and every content-driven
 * feature is dormant if it does not, so that is what these tests pin.
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Link, MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

const sessionProps = vi.fn();
const mounts = vi.fn();
vi.mock("../pages/StudySession", async () => {
  const React = await vi.importActual("react");
  return {
    default: (props) => {
      React.useEffect(() => {
        mounts();
      }, []);
      sessionProps(props);
      return <p>session for {String(props.contentId)}</p>;
    },
  };
});

import StudyRoute from "./StudyRoute";

function at(url) {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <Routes>
        <Route path="/study" element={<StudyRoute />} />
        <Route path="/library" element={<p>library</p>} />
      </Routes>
    </MemoryRouter>
  );
}

describe("/study", () => {
  it("passes the document in the address to the session", () => {
    sessionProps.mockClear();
    at("/study?content=doc-42");
    expect(screen.getByText("session for doc-42")).toBeTruthy();
    expect(sessionProps.mock.calls.at(-1)[0].contentId).toBe("doc-42");
  });

  it("decodes an id that was encoded on the way in", () => {
    at("/study?content=abc%20123");
    expect(sessionProps.mock.calls.at(-1)[0].contentId).toBe("abc 123");
  });

  it("asks what to study rather than silently starting a camera-only session", () => {
    // Someone arriving from the nav almost certainly meant to study something.
    at("/study");
    expect(screen.getByText(/what would you like to study/i)).toBeTruthy();
    expect(screen.queryByText(/^session for/)).toBeNull();
    expect(screen.getByRole("link", { name: /choose a document/i }).getAttribute("href")).toBe(
      "/library"
    );
  });

  it("still allows a session with no document, and says what that costs", async () => {
    const user = userEvent.setup();
    at("/study");
    expect(screen.getByText(/nothing to simplify or summarise/i)).toBeTruthy();

    await user.click(screen.getByRole("button", { name: /start without a document/i }));
    expect(screen.getByText("session for undefined")).toBeTruthy();
    expect(sessionProps.mock.calls.at(-1)[0].contentId).toBeUndefined();
  });

  it("remounts the session when the document changes", async () => {
    // Otherwise dwell, the active chunk and capture state from the previous
    // document leak into the next one. Uses one router and navigates, because
    // that is what a learner switching documents actually does.
    const user = userEvent.setup();
    mounts.mockClear();
    render(
      <MemoryRouter initialEntries={["/study?content=a"]}>
        <Routes>
          <Route
            path="/study"
            element={
              <>
                <Link to="/study?content=b">switch</Link>
                <StudyRoute />
              </>
            }
          />
        </Routes>
      </MemoryRouter>
    );
    expect(mounts).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole("link", { name: "switch" }));
    expect(screen.getByText("session for b")).toBeTruthy();
    expect(mounts).toHaveBeenCalledTimes(2);
  });
});
