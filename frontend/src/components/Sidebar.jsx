const navigation = [
  ['home', '⌂', 'Home'],
  ['overview', '◫', 'Overview'],
  ['brief', '⌁', 'Event brief'],
  ['plan', '▦', 'Plan workspace'],
  ['activity', '◌', 'Agent activity']
];

export function Sidebar({ view, setView, setPlanTab, onNewEvent, events, activeEventId, onSelectEvent }) {
  return <aside className="sidebar" aria-label="Event navigation">
    <a className="brand" href="#home" onClick={() => setView('home')}><span className="brand-mark">E</span><span>EventPilot</span></a>
    <button className="new-event" onClick={onNewEvent}><span>+</span> New event</button>
    <nav className="primary-nav">
      {navigation.map(([id, icon, label]) => <button key={id} className={`nav-item ${view === id ? 'active' : ''}`} onClick={() => setView(id)}><span>{icon}</span> {label}</button>)}
    </nav>
    <div className="sidebar-label">Your events</div>
    <nav className="event-list" aria-label="Saved events">
      {events.length ? events.map(event => <button key={event.id} className={`event-list-item ${event.id === activeEventId ? 'active' : ''}`} onClick={() => onSelectEvent(event.id)}><strong>{event.name}</strong><span>{event.event_date} · {event.location}</span></button>) : <p className="event-list-empty">No saved events yet</p>}
    </nav>
    <div className="sidebar-label">Plan sections</div>
    <nav className="section-nav">
      {['Logistics', 'Budget', 'Schedule', 'Marketing', 'Risks'].map((name, index) => <button key={name} onClick={() => setPlanTab(name.toLowerCase())}>{name} <span className={`section-count ${name === 'Risks' ? 'alert' : ''}`}>{[3, 1, 4, 2, 2][index]}</span></button>)}
    </nav>
    <div className="sidebar-footer"><span className="live-dot" /> Planning system online</div>
  </aside>;
}
