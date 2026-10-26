import { useEffect, useRef, useState } from 'react';
import { getEventChat, sendPlanChat } from '../api/eventApi';
import { ApiError } from '../lib/http';
import './chatbotDock.css';
import './planChat.css';

const SUGGESTIONS = ['Move dinner to 9 PM', 'Add a welcome drink at 6:30 PM', 'Make it 300 guests', 'Put ₹2 lakh into catering', 'What’s the venue?'];
const TERMINAL = new Set(['completed', 'stopped', 'error']);

/** What the owner can change, each with a sentence starter they finish in their own words. */
export const CHANGE_TOPICS = [
  { key: 'venue', emoji: '📍', label: 'Venue', prompt: 'Change the venue to ' },
  { key: 'budget', emoji: '💸', label: 'Budget', prompt: 'Set the total budget to ₹' },
  { key: 'date', emoji: '🗓️', label: 'Date', prompt: 'Move the event to ' },
  { key: 'guests', emoji: '👥', label: 'Guests', prompt: 'Change the guest count to ' },
  { key: 'schedule', emoji: '⏰', label: 'Schedule', prompt: 'In the agenda, ' },
  { key: 'food', emoji: '🍽️', label: 'Food & vendors', prompt: 'For catering, ' },
  { key: 'risks', emoji: '🛟', label: 'Risks', prompt: 'Add a fallback for ' }
];

/**
 * Talk to the plan after it exists: ask about it, or change it in plain words.
 * A change re-runs only the affected specialists (the rest of the plan is kept),
 * and the server posts what changed back into this conversation. The history is
 * saved per event, including the brief intake that created it.
 *
 * The panel is opened from anywhere in the workspace through `seed`: a sentence
 * starter to finish, or (with `send`) a full change to send straight away.
 */
export function PlanChat({ eventId, run, open, onOpenChange, seed, onSeedUsed, onEditRun, onOpenRun, onPlanUpdated }) {
  const setOpen = value => onOpenChange(typeof value === 'function' ? value(open) : value);
  const [messages, setMessages] = useState([]);
  const [sessionId, setSessionId] = useState(null);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [retryAt, setRetryAt] = useState(0);
  const [remaining, setRemaining] = useState(0);
  useEffect(() => {
    const tick = () => setRemaining(Math.max(0, Math.ceil((retryAt - Date.now()) / 1000)));
    tick();
    const timer = window.setInterval(tick, 1000);
    return () => window.clearInterval(timer);
  }, [retryAt]);
  const [pendingRun, setPendingRun] = useState(null);
  const historyRef = useRef(null);
  const inputRef = useRef(null);

  const load = () => getEventChat(eventId)
    .then(session => { setSessionId(session.id || null); setMessages(session.messages); return session.messages; })
    .catch(() => { setError('The conversation could not be loaded. Check that the API is running.'); return []; });

  useEffect(() => { setMessages([]); setSessionId(null); setPendingRun(null); if (eventId) load(); }, [eventId]);

  useEffect(() => { historyRef.current?.scrollTo({ top: historyRef.current.scrollHeight, behavior: 'smooth' }); }, [messages, open, run?.status]);

  // When the edit run finishes or pauses, the server has posted the outcome: fetch it.
  useEffect(() => {
    if (!pendingRun || run?.runId !== pendingRun) return;
    if (run.status === 'awaiting_input' || TERMINAL.has(run.status)) {
      const finished = run.runId;
      const timer = window.setTimeout(() => {
        load().then(latest => {
          if (run.status !== 'completed') return;
          const done = [...latest].reverse().find(message => message.run_id === finished && message.meta?.kind === 'edit_done');
          onPlanUpdated?.(done?.meta?.changes || []);
        });
        if (TERMINAL.has(run.status)) setPendingRun(null);
      }, 400);
      return () => window.clearTimeout(timer);
    }
  }, [run?.status, run?.runId, pendingRun]);

  const send = async text => {
    const message = text.trim();
    if (!message || busy || Date.now() < retryAt) return;
    setBusy(true);
    setError('');
    setDraft('');
    setMessages(current => [...current, { seq: -Date.now(), role: 'user', content: message, pending: true }]);
    try {
      const result = await sendPlanChat(eventId, message, sessionId);
      setSessionId(result.session_id);
      setMessages(current => [...current.filter(item => !item.pending), ...result.messages]);
      if (result.kind === 'edit_started' && result.run_id) {
        setPendingRun(result.run_id);
        onEditRun(result.run_id);
      }
    } catch (failure) {
      setMessages(current => current.filter(item => !item.pending));
      setDraft(message);
      setError(failure.message || 'The planning assistant is unavailable.');
      if (failure instanceof ApiError && failure.status === 429) setRetryAt(Date.now() + (failure.retryAfter ?? 60) * 1000);
    } finally {
      setBusy(false);
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  };

  // Focus the box with the cursor after the sentence starter. The panel may only
  // just be opening, so this waits until the input is on the page.
  const focusEnd = useRef(false);
  useEffect(() => {
    const input = inputRef.current;
    if (!open || !input || !focusEnd.current) return;
    focusEnd.current = false;
    input.focus();
    input.setSelectionRange(input.value.length, input.value.length);
  });
  const startWith = text => { setDraft(text); focusEnd.current = true; };

  // Opened from a button elsewhere in the workspace.
  useEffect(() => {
    if (!seed) return;
    setOpen(true);
    if (seed.send) send(seed.text); else startWith(seed.text || '');
    onSeedUsed?.(); // used once, so remounting the panel never re-sends it
  }, [seed?.nonce]);

  const updating = pendingRun && run?.runId === pendingRun ? run : null;
  const rerun = updating ? updating.steps.filter(step => !(step.summary?.did?.[0] || '').startsWith('Kept from the current plan') && step.status !== 'pending' && step.status !== 'skipped') : [];
  const waiting = updating?.status === 'awaiting_input';
  const locked = busy || remaining > 0 || Boolean(updating && !waiting);
  // Brief intake belongs to Plan with AI. Keep it stored with the event, but do
  // not replay it (the owner's answers or the replies) in the post-plan edit conversation.
  const visibleMessages = messages.filter((message, index) => message.meta?.kind !== 'brief' && !(message.role === 'user' && messages[index + 1]?.meta?.kind === 'brief'));

  return <aside className={`chatbot-dock plan-chat ${open ? 'is-open' : ''}`} aria-label="Change the plan">
    {open && <section className="chatbot-window" role="dialog" aria-label="Change the plan">
      <div className="chatbot-topline"><div><span aria-hidden="true">✦</span><div><strong>Change the plan</strong><small>{updating ? (waiting ? 'Waiting for your decision' : 'Updating only what changed…') : 'Say what to change. Only the affected agents re-run.'}</small></div></div><div className="chatbot-header-actions"><button onClick={() => setOpen(false)} aria-label="Close">×</button></div></div>
      <div className="chat-layout">
        <section className="chat-panel" aria-label="Conversation about the plan">
          <div className="chat-history" ref={historyRef} aria-live="polite">
            {visibleMessages.length === 0 && <div className="chat-message assistant"><span>EP</span><p className="chat-text">Your plan is ready. Ask me about it, or tell me what to change, like “move dinner to 9 PM”, “make it 300 guests”, or “change name to Spring Birthday Celebration”. I’ll re-run only the specialists the change affects, and you approve the result.</p></div>}
            {visibleMessages.map(message => <div className={`chat-message ${message.role} ${message.meta?.kind ? `kind-${message.meta.kind}` : ''}`} key={message.seq}><span>{message.role === 'assistant' ? 'EP' : 'You'}</span><p className="chat-text">{message.content}</p></div>)}
            {updating && <div className="plan-chat-progress" role="status">
              <p>{waiting ? 'A step needs your decision.' : 'Updating the plan'}</p>
              <ul>{rerun.map(step => <li key={step.id} className={`is-${step.status}`}>{step.agent}: {step.status === 'completed' ? 'done' : step.status === 'failed' ? 'needs you' : 'working'}</li>)}</ul>
              {waiting && <button className="button primary" onClick={onOpenRun}>Open the steps</button>}
            </div>}
          </div>
          <div className="chat-composer">
            <div className="change-topics" role="group" aria-label="What to change">{CHANGE_TOPICS.map(topic => <button key={topic.key} type="button" disabled={locked} onClick={() => startWith(topic.prompt)}><span aria-hidden="true">{topic.emoji}</span>{topic.label}</button>)}</div>
            {visibleMessages.length < 2 && <div className="suggestion-row">{SUGGESTIONS.map(text => <button key={text} disabled={locked} onClick={() => send(text)}>{text}</button>)}</div>}
            <form onSubmit={event => { event.preventDefault(); send(draft); }}>
              <input ref={inputRef} value={draft} maxLength={1000} disabled={busy} onChange={event => setDraft(event.target.value)} placeholder={updating ? 'Wait for this update to finish' : 'e.g. Add a shehnai at the gate at 7 PM'} aria-label="Ask about or change the plan" />
              <button className="button primary" type="submit" disabled={locked || !draft.trim()}>{busy ? 'Sending…' : remaining > 0 ? `Wait ${remaining}s` : 'Send'}</button>
            </form>
            {error && <p className="chat-error" role="alert">{error}</p>}
          </div>
        </section>
      </div>
    </section>}
    {!open && <button className="chatbot-launcher" onClick={() => setOpen(true)} aria-expanded={open}><span aria-hidden="true">✦</span> Change the plan</button>}
  </aside>;
}
