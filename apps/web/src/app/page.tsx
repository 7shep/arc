import { ArrowUpRight, Books } from "@phosphor-icons/react/dist/ssr";
import type { Course } from "@arc/shared";
import Link from "next/link";
import { Brand } from "@/components/brand";
import { CreateCourse } from "@/components/create-course";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function Home() {
  let courses: Course[] = [];
  let unavailable = false;
  try { courses = await api.courses(); } catch { unavailable = true; }
  return <main className="min-h-[100dvh]">
    <header className="border-b border-[var(--line)] bg-white"><div className="mx-auto flex h-16 max-w-[1280px] items-center justify-between px-5 lg:px-8"><Brand /><span className="font-mono text-xs text-[var(--muted)]">COURSE KNOWLEDGE SYSTEM</span></div></header>
    <div className="mx-auto max-w-[1280px] px-5 py-12 lg:px-8 lg:py-20">
      <section className="grid items-end gap-8 border-b border-[var(--line)] pb-12 lg:grid-cols-[1fr_auto]">
        <div><p className="mb-5 font-mono text-xs font-medium tracking-[0.12em] text-[var(--accent)]">YOUR WORKSPACE</p><h1 className="max-w-3xl text-5xl font-semibold leading-[0.95] tracking-[-0.065em] sm:text-6xl lg:text-7xl">Course intelligence,<br />connected.</h1><p className="mt-6 max-w-lg text-base leading-7 text-[var(--muted)]">Organize sources now. Build a queryable course knowledge graph as your material grows.</p></div>
        <CreateCourse />
      </section>
      <section className="pt-10"><div className="mb-5 flex items-baseline justify-between"><h2 className="text-xl font-semibold tracking-[-0.03em]">Courses</h2><span className="font-mono text-xs text-[var(--muted)]">{courses.length.toString().padStart(2, "0")} TOTAL</span></div>
        {unavailable ? <div className="border-l-2 border-red-600 bg-red-50 p-5"><p className="font-medium text-red-900">The Arc API is unavailable.</p><p className="mt-1 text-sm text-red-800">Start the backend on port 8000, then reload this workspace.</p></div>
        : courses.length === 0 ? <div className="grid min-h-60 place-items-center border border-dashed border-[#bec8c1] bg-white p-8 text-center"><div><Books size={32} className="mx-auto mb-4 text-[var(--accent)]" /><h3 className="font-semibold">No courses yet</h3><p className="mt-2 text-sm text-[var(--muted)]">Create your first course to begin adding source material.</p></div></div>
        : <div className="border-t border-[var(--line)]">{courses.map((course) => <Link key={course.id} href={`/courses/${course.id}`} className="focus-ring group grid gap-3 border-b border-[var(--line)] bg-white px-5 py-5 hover:bg-[#f0f6f2] sm:grid-cols-[140px_1fr_auto] sm:items-center"><span className="font-mono text-sm font-medium text-[var(--accent)]">{course.code}</span><span><strong className="block font-medium">{course.name}</strong><small className="mt-1 block text-[var(--muted)]">{course.documentCount} sources · {course.nodeCount} nodes · {course.edgeCount} relationships</small></span><ArrowUpRight size={19} className="text-[var(--muted)] transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5" /></Link>)}</div>}
      </section>
    </div>
  </main>;
}
