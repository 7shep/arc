import type { ExtractionSettings } from "@arc/shared";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ExtractionSettingsPanel } from "./extraction-settings";

const { api } = vi.hoisted(() => ({ api: { updateExtractionSettings: vi.fn() } }));

vi.mock("@/lib/api", () => ({ api }));

const settings: ExtractionSettings = {
  enabled: true,
  toolId: "claude",
  command: 'claude -p "{prompt}"',
  commandOverride: null,
  tools: [
    {
      id: "claude",
      name: "Claude Code",
      executable: "claude",
      path: "C:/Users/alex/.local/bin/claude",
      available: true,
      defaultCommand: 'claude -p "{prompt}"',
      verified: true,
      docsUrl: "https://docs.claude.com",
    },
    {
      id: "codex",
      name: "OpenAI Codex",
      executable: "codex",
      path: null,
      available: false,
      defaultCommand: "codex exec {prompt}",
      verified: false,
      docsUrl: "https://developers.openai.com/codex/cli",
    },
  ],
};

beforeEach(() => {
  vi.clearAllMocks();
  api.updateExtractionSettings.mockResolvedValue(settings);
});

describe("ExtractionSettingsPanel", () => {
  it("lists detected agents and marks which are installed", () => {
    render(<ExtractionSettingsPanel initialSettings={settings} />);

    expect(screen.getByText("Claude Code")).toBeInTheDocument();
    expect(screen.getByText("installed")).toBeInTheDocument();
    expect(screen.getByText("not found")).toBeInTheDocument();
    expect(screen.getByText(/command unverified/i)).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /Claude Code/ })).toBeChecked();
    expect(screen.getByRole("radio", { name: /OpenAI Codex/ })).toBeDisabled();
  });

  it("warns when no agent is installed at all", () => {
    render(
      <ExtractionSettingsPanel
        initialSettings={{
          ...settings,
          toolId: null,
          tools: settings.tools.map((tool) => ({ ...tool, available: false, path: null })),
        }}
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent(/No supported agent CLI was found/i);
  });

  it("saves the selected agent", async () => {
    const user = userEvent.setup();
    render(
      <ExtractionSettingsPanel
        initialSettings={{
          ...settings,
          tools: settings.tools.map((tool) => ({ ...tool, available: true })),
        }}
      />,
    );

    await user.click(screen.getByRole("radio", { name: /OpenAI Codex/ }));

    expect(api.updateExtractionSettings).toHaveBeenCalledWith({ toolId: "codex" });
    expect(await screen.findByRole("status")).toHaveTextContent("OpenAI Codex saved.");
  });

  it("turns automatic extraction off", async () => {
    const user = userEvent.setup();
    render(<ExtractionSettingsPanel initialSettings={settings} />);

    await user.click(screen.getByRole("checkbox", { name: /build the graph automatically/i }));

    expect(api.updateExtractionSettings).toHaveBeenCalledWith({ enabled: false });
  });

  it("saves and resets a custom command", async () => {
    const user = userEvent.setup();
    render(
      <ExtractionSettingsPanel
        initialSettings={{ ...settings, commandOverride: "custom {prompt}" }}
      />,
    );

    // Saving keeps the override, so the reset control stays available afterwards.
    api.updateExtractionSettings.mockResolvedValueOnce({
      ...settings,
      commandOverride: "my-agent {prompt}",
    });
    const field = screen.getByLabelText(/extraction command/i);
    await user.clear(field);
    await user.type(field, "my-agent {{prompt}");
    await user.click(screen.getByRole("button", { name: /save command/i }));

    expect(api.updateExtractionSettings).toHaveBeenCalledWith({ command: "my-agent {prompt}" });

    await user.click(screen.getByRole("button", { name: /reset to default/i }));
    expect(api.updateExtractionSettings).toHaveBeenCalledWith({ command: "" });
  });

  it("surfaces a save failure", async () => {
    api.updateExtractionSettings.mockRejectedValue(new Error("Unknown extraction agent"));
    const user = userEvent.setup();
    render(<ExtractionSettingsPanel initialSettings={settings} />);

    await user.click(screen.getByRole("checkbox", { name: /build the graph automatically/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Unknown extraction agent");
  });
});
