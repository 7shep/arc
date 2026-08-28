"use client";

import type { CourseDocument, DocumentGraph, ExtractionStatus } from "@arc/shared";
import { ArrowClockwise, FileText, Graph } from "@phosphor-icons/react";
import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";

const NEUTRAL = "border-[#c9d2cb] bg-[var(--paper)] text-[var(--muted)]";
const GOOD = "border-[#9bc8b4] bg-[#eef8f3] text-[#075b40]";
const BAD = "border-[#e0b4b4] bg-[#fbf0f0] text-[#8a2020]";

type Stage = { label: string; tone: string; busy: boolean };

export function stageOf(document: CourseDocument): Stage {
  if (document.processingStatus === "FAILED")
    return { label: "Could not read file", tone: BAD, busy: false };
  if (document.processingStatus !== "READY")
    return { label: "Reading document", tone: NEUTRAL, busy: true };
  const extraction: Record<ExtractionStatus, Stage> = {
    NOT_STARTED: { label: "Waiting to build graph", tone: NEUTRAL, busy: true },
    RUNNING: { label: "Building graph", tone: NEUTRAL, busy: true },
    COMPLETED: { label: "In graph", tone: GOOD, busy: false },
    FAILED: { label: "Graph build failed", tone: BAD, busy: false },
    UNAVAILABLE: { label: "No extraction agent", tone: BAD, busy: false },
  };
  return extraction[document.extractionStatus];
}

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
  onDocumentChanged,
}: {
  courseId: string;
  documents: CourseDocument[];
  onDocumentChanged?: (document: CourseDocument) => void | Promise<void>;
}) {
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [expanded, setExpanded] = useState("");
  const [records, setRecords] = useState<DocumentGraph | null>(null);
  const [recordsError, setRecordsError] = useState("");

  const stalled = documents.filter(
    (item) =>
      item.processingStatus === "FAILED" ||
      ["FAILED", "UNAVAILABLE"].includes(item.extractionStatus),
  );

  async function retry(document: CourseDocument) {
    setBusy(document.id);
    setError("");
    try {
      const updated =
        document.processingStatus === "READY"
          ? await api.extractDocument(courseId, document.id)
          : await api.processDocument(courseId, document.id);
      await onDocumentChanged?.(updated);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Arc could not retry that source.");
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
        No sources uploaded. Add lecture notes, readings, assignments, or tutorials and Arc will
        build the graph automatically.
      </div>
    );
  }

  return (
    <div>
      {stalled.length > 0 && (
        <p className="mb-4 border-l-2 border-red-700 bg-white px-4 py-3 text-sm">
          {stalled.length} source{stalled.length === 1 ? "" : "s"} did not make it into the graph.
          Check the reason below, or{" "}
          <Link href="/settings" className="focus-ring font-medium text-[var(--accent)] underline">
            review your extraction agent
          </Link>
          .
        </p>
      )}
      {error && (
        <p role="alert" className="mb-4 border-l-2 border-red-700 bg-white px-4 py-3 text-sm text-red-700">
          {error}
        </p>
      )}
      <ul className="border-t border-[var(--line)]">
        {documents.map((document) => {
          const stage = stageOf(document);
          const reason = document.extractionError ?? document.processingError;
          return (
            <li key={document.id} className="border-b border-[var(--line)] bg-white p-4 sm:p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <span className="inline-flex items-center gap-2 font-medium">
                    <FileText size={17} className="text-[var(--accent)]" />
                    {document.originalFilename}
                  </span>
                  <p className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[11px] text-[var(--muted)]">
                    <span>{document.documentType}</span>
                    <span className={`border px-2 py-0.5 text-[10px] ${stage.tone}`}>
                      {stage.busy ? `${stage.label}...` : stage.label}
                    </span>
                    <span>
                      {document.chunkCount} chunk{document.chunkCount === 1 ? "" : "s"}
                    </span>
                    <span>{formatDate(document.createdAt)}</span>
                  </p>
                  {reason && !stage.busy && (
                    <p role="alert" className="mt-2 max-w-2xl text-sm text-red-700">
                      {reason}
                    </p>
                  )}
                </div>
                <div className="flex flex-wrap gap-2">
                  {!stage.busy && stage.tone === BAD && (
                    <button
                      onClick={() => retry(document)}
                      disabled={Boolean(busy)}
                      className="focus-ring inline-flex h-9 items-center gap-1.5 border border-[var(--line)] px-3 text-sm font-medium disabled:opacity-50"
                    >
                      <ArrowClockwise size={15} />
                      {busy === document.id ? "Retrying..." : "Retry"}
                    </button>
                  )}
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
                        {records.nodes.length} node{records.nodes.length === 1 ? "" : "s"} and{" "}
                        {records.edges.length} relationship
                        {records.edges.length === 1 ? "" : "s"} came from this source.
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
                          Nothing in the graph references this source yet.
                        </p>
                      )}
                    </div>
                  )}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
