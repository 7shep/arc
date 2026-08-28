import type { CourseDocument, DocumentGraph } from "@arc/shared";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CourseSources, stageOf } from "./course-sources";

const { api } = vi.hoisted(() => ({
  api: { processDocument: vi.fn(), extractDocument: vi.fn(), documentGraph: vi.fn() },
}));

vi.mock("@/lib/api", () => ({ api }));

const base: CourseDocument = {
  id: "doc-1",
  courseId: "course-1",
  filename: "stored.md",
  originalFilename: "lecture-07.md",
  documentType: "LECTURE",
  mimeType: "text/markdown",
  storagePath: "stored.md",
  processingStatus: "READY",
  processingError: null,
  extractionStatus: "COMPLETED",
  extractionError: null,
  extractedAt: "2026-08-01T10:05:00Z",
  chunkCount: 4,
  createdAt: "2026-08-01T10:00:00Z",
  updatedAt: "2026-08-01T10:00:00Z",
};

const uploading: CourseDocument = {
  ...base,
  id: "doc-2",
  originalFilename: "week-5.pdf",
  processingStatus: "UPLOADED",
  extractionStatus: "NOT_STARTED",
  extractedAt: null,
  chunkCount: 0,
};

const documentGraph: DocumentGraph = {
  documentId: "doc-1",
  chunkCount: 4,
  pendingCandidateCount: 0,
  nodes: [
    {
      id: "node-1",
      courseId: "course-1",
      type: "CONCEPT",
      label: "Cyclic group",
      description: null,
      sourceDocumentId: "doc-1",
      sourceLocation: null,
      confidence: 0.9,
      reviewStatus: "APPROVED",
      metadata: {},
      createdAt: "2026-08-01T10:00:00Z",
      updatedAt: "2026-08-01T10:00:00Z",
    },
  ],
  edges: [],
};

beforeEach(() => vi.clearAllMocks());

describe("stageOf", () => {
  it("describes each point of the automatic pipeline", () => {
    expect(stageOf(uploading).label).toBe("Reading document");
    expect(stageOf(uploading).busy).toBe(true);
    expect(stageOf({ ...base, extractionStatus: "RUNNING" }).label).toBe("Building graph");
    expect(stageOf(base).label).toBe("In graph");
    expect(stageOf(base).busy).toBe(false);
    expect(stageOf({ ...base, extractionStatus: "UNAVAILABLE" }).label).toBe(
      "No extraction agent",
    );
    expect(stageOf({ ...base, processingStatus: "FAILED" }).label).toBe("Could not read file");
  });
});

describe("CourseSources", () => {
  it("shows automatic progress without asking the user to process anything", () => {
    render(<CourseSources courseId="course-1" documents={[base, uploading]} />);

    expect(screen.getByText("In graph")).toBeInTheDocument();
    expect(screen.getByText("Reading document...")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^process$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /retry/i })).not.toBeInTheDocument();
  });

  it("shows the empty state when no sources exist", () => {
    render(<CourseSources courseId="course-1" documents={[]} />);
    expect(screen.getByText(/build the graph automatically/i)).toBeInTheDocument();
  });

  it("explains a missing agent and links to settings", () => {
    render(
      <CourseSources
        courseId="course-1"
        documents={[
          {
            ...base,
            extractionStatus: "UNAVAILABLE",
            extractionError: "claude is not installed or not on PATH",
          },
        ]}
      />,
    );

    expect(screen.getByText(/1 source did not make it into the graph/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /review your extraction agent/i })).toHaveAttribute(
      "href",
      "/settings",
    );
    expect(screen.getByRole("alert")).toHaveTextContent("not installed");
  });

  it("retries extraction for a failed source", async () => {
    const failed = { ...base, extractionStatus: "FAILED" as const, extractionError: "rate limited" };
    api.extractDocument.mockResolvedValue({ ...base });
    const onDocumentChanged = vi.fn();
    const user = userEvent.setup();
    render(
      <CourseSources
        courseId="course-1"
        documents={[failed]}
        onDocumentChanged={onDocumentChanged}
      />,
    );

    await user.click(screen.getByRole("button", { name: /retry/i }));

    expect(api.extractDocument).toHaveBeenCalledWith("course-1", "doc-1");
    await waitFor(() => expect(onDocumentChanged).toHaveBeenCalled());
  });

  it("reprocesses a source that could not be read", async () => {
    api.processDocument.mockResolvedValue({ ...base });
    const user = userEvent.setup();
    render(
      <CourseSources
        courseId="course-1"
        documents={[{ ...base, processingStatus: "FAILED", processingError: "Unreadable" }]}
      />,
    );

    await user.click(screen.getByRole("button", { name: /retry/i }));
    expect(api.processDocument).toHaveBeenCalledWith("course-1", "doc-1");
  });

  it("reports a failed retry", async () => {
    api.extractDocument.mockRejectedValue(new Error("Agent is still unavailable"));
    const user = userEvent.setup();
    render(
      <CourseSources
        courseId="course-1"
        documents={[{ ...base, extractionStatus: "FAILED", extractionError: "rate limited" }]}
      />,
    );

    await user.click(screen.getByRole("button", { name: /retry/i }));
    await waitFor(() =>
      expect(screen.getAllByRole("alert").some((node) => node.textContent?.includes("still unavailable"))).toBe(true),
    );
  });

  it("lists the graph records that came from a source", async () => {
    api.documentGraph.mockResolvedValue(documentGraph);
    const user = userEvent.setup();
    render(<CourseSources courseId="course-1" documents={[base]} />);

    await user.click(screen.getByRole("button", { name: /graph records/i }));

    expect(await screen.findByText(/1 node and 0 relationships/i)).toBeInTheDocument();
    expect(screen.getByText("Cyclic group")).toBeInTheDocument();
    expect(api.documentGraph).toHaveBeenCalledWith("course-1", "doc-1");
  });

  it("keeps source rows readable on a mobile viewport", () => {
    const { container } = render(<CourseSources courseId="course-1" documents={[base]} />);
    const row = container.querySelector("li > div");
    expect(row?.className).toContain("flex-wrap");
    expect(container.querySelector("[class*='min-w-[']")).toBeNull();
  });
});
