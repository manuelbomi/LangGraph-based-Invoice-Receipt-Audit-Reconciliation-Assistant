import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import type { RunSummary } from "../api/types";
import { RunHistoryList } from "../components/RunHistoryList";

const SEEDED_RUNS: RunSummary[] = [
  {
    id: "r1",
    original_filename: "INV-1001_bright_office_supplies.pdf",
    doc_type: "invoice",
    status: "completed",
    final_status: "posted",
    flagged: false,
    is_duplicate: false,
    created_at: "2026-08-12T10:00:00Z",
    updated_at: "2026-08-12T10:06:00Z",
  },
  {
    id: "r2",
    original_filename: "INV-1006_bright_office_supplies_DUPLICATE.pdf",
    doc_type: "invoice",
    status: "rejected",
    final_status: "rejected",
    flagged: true,
    is_duplicate: true,
    created_at: "2026-08-12T12:00:00Z",
    updated_at: "2026-08-12T12:40:00Z",
  },
  {
    id: "r3",
    original_filename: "FM-778_redwood_facilities.pdf",
    doc_type: "invoice",
    status: "completed",
    final_status: "posted",
    flagged: true,
    is_duplicate: false,
    created_at: "2026-08-14T09:00:00Z",
    updated_at: "2026-08-14T09:15:00Z",
  },
];

function renderWithRouter(ui: React.ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>);
}

describe("RunHistoryList", () => {
  it("renders the seeded example runs with their filenames", () => {
    renderWithRouter(<RunHistoryList runs={SEEDED_RUNS} />);

    expect(screen.getByText(/INV-1001_bright_office_supplies\.pdf/)).toBeInTheDocument();
    expect(screen.getByText(/INV-1006_bright_office_supplies_DUPLICATE\.pdf/)).toBeInTheDocument();
    expect(screen.getByText(/FM-778_redwood_facilities\.pdf/)).toBeInTheDocument();
  });

  it("shows a Clean badge for a completed, unflagged run", () => {
    renderWithRouter(<RunHistoryList runs={[SEEDED_RUNS[0]]} />);
    expect(screen.getByText(/clean/i)).toBeInTheDocument();
  });

  it("shows a Duplicate badge when is_duplicate is true", () => {
    renderWithRouter(<RunHistoryList runs={[SEEDED_RUNS[1]]} />);
    expect(screen.getByText(/duplicate/i)).toBeInTheDocument();
  });

  it("shows a Flagged badge for a completed-but-flagged run", () => {
    renderWithRouter(<RunHistoryList runs={[SEEDED_RUNS[2]]} />);
    expect(screen.getByText(/flagged/i)).toBeInTheDocument();
  });

  it("links each run to its detail page", () => {
    renderWithRouter(<RunHistoryList runs={SEEDED_RUNS} />);

    const links = screen.getAllByRole("link");
    expect(links[0]).toHaveAttribute("href", "/runs/r1");
    expect(links[1]).toHaveAttribute("href", "/runs/r2");
  });

  it("shows an empty state when there are no runs", () => {
    renderWithRouter(<RunHistoryList runs={[]} />);

    expect(screen.getByText(/no documents processed yet/i)).toBeInTheDocument();
  });
});
