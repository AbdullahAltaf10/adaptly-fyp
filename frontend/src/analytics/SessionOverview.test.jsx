import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import SessionOverview from "./SessionOverview";

describe("SessionOverview content line", () => {
  it("labels a camera-only session as having no document instead of showing 'Not available'", () => {
    render(
      <SessionOverview
        overview={{ session_status: "completed" }}
        summary={{ content_id: null, completed_at: "2026-10-04T10:00:00Z", duration_seconds: 60 }}
      />
    );
    expect(screen.getByText("Camera only (no document)")).toBeInTheDocument();
    expect(screen.getByText("Content").nextElementSibling).toHaveTextContent("Camera only (no document)");
  });

  it("shows the document title when there is one", () => {
    render(
      <SessionOverview
        overview={{ session_status: "completed", content_title: "Biology notes" }}
        summary={{ content_id: "c1", completed_at: "2026-10-04T10:00:00Z", duration_seconds: 60 }}
      />
    );
    expect(screen.getByText("Biology notes")).toBeInTheDocument();
  });
});
