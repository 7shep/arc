import type { CandidateNode, CandidateQueue, CandidateRelationship, GraphNode } from "@arc/shared";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { GraphReview } from "./graph-review";

const { api } = vi.hoisted(() => ({
  api: {
    candidates: vi.fn(),
    nodeCandidate: vi.fn(),
    relationshipCandidate: vi.fn(),
    approveCandidate: vi.fn(),
    rejectCandidate: vi.fn(),
    editCandidate: vi.fn(),
    mergeCandidate: vi.fn(),
    approveCandidates: vi.fn(),
  },
}));

vi.mock("@/lib/api", () => ({ api }));

const nodeCandidate: CandidateNode = {
  kind: "node",
  id: "node-1",
  courseId: "course-1",
  type: "CONCEPT",
  label: "Green's theorem",
  description: "Relates a line integral to a double integral.",
  confidence: 0.82,
  reviewStatus: "PENDING",
  reviewNote: null,
  reviewedAt: null,
  mergedIntoNodeId: null,
  sourceDocumentId: "doc-1",
  sourceDocumentName: "lecture-07.pdf",
  metadata: {},
  evidenceCount: 1,
  createdAt: "2026-08-01T10:00:00Z",
  updatedAt: "2026-08-01T10:00:00Z",
};

const relationshipCandidate: CandidateRelationship = {
  kind: "relationship",
  id: "edge-1",
  courseId: "course-1",
  type: "REQUIRES",
  sourceNodeId: "node-1",
  targetNodeId: "node-2",
  sourceNodeLabel: "Green's theorem",
  targetNodeLabel: "Line integrals",
  mergedIntoEdgeId: null,
  confidence: 0.61,
  reviewStatus: "PENDING",
  reviewNote: null,
  reviewedAt: null,
  sourceDocumentId: "doc-1",
  sourceDocumentName: "lecture-07.pdf",
  metadata: {},
  evidenceCount: 2,
  createdAt: "2026-08-01T10:00:00Z",
  updatedAt: "2026-08-01T10:00:00Z",
};

const approvedNode: GraphNode = {
  id: "node-2",
  courseId: "course-1",
  type: "CONCEPT",
  label: "Line integrals",
  description: null,
  sourceDocumentId: null,
  sourceLocation: null,
  confidence: null,
  reviewStatus: "APPROVED",
  metadata: {},
  createdAt: "2026-08-01T10:00:00Z",
  updatedAt: "2026-08-01T10:00:00Z",
};

const queue: CandidateQueue = {
  pendingCount: 2,
  nodes: [nodeCandidate],
  relationships: [relationshipCandidate],
};

const emptyQueue: CandidateQueue = { pendingCount: 0, nodes: [], relationships: [] };

function renderReview(initialQueue: CandidateQueue = queue) {
  return render(
    <GraphReview courseId="course-1" initialQueue={initialQueue} approvedNodes={[approvedNode]} />,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  api.candidates.mockResolvedValue(emptyQueue);
});

describe("GraphReview", () => {
  it("renders the pending count, candidate details, and source metadata", () => {
    renderReview();

    expect(screen.getByText(/2 candidates waiting for review/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Green's theorem" })).toBeInTheDocument();
    expect(screen.getByText(/Relates a line integral to a double integral\./)).toBeInTheDocument();
    expect(screen.getByText(/Node · CONCEPT · PENDING/)).toBeInTheDocument();
    expect(screen.getAllByText(/82% confidence/)).not.toHaveLength(0);
    expect(screen.getAllByText("lecture-07.pdf")).toHaveLength(2);
    expect(
      screen.getByRole("button", { name: "Green's theorem → Line integrals" }),
    ).toBeInTheDocument();
  });

  it("shows the empty state when nothing is waiting for review", () => {
    renderReview(emptyQueue);
    expect(screen.getByText(/No candidates are waiting for review/i)).toBeInTheDocument();
  });

  it("loads source excerpts and related nodes when a candidate is opened", async () => {
    api.nodeCandidate.mockResolvedValue({
      candidate: nodeCandidate,
      evidence: [
        {
          id: "evidence-1",
          documentId: "doc-1",
          documentName: "lecture-07.pdf",
          documentType: "LECTURE",
          page: 4,
          section: "Statement",
          sourceLocation: { page: 4 },
          excerpt: "Green's theorem relates a line integral around a simple closed curve.",
          confidence: 0.82,
          createdAt: "2026-08-01T10:00:00Z",
        },
      ],
      relatedNodes: [approvedNode],
    });

    const user = userEvent.setup();
    renderReview();
    await user.click(screen.getByRole("button", { name: "Green's theorem" }));

    expect(await screen.findByText(/relates a line integral around a simple closed curve/i)).toBeInTheDocument();
    expect(screen.getByText(/page 4 · Statement/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /related graph nodes/i })).toBeInTheDocument();
    expect(api.nodeCandidate).toHaveBeenCalledWith("course-1", "node-1");
  });

  it("approves a candidate, reports success, and refreshes the queue", async () => {
    api.approveCandidate.mockResolvedValue(nodeCandidate);
    const onReviewed = vi.fn();
    const user = userEvent.setup();
    render(
      <GraphReview
        courseId="course-1"
        initialQueue={queue}
        approvedNodes={[approvedNode]}
        onReviewed={onReviewed}
      />,
    );

    await user.click(screen.getAllByRole("button", { name: /approve$/i })[0]);

    expect(api.approveCandidate).toHaveBeenCalledWith("course-1", "node", "node-1");
    expect(await screen.findByRole("status")).toHaveTextContent("Green's theorem approved.");
    await waitFor(() => expect(api.candidates).toHaveBeenCalledWith("course-1"));
    await waitFor(() => expect(onReviewed).toHaveBeenCalledWith(emptyQueue));
    expect(await screen.findByText(/No candidates are waiting for review/i)).toBeInTheDocument();
  });

  it("rejects a candidate", async () => {
    api.rejectCandidate.mockResolvedValue(nodeCandidate);
    const user = userEvent.setup();
    renderReview();

    await user.click(screen.getAllByRole("button", { name: /reject/i })[0]);

    expect(api.rejectCandidate).toHaveBeenCalledWith("course-1", "node", "node-1");
    expect(await screen.findByRole("status")).toHaveTextContent("rejected");
  });

  it("edits a candidate and keeps it in review", async () => {
    api.editCandidate.mockResolvedValue(nodeCandidate);
    const user = userEvent.setup();
    renderReview();

    await user.click(screen.getAllByRole("button", { name: /edit/i })[0]);
    const name = screen.getByLabelText(/name/i);
    await user.clear(name);
    await user.type(name, "Green theorem");
    await user.click(screen.getByRole("button", { name: /save changes/i }));

    expect(api.editCandidate).toHaveBeenCalledWith("course-1", "node", "node-1", {
      label: "Green theorem",
      type: "CONCEPT",
      description: "Relates a line integral to a double integral.",
    });
  });

  it("merges a candidate into an existing node", async () => {
    api.mergeCandidate.mockResolvedValue({});
    const user = userEvent.setup();
    renderReview();

    await user.click(screen.getAllByRole("button", { name: "Merge" })[0]);
    expect(screen.getByLabelText(/merge into existing node/i)).toHaveValue("node-2");
    await user.click(screen.getAllByRole("button", { name: "Merge" })[1]);

    expect(api.mergeCandidate).toHaveBeenCalledWith("course-1", "node", "node-1", "node-2");
  });

  it("approves selected candidates in bulk and surfaces partial failures", async () => {
    api.approveCandidates.mockResolvedValue({
      approvedNodeIds: ["node-1"],
      approvedRelationshipIds: [],
      failures: [{ id: "edge-1", kind: "relationship", reason: "Approve both connected nodes first" }],
    });
    const user = userEvent.setup();
    renderReview();

    const bulk = screen.getByRole("button", { name: /approve selected/i });
    expect(bulk).toBeDisabled();

    await user.click(screen.getByRole("checkbox", { name: "Select Green's theorem" }));
    await user.click(
      screen.getByRole("checkbox", { name: "Select Green's theorem → Line integrals" }),
    );
    await user.click(bulk);

    expect(api.approveCandidates).toHaveBeenCalledWith("course-1", {
      nodeIds: ["node-1"],
      relationshipIds: ["edge-1"],
    });
    expect(await screen.findByRole("status")).toHaveTextContent(
      "Approved 1 of 2. Approve both connected nodes first",
    );
  });

  it("shows a retryable error when a review action fails", async () => {
    api.approveCandidate.mockRejectedValue(new Error("An approved node already uses this label"));
    const user = userEvent.setup();
    renderReview();

    await user.click(screen.getAllByRole("button", { name: /approve$/i })[0]);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("An approved node already uses this label");
    expect(screen.getByRole("button", { name: "Green's theorem" })).toBeInTheDocument();

    api.candidates.mockResolvedValue(queue);
    await user.click(within(alert).getByRole("button", { name: /try again/i }));
    await waitFor(() => expect(api.candidates).toHaveBeenCalled());
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("disables merging when the course graph has no approved nodes", () => {
    render(<GraphReview courseId="course-1" initialQueue={queue} approvedNodes={[]} />);
    expect(screen.getByRole("button", { name: "Merge" })).toBeDisabled();
  });

  it("keeps candidate rows readable on a mobile viewport", () => {
    window.innerWidth = 375;
    const { container } = renderReview();
    const row = container.querySelector("li > div");
    expect(row?.className).toContain("flex-wrap");
    expect(row?.className).toContain("sm:flex-nowrap");
    expect(container.querySelector("section")?.className).not.toContain("min-w-[");
  });
});
