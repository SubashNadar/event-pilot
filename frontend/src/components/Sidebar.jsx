import { Activity, ClipboardList, Home, LayoutDashboard, LayoutGrid, Loader2, Workflow } from 'lucide-react';

const navigation = [
  ['home', Home, 'Plan with AI'],
  ['overview', LayoutDashboard, 'Overview'],
  ['brief', ClipboardList, 'Event brief'],
  ['plan', LayoutGrid, 'Plan workspace'],
  ['activity', Activity, 'Agent activity']
];

const runLabel = run => {
  if (!run) return null;
  if (run.status === 'awaiting_input') return { text: 'Input needed', alert: true };
  if (run.status === 'completed') return { text: 'Ready', alert: false };
  if (run.status === 'stopped') return { text: 'Stopped', alert: false };
  if (run.status === 'error') return { text: 'Error', alert: true };
  return { text: 'Live', alert: false, live: true };
};

export function Sidebar({ view, setView, setPlanTab, onNewEvent, onOpenPlanWithAi, events, activeEventId, onSelectEvent, run, counts }) {
  const status = runLabel(run);
  return <aside className="sidebar" aria-label="Event navigation">
    <a className="brand" href="#home" onClick={() => setView('home')}><span className="brand-mark">E</span><span>EventPilot</span></a>
    <button className="new-event" onClick={onNewEvent}><span>+</span> New event</button>
    <nav className="primary-nav">
      {navigation.map(([id, Icon, label]) => <button key={id} className={`nav-item ${view === id ? 'active' : ''}`} onClick={() => id === 'home' ? onOpenPlanWithAi?.() : setView(id)} aria-current={view === id ? 'page' : undefined}><span><Icon size={15} aria-hidden /></span> {label}</button>)}
      {run && <button className={`nav-item ${view === 'run' ? 'active' : ''}`} onClick={() => setView('run')} aria-current={view === 'run' ? 'page' : undefined}><span>{status?.live ? <Loader2 size={15} className="spin" aria-hidden /> : <Workflow size={15} aria-hidden />}</span> Planning run {status && <span className={`section-count ${status.alert ? 'alert' : ''}`}>{status.text}</span>}</button>}
    </nav>
    <div className="sidebar-label">Plan sections</div>
    <nav className="section-nav">
      {['Logistics', 'Budget', 'Schedule', 'Marketing', 'Risks'].map(name => { const key = name.toLowerCase(); const count = counts?.[key] ?? 0; return <button key={name} onClick={() => setPlanTab(key)}>{name} <span className={`section-count ${key === 'risks' && count > 0 ? 'alert' : ''}`}>{count}</span></button>; })}
    </nav>
    <div className="sidebar-footer"><span className="live-dot" /> Planning system online</div>
  </aside>;
}
