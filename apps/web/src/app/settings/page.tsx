import { ArrowLeft } from "@phosphor-icons/react/dist/ssr";
import Link from "next/link";
import { Brand } from "@/components/brand";
import { ExtractionSettingsPanel } from "@/components/extraction-settings";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function SettingsPage() {
  const settings = await api.extractionSettings();
  return (
    <main className="min-h-[100dvh]">
      <header className="border-b border-[var(--line)] bg-white">
        <div className="mx-auto flex h-16 max-w-[1280px] items-center justify-between px-5 lg:px-8">
          <Brand />
          <Link
            href="/"
            className="focus-ring inline-flex items-center gap-2 text-sm text-[var(--muted)] hover:text-[var(--ink)]"
          >
            <ArrowLeft size={16} /> All courses
          </Link>
        </div>
      </header>
      <div className="mx-auto max-w-[840px] px-5 py-10 lg:px-8">
        <h1 className="mb-8 text-4xl font-semibold tracking-[-0.055em]">Settings</h1>
        <ExtractionSettingsPanel initialSettings={settings} />
      </div>
    </main>
  );
}
