"use client";

import type { ExtractionSettings } from "@arc/shared";
import { CheckCircle, Warning } from "@phosphor-icons/react";
import { useState } from "react";
import { api } from "@/lib/api";

export function ExtractionSettingsPanel({ initialSettings }: { initialSettings: ExtractionSettings }) {
  const [settings, setSettings] = useState(initialSettings);
  const [command, setCommand] = useState(initialSettings.commandOverride ?? "");
  const [saving, setSaving] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function save(changes: Parameters<typeof api.updateExtractionSettings>[0], label: string) {
    setSaving(label);
    setError("");
    setNotice("");
    try {
      const updated = await api.updateExtractionSettings(changes);
      setSettings(updated);
      setCommand(updated.commandOverride ?? "");
      setNotice(`${label} saved.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Arc could not save that setting.");
    } finally {
      setSaving("");
    }
  }

  const installed = settings.tools.filter((tool) => tool.available);

  return (
    <div className="grid gap-8">
      <section>
        <h2 className="text-xl font-semibold tracking-[-0.03em]">Extraction agent</h2>
        <p className="mt-1 max-w-2xl text-sm text-[var(--muted)]">
          Arc builds your course graph by running an AI coding agent you already have installed,
          signed in with your own subscription. Arc never stores an API key and never bills you for
          the model.
        </p>
      </section>

      {notice && (
        <p role="status" className="border-l-2 border-[var(--accent)] bg-white px-4 py-3 text-sm">
          {notice}
        </p>
      )}
      {error && (
        <p role="alert" className="border-l-2 border-red-700 bg-white px-4 py-3 text-sm text-red-700">
          {error}
        </p>
      )}

      <section>
        <label className="flex items-start gap-3 border border-[var(--line)] bg-white p-4">
          <input
            type="checkbox"
            className="focus-ring mt-1 h-4 w-4 accent-[var(--accent)]"
            checked={settings.enabled}
            onChange={(event) => save({ enabled: event.target.checked }, "Automatic extraction")}
            disabled={Boolean(saving)}
          />
          <span>
            <span className="font-medium">Build the graph automatically on upload</span>
            <span className="mt-1 block text-sm text-[var(--muted)]">
              Turn this off to keep uploads as plain sources without running an agent.
            </span>
          </span>
        </label>
      </section>

      <section>
        <h3 className="text-sm font-medium">Agent</h3>
        {!installed.length && (
          <p role="alert" className="mt-2 border-l-2 border-red-700 bg-white px-4 py-3 text-sm">
            No supported agent CLI was found on this machine. Install one below, then reload this
            page.
          </p>
        )}
        <ul className="mt-3 grid gap-3">
          {settings.tools.map((tool) => (
            <li key={tool.id}>
              <label
                className={`flex cursor-pointer items-start gap-3 border bg-white p-4 ${
                  settings.toolId === tool.id ? "border-[var(--accent)]" : "border-[var(--line)]"
                }`}
              >
                <input
                  type="radio"
                  name="extraction-tool"
                  className="focus-ring mt-1 h-4 w-4 accent-[var(--accent)]"
                  checked={settings.toolId === tool.id}
                  disabled={!tool.available || Boolean(saving)}
                  onChange={() => save({ toolId: tool.id }, tool.name)}
                />
                <span className="min-w-0 flex-1">
                  <span className="flex flex-wrap items-center gap-2 font-medium">
                    {tool.name}
                    {tool.available ? (
                      <span className="inline-flex items-center gap-1 border border-[#9bc8b4] bg-[#eef8f3] px-2 py-0.5 font-mono text-[10px] text-[#075b40]">
                        <CheckCircle size={11} /> installed
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 border border-[#c9d2cb] bg-[var(--paper)] px-2 py-0.5 font-mono text-[10px] text-[var(--muted)]">
                        not found
                      </span>
                    )}
                    {!tool.verified && (
                      <span className="inline-flex items-center gap-1 border border-[#e0c9a4] bg-[#fdf6ec] px-2 py-0.5 font-mono text-[10px] text-[#8a5a20]">
                        <Warning size={11} /> command unverified
                      </span>
                    )}
                  </span>
                  <span className="mt-1 block break-all font-mono text-[11px] text-[var(--muted)]">
                    {tool.path ?? tool.executable}
                  </span>
                  <a
                    href={tool.docsUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="focus-ring mt-1 inline-block text-xs text-[var(--accent)] hover:underline"
                  >
                    Setup guide
                  </a>
                </span>
              </label>
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h3 className="text-sm font-medium">Command</h3>
        <p className="mt-1 max-w-2xl text-sm text-[var(--muted)]">
          Arc substitutes <code className="font-mono text-xs">{"{prompt}"}</code> and{" "}
          <code className="font-mono text-xs">{"{mcp_config}"}</code> before running this. Edit it if
          your agent uses different flags.
        </p>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void save({ command }, "Command");
          }}
          className="mt-3 grid gap-3"
        >
          <textarea
            value={command}
            onChange={(event) => setCommand(event.target.value)}
            rows={3}
            aria-label="Extraction command"
            placeholder={settings.command ?? ""}
            className="focus-ring w-full border border-[var(--line)] bg-white p-3 font-mono text-xs"
          />
          <div className="flex flex-wrap gap-2">
            <button
              disabled={Boolean(saving)}
              className="focus-ring h-10 bg-[var(--ink)] px-4 text-sm font-medium text-white disabled:opacity-50"
            >
              {saving === "Command" ? "Saving..." : "Save command"}
            </button>
            <button
              type="button"
              onClick={() => save({ command: "" }, "Command")}
              disabled={Boolean(saving) || !settings.commandOverride}
              className="focus-ring h-10 border border-[var(--line)] bg-white px-4 text-sm font-medium disabled:opacity-50"
            >
              Reset to default
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
