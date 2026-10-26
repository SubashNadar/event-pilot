import { CalendarDays, FileText, LayoutGrid, Loader2, Sparkles, Workflow } from 'lucide-react';

/** Views that only make sense once a plan exists. */
const PLAN_VIEWS = [
  ['plan', LayoutGrid, 'Plan Workspace'],
  ['brief', FileText, 'Event brief']
];

const runLabel = run => {
  if (!run) return null;
  if (run.status === 'awaiting_input') return { text: 'Decide', alert: true };
  if (run.status === 'completed') return { text: 'Ready', alert: false };
  if (run.status === 'stopped') return { text: 'Stopped', alert: false };
  if (run.status === 'error') return { text: 'Error', alert: true };
  return { text: 'Live', alert: false, live: true };
};

/**
 * The one menu: workspace navigation, the current plan (only once one exists),
 * saved plans, and the connection status.
 */
export function Sidebar({ view, setView, setPlanTab, onNewEvent, onOpenPlanWithAi, onChangePlan, run, counts, history, online, hasEvent = false }) {
  const status = runLabel(run);
  const hasPlan = Boolean(counts);
  return <aside className="sidebar" id="app-nav" aria-label="Event Pilot navigation">
    <a className="brand" href="#events" onClick={() => setView('events')}><span className="brand-mark" aria-hidden="true">✦</span><span>Event Pilot</span></a>
    <button type="button" className="new-event" onClick={onNewEvent}><span aria-hidden="true">+</span> New Plan</button>

    <nav className="primary-nav" aria-label="Workspace">
      <button type="button" className={`nav-item ${view === 'events' ? 'active' : ''}`} onClick={() => setView('events')} aria-current={view === 'events' ? 'page' : undefined}><span><CalendarDays size={15} aria-hidden="true" /></span> Events</button>
      {run && <button type="button" className={`nav-item ${view === 'run' ? 'active' : ''}`} onClick={() => setView('run')} aria-current={view === 'run' ? 'page' : undefined}><span>{status?.live ? <Loader2 size={15} className="spin" aria-hidden="true" /> : <Workflow size={15} aria-hidden="true" />}</span> Planning run {status && <span className={`section-count ${status.alert ? 'alert' : ''}`}>{status.text}</span>}</button>}
    </nav>

    {(hasPlan || hasEvent) && <nav className="section-nav" aria-label="This plan">
      <p className="sidebar-label">This Plan</p>
      {PLAN_VIEWS.map(([id, Icon, label]) => <button type="button" key={id} className={`nav-item ${view === id ? 'active' : ''}`} onClick={() => setView(id)} aria-current={view === id ? 'page' : undefined}><span><Icon size={15} aria-hidden="true" /></span> {label}</button>)}
      {onChangePlan && <button type="button" className="nav-item nav-change" onClick={onChangePlan}><span><Sparkles size={15} aria-hidden="true" /></span> Change plan</button>}
    </nav>}

    <section className="sidebar-history" aria-label="Saved plans">{history}</section>

    <div className="sidebar-footer" role="status"><span className={`live-dot ${online ? '' : 'offline'}`} aria-hidden="true" /> {online ? 'Planning system online' : 'Backend offline'}</div>
  </aside>;
}
