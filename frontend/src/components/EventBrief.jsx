import { useEffect, useRef, useState } from 'react';
import { ApiError, errorMessage } from '../lib/http';
import { discardBriefDraft, getBriefDraft, saveBriefDraft } from '../api/eventApi';

/** Map the saved draft's field names onto the brief's. */
const fromDraft = saved => ({ ...(saved.name !== undefined && { name: saved.name }), ...(saved.event_date !== undefined && { date: saved.event_date }), ...(saved.location !== undefined && { location: saved.location }), ...(saved.attendees !== undefined && { attendees: saved.attendees }), ...(saved.budget !== undefined && { budget: saved.budget }), ...(saved.objective !== undefined && { objective: saved.objective }) });

/** Only the fields the owner has changed, in the API's names. */
const changedFields = (draft, event) => {
  const names = { name: 'name', date: 'event_date', location: 'location', attendees: 'attendees', budget: 'budget', objective: 'objective' };
  return Object.fromEntries(Object.entries(names).filter(([key]) => String(draft[key] ?? '') !== String(event[key] ?? '')).map(([key, api]) => [api, draft[key]]));
};

export function EventBrief({ event, eventId, onSave, hasPlan = false }) {
  const id = eventId ?? event?.id;
  const [draft, setDraft] = useState(event);
  const [restored, setRestored] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState('');
  const [fieldErrors, setFieldErrors] = useState({});
  const [saving, setSaving] = useState(false);
  const loaded = useRef(false);

  /* A brief the owner left half-edited comes back exactly as they left it. */
  useEffect(() => {
    loaded.current = false;
    setDraft(event); setDirty(false); setRestored(false);
    if (!id) { loaded.current = true; return; }
    getBriefDraft(id)
      .then(({ draft: saved }) => { if (saved && Object.keys(saved).length) { setDraft({ ...event, ...fromDraft(saved) }); setDirty(true); setRestored(true); } })
      .catch(() => {})
      .finally(() => { loaded.current = true; });
  }, [id]);

  /* Every change is kept as the owner types, so leaving the page never loses it. */
  useEffect(() => {
    if (!loaded.current || !id) return undefined;
    const fields = changedFields(draft, event);
    if (!Object.keys(fields).length) return undefined;
    const timer = setTimeout(() => saveBriefDraft(id, fields).catch(() => {}), 600);
    return () => clearTimeout(timer);
  }, [draft]);

  const update = field => e => { setDraft({ ...draft, [field]: e.target.value }); setDirty(true); };

  async function submit(e) {
    e.preventDefault();
    if (saving) return;
    setSaving(true); setError(''); setFieldErrors({});
    try {
      await onSave({ ...draft, attendees: Number(draft.attendees), budget: Number(draft.budget) });
      if (id) await discardBriefDraft(id).catch(() => {});
      setDirty(false); setRestored(false);
    }
    catch (failure) { setError(errorMessage(failure)); if (failure instanceof ApiError) setFieldErrors(failure.fieldErrors); }
    finally { setSaving(false); }
  }

  async function discard() {
    if (id) await discardBriefDraft(id).catch(() => {});
    setDraft(event); setDirty(false); setRestored(false);
  }

  return <section className="view active"><div className="view-heading"><p className="eyebrow">INPUTS</p><h1>Event brief</h1><p>{hasPlan ? 'Change any detail and save. Your change goes to the planning team, only the parts it affects are re-planned, and you approve the result.' : 'Keep the planning team aligned by updating the core constraints.'}</p></div>
    <p className="muted" role="status" style={{ fontSize: 12.5 }}>{restored ? 'We kept your unsaved changes from last time.' : dirty ? 'Unsaved changes are kept for you until you save or discard them.' : 'All changes saved.'}</p>
    <form className="brief-form" onSubmit={submit}>
    <label>Event name<input value={draft.name} onChange={update('name')} required /></label><label>Event date<input type="date" value={draft.date} onChange={update('date')} required /></label><label>Location<input value={draft.location} onChange={update('location')} required /></label><label>Expected attendees<input type="number" value={draft.attendees} onChange={update('attendees')} min="1" required /></label><label>Total budget (INR)<input type="number" value={draft.budget} onChange={update('budget')} min="0" required /></label><label>Objective<textarea value={draft.objective} onChange={update('objective')} /></label>{Object.entries(fieldErrors).map(([field, message]) => <p key={field} className="chat-error" role="alert">{field.replace(/_/g, ' ')}: {message}</p>)}{error && <p className="chat-error" role="alert">{error}</p>}
    <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}><button className="button primary" type="submit" disabled={saving}>{saving ? 'Saving…' : hasPlan ? 'Save and update plan' : 'Save event brief'}</button>{dirty && <button className="button secondary" type="button" onClick={discard}>Discard changes</button>}</div>
  </form></section>;
}
