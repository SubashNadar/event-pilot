import { useCallback, useEffect, useRef, useState } from "react";
import clsx from "clsx";
import { CheckCircle2, Menu, Moon, PanelLeftOpen, Pencil, Sun, WifiOff } from "lucide-react";
import { useAgent } from "../hooks/useAgentStream";
import Sidebar from "./Sidebar";
import ChatWindow from "./ChatWindow";
import StepDetailDrawer from "./StepDetailDrawer";

type Selected = { msgId: string; stepId: string } | null;

function useTheme() {
  const [dark, setDark] = useState(() => document.documentElement.classList.contains("dark"));
  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    try {
      localStorage.setItem("event-pilot-theme", dark ? "dark" : "light");
    } catch {
      /* storage unavailable — theme still applies for this visit */
    }
  }, [dark]);
  return [dark, setDark] as const;
}

function EditableTitle() {
  const { state, rename } = useAgent();
  const [editing, setEditing] = useState(false);
  const [v, setV] = useState(state.title);
  useEffect(() => setV(state.title), [state.title]);

  if (editing) {
    return (
      <input
        autoFocus
        aria-label="Session title"
        value={v}
        onChange={(e) => setV(e.target.value)}
        onBlur={() => {
          rename(v);
          setEditing(false);
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter") (e.target as HTMLInputElement).blur();
          if (e.key === "Escape") {
            setV(state.title);
            setEditing(false);
          }
        }}
        className="w-full max-w-[360px] rounded-lg border border-border bg-surface px-2 py-1 text-[14px] font-medium focus:outline-none"
      />
    );
  }
  return (
    <button
      type="button"
      onClick={() => setEditing(true)}
      disabled={!state.sessionId}
      className="group inline-flex min-w-0 max-w-full items-center gap-1.5 rounded-lg px-2 py-1 text-[14px] font-medium hover:bg-surface-2 disabled:hover:bg-transparent"
      title={state.sessionId ? "Rename" : undefined}
    >
      <span className="truncate">{state.title}</span>
      {state.sessionId && <Pencil size={12} className="shrink-0 text-muted opacity-0 transition-opacity group-hover:opacity-100" aria-hidden />}
    </button>
  );
}

function ConnectionBanner() {
  const { state } = useAgent();
  if (state.connection === "connected") return null;
  const reconnecting = state.connection === "reconnecting";
  return (
    <div
      role="status"
      className={clsx(
        "flex items-center justify-center gap-2 border-b px-4 py-2 text-[13px] animate-fade-in",
        reconnecting ? "border-warn/30 bg-warn/10 text-warn" : "border-success/30 bg-success/10 text-success",
      )}
    >
      {reconnecting ? (
        <>
          <WifiOff size={14} aria-hidden />
          Connection lost — reconnecting… Your plan will resume where it left off.
        </>
      ) : (
        <>
          <CheckCircle2 size={14} aria-hidden />
          Reconnected — picked up the stream where it stopped.
        </>
      )}
    </div>
  );
}

export default function AppShell() {
  const { state, retryStep } = useAgent();
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [dark, setDark] = useTheme();
  const [selected, setSelected] = useState<Selected>(null);
  const lastFocus = useRef<string | null>(null);

  const openStep = useCallback((msgId: string, stepId: string) => {
    lastFocus.current = `step-btn-${msgId}-${stepId}`;
    setSelected((cur) => (cur?.msgId === msgId && cur.stepId === stepId ? null : { msgId, stepId }));
  }, []);

  const closeStep = useCallback(() => {
    setSelected(null);
    const id = lastFocus.current;
    if (id) requestAnimationFrame(() => document.getElementById(id)?.focus());
  }, []);

  // Close the drawer when its message disappears (new session, regenerate).
  const msg = selected ? state.messages.find((m) => m.id === selected.msgId) : undefined;
  const run = msg?.role === "agent" ? msg.run : undefined;
  const stepIndex = run && selected ? run.steps.findIndex((s) => s.id === selected.stepId) : -1;
  const step = run && stepIndex >= 0 ? run.steps[stepIndex] : undefined;
  useEffect(() => {
    if (selected && !step) setSelected(null);
  }, [selected, step]);

  return (
    <div className="flex h-full overflow-hidden">
      <Sidebar open={sidebarOpen} mobileOpen={mobileOpen} onClose={() => setSidebarOpen(false)} onCloseMobile={() => setMobileOpen(false)} />

      <main className={clsx("flex min-w-0 flex-1 flex-col transition-[margin] duration-250", step && "lg:mr-[440px]")}>
        <header className="flex h-14 shrink-0 items-center gap-1.5 px-3 sm:px-4">
          <button type="button" className="icon-btn md:hidden" onClick={() => setMobileOpen(true)} aria-label="Open menu">
            <Menu size={18} />
          </button>
          {!sidebarOpen && (
            <button type="button" className="icon-btn hidden md:inline-flex" onClick={() => setSidebarOpen(true)} aria-label="Expand sidebar" title="Expand sidebar">
              <PanelLeftOpen size={17} />
            </button>
          )}
          <div className="min-w-0 flex-1">
            <EditableTitle />
          </div>
          <button type="button" className="icon-btn" onClick={() => setDark((d) => !d)} aria-label={dark ? "Switch to light mode" : "Switch to dark mode"} title="Toggle theme">
            {dark ? <Sun size={16} /> : <Moon size={16} />}
          </button>
        </header>

        <ConnectionBanner />
        <ChatWindow selected={step ? selected : null} onOpenStep={openStep} />
      </main>

      {run && step && selected && (
        <StepDetailDrawer run={run} step={step} index={stepIndex} onClose={closeStep} onRetry={() => retryStep(selected.msgId, step.id)} />
      )}
    </div>
  );
}
