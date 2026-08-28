"use client";

import { Plus, X } from "@phosphor-icons/react";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { api } from "@/lib/api";

export function CreateCourse() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setPending(true); setError("");
    const data = new FormData(event.currentTarget);
    try {
      const course = await api.createCourse({ name: String(data.get("name")), code: String(data.get("code")), description: String(data.get("description") || "") || undefined });
      router.push(`/courses/${course.id}`);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Course creation failed."); setPending(false); }
  }

  return <>
    <button onClick={() => setOpen(true)} className="focus-ring inline-flex h-11 items-center gap-2 bg-[var(--accent)] px-4 font-medium text-white hover:bg-[var(--accent-strong)]"><Plus size={18} weight="bold" /> Create Course</button>
    {open && <div className="fixed inset-0 z-50 grid place-items-center bg-black/35 p-4" role="presentation" onMouseDown={(e) => e.target === e.currentTarget && setOpen(false)}>
      <section role="dialog" aria-modal="true" aria-labelledby="create-title" className="w-full max-w-lg border border-[var(--line)] bg-white p-6 shadow-[0_24px_80px_rgba(20,35,27,.18)]">
        <div className="mb-6 flex items-start justify-between"><div><h2 id="create-title" className="text-2xl font-semibold tracking-[-0.04em]">Create a course</h2><p className="mt-1 text-sm text-[var(--muted)]">Start with the course identity. Sources come next.</p></div><button onClick={() => setOpen(false)} aria-label="Close" className="focus-ring p-1 text-[var(--muted)] hover:text-[var(--ink)]"><X size={20} /></button></div>
        <form onSubmit={submit} className="space-y-4">
          <label className="block text-sm font-medium">Course code<input name="code" required maxLength={32} placeholder="MATH221" className="focus-ring mt-2 h-11 w-full border border-[var(--line)] bg-[var(--paper)] px-3 uppercase placeholder:normal-case placeholder:text-[#8b938e]" /></label>
          <label className="block text-sm font-medium">Course name<input name="name" required maxLength={160} placeholder="Vector Calculus" className="focus-ring mt-2 h-11 w-full border border-[var(--line)] bg-[var(--paper)] px-3 placeholder:text-[#8b938e]" /></label>
          <label className="block text-sm font-medium">Description <span className="font-normal text-[var(--muted)]">Optional</span><textarea name="description" rows={3} maxLength={2000} className="focus-ring mt-2 w-full resize-none border border-[var(--line)] bg-[var(--paper)] p-3" /></label>
          {error && <p role="alert" className="border-l-2 border-red-600 bg-red-50 p-3 text-sm text-red-800">{error}</p>}
          <button disabled={pending} className="focus-ring h-11 w-full bg-[var(--accent)] px-4 font-medium text-white hover:bg-[var(--accent-strong)] disabled:cursor-wait disabled:opacity-60">{pending ? "Creating course..." : "Create course"}</button>
        </form>
      </section>
    </div>}
  </>;
}
