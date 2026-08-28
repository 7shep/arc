import type { CourseDocument, DocumentGraph } from "@arc/shared";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CourseSources } from "./course-sources";

const { api } = vi.hoisted(() => ({
  api: { processDocument: vi.fn(), documentGraph: vi.fn() },
}));

vi.mock("@/lib/api", () => ({ api }));

const uploaded: CourseDocument = {
  id: "doc-1",
  courseId: "course-1",
  filename: "stored.md",
  originalFilename: "lecture-07.md",
  documentType: "LECTURE",
  mimeType: "text/markdown",
  storagePath: "stored.md",
  processingStatus: "UPLOADED",
  processingError: null,
  chunkCount: 0,
  createdAt: "2026-08-01T10:00:00Z",
  updatedAt: "2026-08-01T10:00:00Z",
};

const ready: CourseDocument = {
  ...uploaded,
  id: "doc-2",
  originalFilename: "reading-02.md",
  processingStatus: "READY",
  chunkCount: 4,
};

const documentGraph: DocumentGraph = {
  documentId: "doc-2",
  chunkCount: 4,
  pendingCandidateCount: 1,
  nodes: [
    {
      id: "node-1",
      courseId: "course-1",
      type: "CONCEPT",
      label: "Green's theorem",
      description: null,
      sourceDocumentId: "doc-2",
      sourceLocation: null,
      confidence: 0.86,
      reviewStatus: "APPROVED",
      metadata: {},
      createdAt: "2026-08-01T10:00:00Z",
      updatedAt: "2026-08-01T10:00:00Z",
    },
  ],
  edges: [],
};

beforeEach(() => vi.clearAllMocks());

describe("CourseSources", () => {
  it("shows how many sources still need processing", () => {
    render(<CourseSources courseId="course-1" documents={[uploaded, ready]} />);
    expect(
      screen.getByText(/1 of 2 sources still need processing/i),
    ).toBeInTheDocument();
    expect(screen.getByText("UPLOADED")).toBeInTheDocument();
    expect(screen.getByText("4 chunks")).toBeInTheDocument();
  });

  it("shows the empty state when no sources exist", () => {
    render(<CourseSources courseId="course-1" documents={[]} />);
    expect(screen.getByText(/No sources uploaded/i)).toBeInTheDocument();
  });

  it("processes a source and reports the resulting chunks", async () => {
    api.processDocument.mockResolvedValue({ ...uploaded, processingStatus: "READY", chunkCount: 3 });
    const onDocumentProcessed = vi.fn();
    const user = userEvent.setup();
    render(
      <CourseSources
        courseId="course-1"
        documents={[uploaded]}
        onDocumentProcessed={onDocumentProcessed}
      />,
    );

    await user.click(screen.getByRole("button", { name: /^process$/i }));

    expect(api.processDocument).toHaveBeenCalledWith("course-1", "doc-1");
    expect(await screen.findByRole("status")).toHaveTextContent(
      "lecture-07.md processed into 3 chunks.",
    );
    await waitFor(() => expect(onDocumentProcessed).toHaveBeenCalled());
  });

  it("reports a processing failure", async () => {
    api.processDocument.mockRejectedValue(
      new Error("Document processing failed: Document did not contain extractable text"),
    );
    const user = userEvent.setup();
    render(<CourseSources courseId="course-1" documents={[uploaded]} />);

    await user.click(screen.getByRole("button", { name: /^process$/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("extractable text");
  });

  it("surfaces a stored processing error on the row", () => {
    render(
      <CourseSources
        courseId="course-1"
        documents={[{ ...uploaded, processingStatus: "FAILED", processingError: "Unreadable file" }]}
      />,
    );
    expect(screen.getByText("FAILED")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Unreadable file");
    expect(screen.getByRole("button", { name: /^process$/i })).toBeInTheDocument();
  });

  it("lists the approved graph records that came from a source", async () => {
    api.documentGraph.mockResolvedValue(documentGraph);
    const user = userEvent.setup();
    render(<CourseSources courseId="course-1" documents={[ready]} />);

    await user.click(screen.getByRole("button", { name: /graph records/i }));

    expect(await screen.findByText(/1 approved node and 0 relationships/i)).toBeInTheDocument();
    expect(screen.getByText(/1 candidate still waiting for review/i)).toBeInTheDocument();
    expect(screen.getByText("Green's theorem")).toBeInTheDocument();
    expect(api.documentGraph).toHaveBeenCalledWith("course-1", "doc-2");
  });

  it("keeps source rows readable on a mobile viewport", () => {
    const { container } = render(<CourseSources courseId="course-1" documents={[ready]} />);
    const row = container.querySelector("li > div");
    expect(row?.className).toContain("flex-wrap");
    expect(container.querySelector("[class*='min-w-[']")).toBeNull();
  });
});
