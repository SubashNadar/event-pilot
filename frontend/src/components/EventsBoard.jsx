import { useEffect, useMemo, useState } from 'react';
import { latestRun } from '../run';

const STATUS = {
  awaiting_input: { label: 'Decision needed', tone: 'decide', group: 'decide' },
  paused: { label: 'Decision needed', tone: 'decide', group: 'decide' },
  running: { label: 'Planning', tone: 'run', group: 'run' },
  executing: { label: 'Planning', tone: 'run', group: 'run' },
  completed: { label: 'Plan approved', tone: 'done', group: 'done' },
  error: { label: 'Needs attention', tone: 'attn', group: 'attn' },
  cancelled: { label: 'Stopped', tone: '', group: 'stopped' },
  stopped: { label: 'Stopped', tone: '', group: 'stopped' }
};
const statusOf = status => STATUS[status] || { label: 'Not started', tone: '', group: 'new' };
const money = value => `₹${Math.round(Number(value) || 0).toLocaleString('en-IN')}`;
const FILTERS = [['all', 'All'], ['run', 'Planning'], ['decide', 'Decision needed'], ['done', 'Approved'], ['attn', 'Needs attention']];

/** The events the owner has planned, with their status. Search and filters sit together above the cards. */
export function EventsBoard({ events, onOpen }) {
  const [statuses, setStatuses] = useState({});
  const [filter, setFilter] = useState('all');
  const [query, setQuery] = useState('');

  useEffect(() => {
    let alive = true;
    Promise.all(events.map(event => latestRun(event.id).then(run => [event.id, run?.status]).catch(() => [event.id, null])))
      .then(pairs => { if (alive) setStatuses(Object.fromEntries(pairs)); });
    return () => { alive = false; };
  }, [events]);

  const rows = useMemo(() => events.map(event => ({ ...event, status: statuses[event.id], meta: statusOf(statuses[event.id]) })), [events, statuses]);
  const counts = useMemo(() => rows.reduce((all, row) => ({ ...all, [row.meta.group]: (all[row.meta.group] || 0) + 1 }), {}), [rows]);
  const shown = rows
    .filter(row => filter === 'all' || row.meta.group === (filter === 'attn' ? 'attn' : filter))
    .filter(row => `${row.name} ${row.location}`.toLowerCase().includes(query.trim().toLowerCase()))
    .sort((a, b) => String(a.event_date).localeCompare(String(b.event_date)));

  return <section className="events-board" aria-labelledby="events-board-title">
    <div className="eb-stats">
      <div className="eb-stat"><span>Events</span><strong>{events.length}</strong></div>
      <div className="eb-stat"><span>Plan approved</span><strong>{counts.done || 0}</strong></div>
      <div className="eb-stat"><span>Decision needed</span><strong>{counts.decide || 0}</strong></div>
      <div className="eb-stat"><span>Needs attention</span><strong>{counts.attn || 0}</strong></div>
    </div>
    <div className="eb-toolbar">
      <h2 id="events-board-title" className="visually-hidden">Your planned events</h2>
      <div className="eb-chips" role="group" aria-label="Filter events">{FILTERS.map(([key, label]) => <button key={key} type="button" className="eb-chip" aria-pressed={filter === key} onClick={() => setFilter(key)}>{label}</button>)}</div>
      <input className="eb-search" type="search" placeholder="Search events" aria-label="Search events" value={query} onChange={event => setQuery(event.target.value)} />
    </div>
    <div className="eb-grid">{shown.length ? shown.map(row => <button key={row.id} type="button" className="eb-card" onClick={() => onOpen(row.id)}>
      <span className={`eb-pill ${row.meta.tone}`}>{row.meta.label}</span>
      <strong>{row.name}</strong>
      <span className="muted">{row.location} · {row.attendees} guests</span>
      <span className="muted num">{row.event_date} · {money(row.budget)}</span>
    </button>) : <p className="muted">No events match this filter yet.</p>}</div>
  </section>;
}
