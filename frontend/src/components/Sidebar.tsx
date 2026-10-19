import { useMemo, useState } from "react";
import clsx from "clsx";
import { PanelLeftClose, Plus, Search, X } from "lucide-react";
import { useAgent } from "../hooks/useAgentStream";
import { groupSessions } from "../lib/sessions";
import { EventPilotLogo } from "./Logo";

interface Props {
  /** Desktop: expanded or collapsed. */
  open: boolean;
  /** Mobile overlay visibility. */
  mobileOpen: boolean;
  onClose: () => void;
  onCloseMobile: () => void;
}

export default function Sidebar({ open, mobileOpen, onClose, onCloseMobile }: Props) {
  const { state, openSession, newSession } = useAgent();
  const [q, setQ] = useState("");

  const groups = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const list = needle
      ? state.sessions.filter((s) => `${s.title} ${s.eventName}`.toLowerCase().includes(needle))
      : state.sessions;
    return groupSessions(list);
  }, [state.sessions, q]);

  const pick = (fn: () => void) => () => {
    fn();
    onCloseMobile();
  };

  const body = (
    <div className="flex h-full w-[272px] flex-col bg-surface-2/60">
      <div className="flex h-14 items-center gap-2.5 px-4">
        <EventPilotLogo markSize={28} />
        <button type="button" className="icon-btn ml-auto hidden md:inline-flex" onClick={onClose} aria-label="Collapse sidebar" title="Collapse sidebar">
          <PanelLeftClose size={17} />
        </button>
        <button type="button" className="icon-btn ml-auto md:hidden" onClick={onCloseMobile} aria-label="Close menu">
          <X size={17} />
        </button>
      </div>

      <div className="space-y-2 px-3">
        <button
          type="button"
          onClick={pick(newSession)}
          className="flex w-full items-center gap-2 rounded-xl border border-border bg-surface px-3 py-2 text-[13.5px] font-medium shadow-soft transition-colors duration-150 hover:border-muted/40"
        >
          <span className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-accent text-accent-ink">
            <Plus size={13} strokeWidth={2.5} />
          </span>
          New plan
        </button>
        <div className="relative">
          <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" aria-hidden />
          <label htmlFor="session-search" className="sr-only">
            Search plans
          </label>
          <input
            id="session-search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search plans"
            className="w-full rounded-xl border border-transparent bg-surface-2 py-1.5 pl-8 pr-3 text-[13px] placeholder:text-muted focus:border-border focus:bg-surface focus:outline-none"
          />
        </div>
      </div>

      <nav aria-label="Plan history" className="scroll-thin mt-3 min-h-0 flex-1 overflow-y-auto px-2 pb-4">
        {groups.length === 0 && <p className="px-3 py-6 text-center text-[13px] text-muted">No plans match “{q}”.</p>}
        {groups.map(([label, items]) => (
          <div key={label} className="mb-3">
            <h2 className="px-3 pb-1 pt-2 text-[11.5px] font-medium text-muted">{label}</h2>
            <ul>
              {items.map((s) => (
                <li key={s.id}>
                  <button
                    type="button"
                    onClick={pick(() => openSession(s.id))}
                    aria-current={state.sessionId === s.id ? "page" : undefined}
                    className={clsx(
                      "w-full rounded-lg px-3 py-1.5 text-left transition-colors duration-150",
                      state.sessionId === s.id ? "bg-surface shadow-soft" : "hover:bg-surface/70",
                    )}
                  >
                    <span className="block truncate text-[13.5px]">{s.title}</span>
                    <span className="block truncate text-[11.5px] text-muted">
                      {s.eventName} · {s.eventDate}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>

      <div className="flex items-center gap-2.5 border-t border-border px-4 py-3">
        <span className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-ink text-[11px] font-semibold text-bg">EV</span>
        <span className="min-w-0">
          <span className="block truncate text-[13px] font-medium">Events team</span>
          <span className="block text-[11.5px] text-muted">Team workspace</span>
        </span>
      </div>
    </div>
  );

  return (
    <>
      {/* Desktop */}
      <aside
        className={clsx(
          "hidden shrink-0 overflow-hidden border-r border-border transition-[width] duration-250 ease-out md:block",
          open ? "w-[272px]" : "w-0 border-r-0",
        )}
        aria-hidden={!open}
      >
        {open && body}
      </aside>

      {/* Mobile overlay */}
      {mobileOpen && (
        <div className="fixed inset-0 z-40 md:hidden" role="dialog" aria-modal="true" aria-label="Plan history">
          <button type="button" aria-label="Close menu" className="absolute inset-0 bg-black/30 animate-fade-in" onClick={onCloseMobile} />
          <div className="absolute inset-y-0 left-0 bg-bg shadow-lift animate-slide-in-left">{body}</div>
        </div>
      )}
    </>
  );
}
