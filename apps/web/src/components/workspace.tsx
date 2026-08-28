"use client";

import type { Course, CourseDocument, CourseGraph } from "@arc/shared";
import { DOCUMENT_TYPES } from "@arc/shared";
import { ArrowLeft, FileArrowUp, FileText, Gear, Graph, SquaresFour } from "@phosphor-icons/react";
import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Brand } from "./brand";
import { CourseGraph as GraphView } from "./course-graph";
import { CourseSources } from "./course-sources";

type Tab = "overview" | "sources" | "graph";

const SETTLING: CourseDocument["processingStatus"][] = ["UPLOADED", "PROCESSING"];

function isWorking(document: CourseDocument) {
  return SETTLING.includes(document.processingStatus) || document.extractionStatus === "RUNNING";
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en", { month: "short", day: "numeric", year: "numeric" }).format(new Date(value));
}

export function Workspace({ initialCourse, initialDocuments, initialGraph }: { initialCourse: Course; initialDocuments: CourseDocument[]; initialGraph: CourseGraph }) {
  const [tab, setTab] = useState<Tab>("overview");
  const [documents, setDocuments] = useState(initialDocuments);
  const [graph, setGraph] = useState(initialGraph);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const [uploadOpen, setUploadOpen] = useState(false);

  const handleDocumentChanged = useCallback(async (changed: CourseDocument) => {
    setDocuments((items) => items.map((item) => (item.id === changed.id ? changed : item)));
    setGraph(await api.graph(initialCourse.id));
  }, [initialCourse.id]);

  // Uploads are chunked and extracted in the background, so poll until the work settles and then
  // pick up whatever the agent added to the graph.
  const working = documents.some(isWorking);
  useEffect(() => {
    if (!working) return;
    let active = true;
    const timer = setInterval(async () => {
      try {
        const next = await api.documents(initialCourse.id);
        if (!active) return;
        setDocuments(next);
        if (!next.some(isWorking)) setGraph(await api.graph(initialCourse.id));
      } catch { /* a transient failure is retried on the next tick */ }
    }, 3000);
    return () => { active = false; clearInterval(timer); };
  }, [working, initialCourse.id]);

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setUploading(true); setUploadError("");
    const form = new FormData(event.currentTarget);
    try {
      const document = await api.uploadDocument(initialCourse.id, form);
      setDocuments((items) => [document, ...items]);
      setUploading(false); setUploadOpen(false);
    } catch (reason) { setUploadError(reason instanceof Error ? reason.message : "Upload failed."); setUploading(false); }
  }

  return <main className="min-h-[100dvh]">
    <header className="border-b border-[var(--line)] bg-white"><div className="mx-auto flex h-16 max-w-[1280px] items-center justify-between px-5 lg:px-8"><Brand /><div className="flex items-center gap-5"><Link href="/settings" className="focus-ring inline-flex items-center gap-2 text-sm text-[var(--muted)] hover:text-[var(--ink)]"><Gear size={16} /> Settings</Link><Link href="/" className="focus-ring inline-flex items-center gap-2 text-sm text-[var(--muted)] hover:text-[var(--ink)]"><ArrowLeft size={16} /> All courses</Link></div></div></header>
    <div className="mx-auto max-w-[1280px] px-5 py-8 lg:px-8 lg:py-10">
      <section className="grid gap-4 pb-8 sm:grid-cols-[140px_1fr]"><p className="font-mono text-sm font-medium text-[var(--accent)]">{initialCourse.code}</p><div><h1 className="text-4xl font-semibold tracking-[-0.055em] sm:text-5xl">{initialCourse.name}</h1>{initialCourse.description && <p className="mt-3 max-w-2xl text-[var(--muted)]">{initialCourse.description}</p>}</div></section>
      <nav aria-label="Course sections" className="flex gap-7 border-b border-[var(--line)]">{([{ id: "overview", label: "Overview", icon: SquaresFour }, { id: "sources", label: "Sources", icon: FileText }, { id: "graph", label: "Graph", icon: Graph }] as const).map(({ id, label, icon: Icon }) => <button key={id} onClick={() => setTab(id)} aria-current={tab === id ? "page" : undefined} className={`focus-ring -mb-px inline-flex h-12 items-center gap-2 border-b-2 text-sm font-medium ${tab === id ? "border-[var(--accent)] text-[var(--ink)]" : "border-transparent text-[var(--muted)] hover:text-[var(--ink)]"}`}><Icon size={17} />{label}</button>)}</nav>

      {tab === "overview" && <section className="py-8">
        <div className="grid border border-[var(--line)] bg-white sm:grid-cols-3 sm:divide-x sm:divide-[var(--line)]">{[[documents.length, "Uploaded sources"], [graph.nodes.length, "Graph nodes"], [graph.edges.length, "Relationships"]].map(([value, label]) => <div key={label} className="border-b border-[var(--line)] p-6 last:border-b-0 sm:border-b-0"><strong className="block text-4xl font-semibold tracking-[-0.05em]">{value}</strong><span className="mt-2 block text-sm text-[var(--muted)]">{label}</span></div>)}</div>
        <div className="mt-10"><div className="mb-4 flex items-center justify-between"><h2 className="text-xl font-semibold tracking-[-0.03em]">Recent uploads</h2><button onClick={() => setTab("sources")} className="focus-ring text-sm font-medium text-[var(--accent)] hover:underline">View sources</button></div><DocumentList documents={documents.slice(0, 5)} empty="Upload material to begin organizing this course." /></div>
      </section>}

      {tab === "sources" && <section className="py-8"><div className="mb-6 flex flex-wrap items-center justify-between gap-4"><div><h2 className="text-xl font-semibold tracking-[-0.03em]">Course sources</h2><p className="mt-1 text-sm text-[var(--muted)]">PDF, Markdown, text, or Word. Up to 25 MB. Arc reads each source and builds the graph for you.</p></div><div className="flex flex-wrap items-center gap-3"><button onClick={() => setUploadOpen((value) => !value)} className="focus-ring inline-flex h-10 items-center gap-2 bg-[var(--ink)] px-4 text-sm font-medium text-white"><FileArrowUp size={17} /> Upload source</button></div></div>
        {uploadOpen && <form onSubmit={upload} className="mb-6 grid gap-4 border-l-2 border-[var(--accent)] bg-white p-5 sm:grid-cols-[1fr_220px_auto] sm:items-end"><label className="text-sm font-medium">File<input required name="file" type="file" accept=".pdf,.md,.txt,.docx" className="focus-ring mt-2 block h-11 w-full border border-[var(--line)] bg-[var(--paper)] text-sm file:mr-3 file:h-full file:border-0 file:border-r file:border-[var(--line)] file:bg-white file:px-3 file:font-medium" /></label><label className="text-sm font-medium">Document type<select name="document_type" defaultValue="LECTURE" className="focus-ring mt-2 h-11 w-full border border-[var(--line)] bg-[var(--paper)] px-3">{DOCUMENT_TYPES.map((type) => <option key={type}>{type}</option>)}</select></label><button disabled={uploading} className="focus-ring h-11 bg-[var(--accent)] px-5 text-sm font-medium text-white disabled:opacity-60">{uploading ? "Uploading..." : "Add source"}</button>{uploadError && <p role="alert" className="text-sm text-red-700 sm:col-span-3">{uploadError}</p>}</form>}
        <CourseSources courseId={initialCourse.id} documents={documents} onDocumentChanged={handleDocumentChanged} />
      </section>}

      {tab === "graph" && <section className="py-8"><div className="mb-6 flex flex-wrap items-start justify-between gap-4"><div><h2 className="text-xl font-semibold tracking-[-0.03em]">Course graph</h2><p className="mt-1 text-sm text-[var(--muted)]">Drag nodes and use the controls to inspect relationships. Only approved knowledge appears here.</p></div></div>{graph.nodes.length ? <GraphView graph={graph} /> : <div className="grid min-h-[440px] place-items-center border border-dashed border-[#bec8c1] bg-white p-8 text-center"><div><Graph size={34} className="mx-auto mb-4 text-[var(--accent)]" /><h3 className="font-semibold">No course graph yet.</h3><p className="mt-2 max-w-sm text-sm leading-6 text-[var(--muted)]">Upload a source and Arc will read it, then build connections between concepts, lectures, assignments, and source material here.</p></div></div>}</section>}
    </div>
  </main>;
}

function DocumentList({ documents, empty }: { documents: CourseDocument[]; empty: string }) {
  if (!documents.length) return <div className="grid min-h-44 place-items-center border border-dashed border-[#bec8c1] bg-white p-6 text-center text-sm text-[var(--muted)]">{empty}</div>;
  return <div className="overflow-x-auto border-t border-[var(--line)]"><table className="w-full min-w-[680px] border-collapse text-left text-sm"><thead><tr className="text-xs text-[var(--muted)]"><th className="py-3 font-medium">Filename</th><th className="py-3 font-medium">Type</th><th className="py-3 font-medium">Status</th><th className="py-3 text-right font-medium">Uploaded</th></tr></thead><tbody>{documents.map((document) => <tr key={document.id} className="border-t border-[var(--line)] bg-white"><td className="py-4 pr-6 font-medium"><span className="inline-flex items-center gap-2"><FileText size={17} className="text-[var(--accent)]" />{document.originalFilename}</span></td><td className="py-4 pr-6 font-mono text-xs text-[var(--muted)]">{document.documentType}</td><td className="py-4 pr-6"><span className="border border-[#9bc8b4] bg-[#eef8f3] px-2 py-1 font-mono text-[10px] text-[#075b40]">{document.processingStatus}</span></td><td className="py-4 text-right text-[var(--muted)]">{formatDate(document.createdAt)}</td></tr>)}</tbody></table></div>;
}
