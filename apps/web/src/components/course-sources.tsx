"use client";

import type { CourseDocument, DocumentGraph } from "@arc/shared";
import { FileText, Graph, Lightning } from "@phosphor-icons/react";
import { useState } from "react";
import { api } from "@/lib/api";

const STATUS_STYLES: Record<CourseDocument["processingStatus"], string> = {
  UPLOADED: "border-[#c9d2cb] bg-[var(--paper)] text-[var(--muted)]",
  PROCESSING: "border-[#c9d2cb] bg-[var(--paper)] text-[var(--muted)]",
  READY: "border-[#9bc8b4] bg-[#eef8f3] text-[#075b40]",
  FAILED: "border-[#e0b4b4] bg-[#fbf0f0] text-[#8a2020]",
};

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(value));
}

export function CourseSources({
  courseId,
  documents,
  onDocumentProcessed,
}: {
  courseId: string;
  documents: CourseDocument[];
  onDocumentProcessed?: (document: CourseDocument) => void | Promise<void>;
}) {
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [expanded, setExpanded] = useState("");
  const [records, setRecords] = useState<DocumentGraph | null>(null);
  const [recordsError, setRecordsError] = useState("");

  const unprocessed = documents.filter((item) => item.processingStatus !== "READY");

  async function process(document: CourseDocument) {
    setBusy(document.id);
    setError("");
    setNotice("");
    try {
      const processed = await api.processDocument(courseId, document.id);
      setNotice(`${document.originalFilename} processed into ${processed.chunkCount} chunks.`);
      await onDocumentProcessed?.(processed);
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Arc could not process that source.",
      );
    } finally {
      setBusy("");
    }
  }

  async function toggleRecords(document: CourseDocument) {
    if (expanded === document.id) {
      setExpanded("");
      setRecords(null);
      return;
    }
    setExpanded(document.id);
    setRecords(null);
    setRecordsError("");
    try {
      setRecords(await api.documentGraph(courseId, document.id));
    } catch (reason) {
      setRecordsError(
        reason instanceof Error ? reason.message : "Arc could not load graph records.",
      );
    }
  }

  if (!documents.length) {
    return (
      <div className="grid min-h-44 place-items-center border border-dashed border-[#bec8c1] bg-white p-6 text-center text-sm text-[var(--muted)]">
        No sources uploaded. Add lecture notes, readings, assignments, or tutorials.
      </div>
    );
  }

  return (
    <div>
      <p className="mb-3 text-sm text-[var(--muted)]">
        {unprocessed.length
          ? `${unprocessed.length} of ${documents.length} sources still need processing before they can be extracted.`
          : "Every source has been processed into chunks."}
      </p>
      {notice && (
        <p role="status" className="mb-4 border-l-2 border-[var(--accent)] bg-white px-4 py-3 text-sm">
          {notice}
        </p>
      )}
      {error && (
        <p role="alert" className="mb-4 border-l-2 border-red-700 bg-white px-4 py-3 text-sm text-red-700">
          {error}
        </p>
      )}
      <ul className="border-t border-[var(--line)]">
        {documents.map((document) => (
          <li key={document.id} className="border-b border-[var(--line)] bg-white p-4 sm:p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <span className="inline-flex items-center gap-2 font-medium">
                  <FileText size={17} className="text-[var(--accent)]" />
                  {document.originalFilename}
                </span>
                <p className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[11px] text-[var(--muted)]">
                  <span>{document.documentType}</span>
                  <span
                    className={`border px-2 py-0.5 text-[10px] ${STATUS_STYLES[document.processingStatus]}`}
                  >
                    {document.processingStatus}
                  </span>
                  <span>
                    {document.chunkCount} chunk{document.chunkCount === 1 ? "" : "s"}
                  </span>
                  <span>{formatDate(document.createdAt)}</span>
                </p>
                {document.processingError && (
                  <p role="alert" className="mt-2 text-sm text-red-700">
                    {document.processingError}
                  </p>
                )}
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  onClick={() => process(document)}
                  disabled={Boolean(busy)}
                  className="focus-ring inline-flex h-9 items-center gap-1.5 border border-[var(--line)] px-3 text-sm font-medium disabled:opacity-50"
                >
                  <Lightning size={15} />
                  {busy === document.id
                    ? "Processing..."
                    : document.processingStatus === "READY"
                      ? "Reprocess"
                      : "Process"}
                </button>
                <button
                  onClick={() => toggleRecords(document)}
                  aria-expanded={expanded === document.id}
                  className="focus-ring inline-flex h-9 items-center gap-1.5 border border-[var(--line)] px-3 text-sm font-medium"
                >
                  <Graph size={15} /> Graph records
                </button>
              </div>
            </div>

            {expanded === document.id && (
              <div className="mt-4 border-t border-[var(--line)] pt-4 text-sm">
                {recordsError && (
                  <p role="alert" className="text-red-700">
                    {recordsError}
                  </p>
                )}
                {!records && !recordsError && (
                  <p className="text-[var(--muted)]">Loading graph records...</p>
                )}
                {records && (
                  <div>
                    <p className="text-[var(--muted)]">
                      {records.nodes.length} approved node
                      {records.nodes.length === 1 ? "" : "s"} and {records.edges.length} relationship
                      {records.edges.length === 1 ? "" : "s"} came from this source.
                      {records.pendingCandidateCount > 0 &&
                        ` ${records.pendingCandidateCount} candidate${records.pendingCandidateCount === 1 ? "" : "s"} still waiting for review.`}
                    </p>
                    {records.nodes.length ? (
                      <ul className="mt-2 space-y-1">
                        {records.nodes.map((node) => (
                          <li key={node.id}>
                            {node.label}{" "}
                            <span className="font-mono text-[11px] text-[var(--muted)]">
                              {node.type}
                            </span>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="mt-2 text-[var(--muted)]">
                        No approved graph records reference this source yet.
                      </p>
                    )}
                  </div>
                )}
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
