import { useState } from 'react';
import { ApiError, errorMessage } from '../lib/http';

export function EventBrief({ event, onSave }) {
  const [draft, setDraft] = useState(event);
  const [error, setError] = useState('');
  const [fieldErrors, setFieldErrors] = useState({});
  const [saving, setSaving] = useState(false);
  const update = field => e => setDraft({ ...draft, [field]: e.target.value });
  async function submit(e) {
    e.preventDefault();
    if (saving) return;
    setSaving(true); setError(''); setFieldErrors({});
    try { await onSave({ ...draft, attendees: Number(draft.attendees), budget: Number(draft.budget) }); }
    catch (failure) { setError(errorMessage(failure)); if (failure instanceof ApiError) setFieldErrors(failure.fieldErrors); }
    finally { setSaving(false); }
  }
  return <section className="view active"><div className="view-heading"><p className="eyebrow">INPUTS</p><h1>Event brief</h1><p>Keep the planning team aligned by updating the core constraints.</p></div><form className="brief-form" onSubmit={submit}>
    <label>Event name<input value={draft.name} onChange={update('name')} required /></label><label>Event date<input type="date" value={draft.date} onChange={update('date')} required /></label><label>Location<input value={draft.location} onChange={update('location')} required /></label><label>Expected attendees<input type="number" value={draft.attendees} onChange={update('attendees')} min="1" required /></label><label>Total budget (INR)<input type="number" value={draft.budget} onChange={update('budget')} min="0" required /></label><label>Objective<textarea value={draft.objective} onChange={update('objective')} /></label>{Object.entries(fieldErrors).map(([field, message]) => <p key={field} className="chat-error" role="alert">{field.replace(/_/g, ' ')}: {message}</p>)}{error && <p className="chat-error" role="alert">{error}</p>}<button className="button primary" type="submit" disabled={saving}>{saving ? 'Saving…' : 'Save event brief'}</button>
  </form></section>;
}
