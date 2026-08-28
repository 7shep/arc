"use client";

import type {
  Candidate,
  CandidateDetail,
  CandidateNode,
  CandidateQueue,
  CandidateRelationship,
  GraphNode,
} from "@arc/shared";
import { ArrowsMerge, Check, Pencil, X } from "@phosphor-icons/react";
import { useCallback, useState } from "react";
import { api, type CandidateKind } from "@/lib/api";

type EditState = { id: string; label: string; type: string; description: string };
type MergeState = { id: string; targetId: string };

const EMPTY_QUEUE: CandidateQueue = { pendingCount: 0, nodes: [], relationships: [] };

function candidateKey(candidate: Candidate) {
  return `${candidate.kind}:${candidate.id}`;
}

function confidenceLabel(confidence: number | null) {
  return confidence === null ? "No confidence" : `${Math.round(confidence * 100)}% confidence`;
}

function describe(candidate: Candidate) {
  return candidate.kind === "node"
    ? candidate.label
    : `${candidate.sourceNodeLabel ?? "Unknown"} → ${candidate.targetNodeLabel ?? "Unknown"}`;
}

function message(reason: unknown) {
  return reason instanceof Error ? reason.message : "Arc could not complete that review action.";
}

export function GraphReview({
  courseId,
  initialQueue,
  approvedNodes,
  onReviewed,
}: {
  courseId: string;
  initialQueue?: CandidateQueue;
  approvedNodes: GraphNode[];
  onReviewed?: (queue: CandidateQueue) => void | Promise<void>;
}) {
  const [queue, setQueue] = useState<CandidateQueue>(initialQueue ?? EMPTY_QUEUE);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [expanded, setExpanded] = useState("");
  const [detail, setDetail] = useState<CandidateDetail | null>(null);
  const [detailError, setDetailError] = useState("");
  const [edit, setEdit] = useState<EditState | null>(null);
  const [merge, setMerge] = useState<MergeState | null>(null);

  const candidates: Candidate[] = [...queue.nodes, ...queue.relationships];

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const next = await api.candidates(courseId);
      setQueue(next);
      await onReviewed?.(next);
    } catch (reason) {
      setError(message(reason));
    } finally {
      setLoading(false);
    }
  }, [courseId, onReviewed]);

  async function act(candidate: Candidate, label: string, action: () => Promise<unknown>) {
    setBusy(candidateKey(candidate));
    setError("");
    setNotice("");
    try {
      await action();
      setEdit(null);
      setMerge(null);
      setExpanded("");
      setDetail(null);
      setSelected((items) => items.filter((item) => item !== candidateKey(candidate)));
      setNotice(`${describe(candidate)} ${label}.`);
      await refresh();
    } catch (reason) {
      setError(message(reason));
    } finally {
      setBusy("");
    }
  }

  async function toggleDetail(candidate: Candidate) {
    const key = candidateKey(candidate);
    if (expanded === key) {
      setExpanded("");
      setDetail(null);
      return;
    }
    setExpanded(key);
    setDetail(null);
    setDetailError("");
    try {
      setDetail(
        candidate.kind === "node"
          ? await api.nodeCandidate(courseId, candidate.id)
          : await api.relationshipCandidate(courseId, candidate.id),
      );
    } catch (reason) {
      setDetailError(message(reason));
    }
  }

  async function approveSelected() {
    const nodeIds = queue.nodes.filter((node) => selected.includes(candidateKey(node))).map((node) => node.id);
    const relationshipIds = queue.relationships
      .filter((relationship) => selected.includes(candidateKey(relationship)))
      .map((relationship) => relationship.id);
    setBusy("bulk");
    setError("");
    setNotice("");
    try {
      const result = await api.approveCandidates(courseId, { nodeIds, relationshipIds });
      const approved = result.approvedNodeIds.length + result.approvedRelationshipIds.length;
      setNotice(
        result.failures.length
          ? `Approved ${approved} of ${approved + result.failures.length}. ${result.failures[0].reason}`
          : `Approved ${approved} candidate${approved === 1 ? "" : "s"}.`,
      );
      setSelected([]);
      await refresh();
    } catch (reason) {
      setError(message(reason));
    } finally {
      setBusy("");
    }
  }

  function startEdit(candidate: Candidate) {
    setMerge(null);
    setEdit({
      id: candidateKey(candidate),
      label: candidate.kind === "node" ? candidate.label : "",
      type: candidate.type,
      description: candidate.kind === "node" ? (candidate.description ?? "") : "",
    });
  }

  function saveEdit(candidate: Candidate) {
    if (!edit) return;
    const data =
      candidate.kind === "node"
        ? { label: edit.label.trim(), type: edit.type, description: edit.description.trim() || null }
        : { type: edit.type };
    return act(candidate, "updated and kept in review", () =>
      api.editCandidate(courseId, candidate.kind as CandidateKind, candidate.id, data),
    );
  }

  const busyAnywhere = Boolean(busy) || loading;

  return (
    <section className="py-8" aria-busy={loading}>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold tracking-[-0.03em]">Review extracted knowledge</h2>
          <p className="mt-1 text-sm text-[var(--muted)]">
            {queue.pendingCount} candidate{queue.pendingCount === 1 ? "" : "s"} waiting for review. Nothing
            reaches the course graph until you approve it.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <button
            onClick={approveSelected}
            disabled={!selected.length || busyAnywhere}
            className="focus-ring inline-flex h-10 items-center gap-2 bg-[var(--accent)] px-4 text-sm font-medium text-white disabled:opacity-50"
          >
            <Check size={16} /> Approve selected ({selected.length})
          </button>
          <button
            onClick={refresh}
            disabled={busyAnywhere}
            className="focus-ring inline-flex h-10 items-center border border-[var(--line)] bg-white px-4 text-sm font-medium disabled:opacity-50"
          >
            {loading ? "Refreshing..." : "Refresh"}
          </button>
        </div>
      </div>

      {notice && (
        <p role="status" className="mb-4 border-l-2 border-[var(--accent)] bg-white px-4 py-3 text-sm">
          {notice}
        </p>
      )}
      {error && (
        <div role="alert" className="mb-4 border-l-2 border-red-700 bg-white px-4 py-3 text-sm">
          <p className="text-red-700">{error}</p>
          <button onClick={refresh} className="focus-ring mt-2 text-sm font-medium text-[var(--accent)] hover:underline">
            Try again
          </button>
        </div>
      )}

      {loading && !candidates.length && (
        <p className="border border-dashed border-[#bec8c1] bg-white p-6 text-sm text-[var(--muted)]">
          Loading candidates...
        </p>
      )}

      {!candidates.length && !loading ? (
        <div className="grid min-h-44 place-items-center border border-dashed border-[#bec8c1] bg-white p-6 text-center text-sm text-[var(--muted)]">
          No candidates are waiting for review. Process a source to extract new knowledge.
        </div>
      ) : (
        <ul className="border-t border-[var(--line)]">
          {candidates.map((candidate) => {
            const key = candidateKey(candidate);
            const isBusy = busy === key;
            const isOpen = expanded === key;
            return (
              <li key={key} className="border-b border-[var(--line)] bg-white p-4 sm:p-5">
                <div className="flex flex-wrap items-start gap-3 sm:flex-nowrap">
                  <input
                    type="checkbox"
                    className="focus-ring mt-1 h-4 w-4 accent-[var(--accent)]"
                    checked={selected.includes(key)}
                    onChange={(event) =>
                      setSelected((items) =>
                        event.target.checked ? [...items, key] : items.filter((item) => item !== key),
                      )
                    }
                    aria-label={`Select ${describe(candidate)}`}
                  />
                  <div className="min-w-0 flex-1">
                    <p className="font-mono text-[10px] uppercase tracking-[0.08em] text-[var(--muted)]">
                      {candidate.kind === "node" ? "Node" : "Relationship"} · {candidate.type} ·{" "}
                      {candidate.reviewStatus}
                    </p>
                    <button
                      onClick={() => toggleDetail(candidate)}
                      aria-expanded={isOpen}
                      className="focus-ring mt-1 block text-left text-base font-medium hover:text-[var(--accent)]"
                    >
                      {describe(candidate)}
                    </button>
                    {candidate.kind === "node" && candidate.description && (
                      <p className="mt-1 text-sm text-[var(--muted)]">{candidate.description}</p>
                    )}
                    <p className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-[var(--muted)]">
                      <span>{confidenceLabel(candidate.confidence)}</span>
                      <span>{candidate.sourceDocumentName ?? "No source document"}</span>
                      <span>
                        {candidate.evidenceCount} source excerpt
                        {candidate.evidenceCount === 1 ? "" : "s"}
                      </span>
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button
                      onClick={() => act(candidate, "approved", () => api.approveCandidate(courseId, candidate.kind, candidate.id))}
                      disabled={busyAnywhere}
                      className="focus-ring inline-flex h-9 items-center gap-1.5 bg-[var(--accent)] px-3 text-sm font-medium text-white disabled:opacity-50"
                    >
                      <Check size={15} /> {isBusy ? "Working..." : "Approve"}
                    </button>
                    <button
                      onClick={() => act(candidate, "rejected", () => api.rejectCandidate(courseId, candidate.kind, candidate.id))}
                      disabled={busyAnywhere}
                      className="focus-ring inline-flex h-9 items-center gap-1.5 border border-[var(--line)] px-3 text-sm font-medium disabled:opacity-50"
                    >
                      <X size={15} /> Reject
                    </button>
                    <button
                      onClick={() => startEdit(candidate)}
                      disabled={busyAnywhere}
                      className="focus-ring inline-flex h-9 items-center gap-1.5 border border-[var(--line)] px-3 text-sm font-medium disabled:opacity-50"
                    >
                      <Pencil size={15} /> Edit
                    </button>
                    {candidate.kind === "node" && (
                      <button
                        onClick={() => {
                          setEdit(null);
                          setMerge({ id: key, targetId: approvedNodes[0]?.id ?? "" });
                        }}
                        disabled={busyAnywhere || !approvedNodes.length}
                        className="focus-ring inline-flex h-9 items-center gap-1.5 border border-[var(--line)] px-3 text-sm font-medium disabled:opacity-50"
                      >
                        <ArrowsMerge size={15} /> Merge
                      </button>
                    )}
                  </div>
                </div>

                {edit?.id === key && (
                  <form
                    onSubmit={(event) => {
                      event.preventDefault();
                      void saveEdit(candidate);
                    }}
                    className="mt-4 grid gap-3 border-l-2 border-[var(--accent)] bg-[var(--paper)] p-4 sm:grid-cols-2"
                  >
                    {candidate.kind === "node" && (
                      <label className="text-sm font-medium">
                        Name
                        <input
                          value={edit.label}
                          onChange={(event) => setEdit({ ...edit, label: event.target.value })}
                          required
                          className="focus-ring mt-2 h-10 w-full border border-[var(--line)] bg-white px-3 text-sm font-normal"
                        />
                      </label>
                    )}
                    <label className="text-sm font-medium">
                      Type
                      <input
                        value={edit.type}
                        onChange={(event) => setEdit({ ...edit, type: event.target.value.toUpperCase() })}
                        className="focus-ring mt-2 h-10 w-full border border-[var(--line)] bg-white px-3 text-sm font-normal"
                      />
                    </label>
                    {candidate.kind === "node" && (
                      <label className="text-sm font-medium sm:col-span-2">
                        Description
                        <textarea
                          value={edit.description}
                          onChange={(event) => setEdit({ ...edit, description: event.target.value })}
                          rows={2}
                          className="focus-ring mt-2 w-full border border-[var(--line)] bg-white p-3 text-sm font-normal"
                        />
                      </label>
                    )}
                    <div className="flex gap-2 sm:col-span-2">
                      <button
                        disabled={busyAnywhere}
                        className="focus-ring h-10 bg-[var(--ink)] px-4 text-sm font-medium text-white disabled:opacity-50"
                      >
                        Save changes
                      </button>
                      <button
                        type="button"
                        onClick={() => setEdit(null)}
                        className="focus-ring h-10 border border-[var(--line)] bg-white px-4 text-sm font-medium"
                      >
                        Cancel
                      </button>
                    </div>
                  </form>
                )}

                {merge?.id === key && candidate.kind === "node" && (
                  <form
                    onSubmit={(event) => {
                      event.preventDefault();
                      void act(candidate, "merged", () =>
                        api.mergeCandidate(courseId, "node", candidate.id, merge.targetId),
                      );
                    }}
                    className="mt-4 grid gap-3 border-l-2 border-[var(--accent)] bg-[var(--paper)] p-4 sm:grid-cols-[1fr_auto_auto] sm:items-end"
                  >
                    <label className="text-sm font-medium">
                      Merge into existing node
                      <select
                        value={merge.targetId}
                        onChange={(event) => setMerge({ ...merge, targetId: event.target.value })}
                        className="focus-ring mt-2 h-10 w-full border border-[var(--line)] bg-white px-3 text-sm font-normal"
                      >
                        {approvedNodes.map((node) => (
                          <option key={node.id} value={node.id}>
                            {node.label}
                          </option>
                        ))}
                      </select>
                    </label>
                    <button
                      disabled={busyAnywhere || !merge.targetId}
                      className="focus-ring h-10 bg-[var(--ink)] px-4 text-sm font-medium text-white disabled:opacity-50"
                    >
                      Merge
                    </button>
                    <button
                      type="button"
                      onClick={() => setMerge(null)}
                      className="focus-ring h-10 border border-[var(--line)] bg-white px-4 text-sm font-medium"
                    >
                      Cancel
                    </button>
                  </form>
                )}

                {isOpen && (
                  <div className="mt-4 border-t border-[var(--line)] pt-4">
                    {detailError && (
                      <p role="alert" className="text-sm text-red-700">
                        {detailError}
                      </p>
                    )}
                    {!detail && !detailError && (
                      <p className="text-sm text-[var(--muted)]">Loading source excerpts...</p>
                    )}
                    {detail && (
                      <div className="grid gap-4 lg:grid-cols-2">
                        <div>
                          <h3 className="text-xs font-medium uppercase tracking-[0.08em] text-[var(--muted)]">
                            Source excerpts
                          </h3>
                          {detail.evidence.length ? (
                            <ul className="mt-2 space-y-3">
                              {detail.evidence.map((evidence) => (
                                <li key={evidence.id} className="border-l-2 border-[var(--line)] pl-3">
                                  <p className="text-sm">{evidence.excerpt}</p>
                                  <p className="mt-1 font-mono text-[11px] text-[var(--muted)]">
                                    {evidence.documentName}
                                    {evidence.page !== null && ` · page ${evidence.page}`}
                                    {evidence.section && ` · ${evidence.section}`}
                                    {` · ${confidenceLabel(evidence.confidence)}`}
                                  </p>
                                </li>
                              ))}
                            </ul>
                          ) : (
                            <p className="mt-2 text-sm text-[var(--muted)]">No source excerpts recorded.</p>
                          )}
                        </div>
                        <div>
                          <h3 className="text-xs font-medium uppercase tracking-[0.08em] text-[var(--muted)]">
                            Related graph nodes
                          </h3>
                          {detail.relatedNodes.length ? (
                            <ul className="mt-2 space-y-2 text-sm">
                              {detail.relatedNodes.map((node) => (
                                <li key={node.id}>
                                  {node.label}{" "}
                                  <span className="font-mono text-[11px] text-[var(--muted)]">{node.type}</span>
                                </li>
                              ))}
                            </ul>
                          ) : (
                            <p className="mt-2 text-sm text-[var(--muted)]">
                              Nothing in the approved graph looks related yet.
                            </p>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

export type { CandidateNode, CandidateRelationship };
