const navigation = [
  ['overview', '◫', 'Overview'],
  ['brief', '⌁', 'Event brief'],
  ['plan', '▦', 'Plan workspace'],
  ['activity', '◌', 'Agent activity']
];

export function Sidebar({ view, setView, setPlanTab, onNewEvent }) {
  return <aside className="sidebar" aria-label="Event navigation">
    <a className="brand" href="#overview" onClick={() => setView('overview')}><span className="brand-mark">E</span><span>EventPilot</span></a>
    <button className="new-event" onClick={onNewEvent}><span>+</span> New event</button>
    <nav className="primary-nav">
      {navigation.map(([id, icon, label]) => <button key={id} className={`nav-item ${view === id ? 'active' : ''}`} onClick={() => setView(id)}><span>{icon}</span> {label}</button>)}
    </nav>
    <div className="sidebar-label">Plan sections</div>
    <nav className="section-nav">
      {['Logistics', 'Budget', 'Schedule', 'Marketing', 'Risks'].map((name, index) => <button key={name} onClick={() => setPlanTab(name.toLowerCase())}>{name} <span className={`section-count ${name === 'Risks' ? 'alert' : ''}`}>{[3, 1, 4, 2, 2][index]}</span></button>)}
    </nav>
    <div className="sidebar-footer"><span className="live-dot" /> Planning system online</div>
  </aside>;
}
