import { useEffect, useRef, useState } from 'react';
import { briefTurn } from '../api/eventApi';
import { KnowledgeGuide } from './KnowledgeGuide';
import './chatbotDock.css';

const TOTAL_FIELDS = 7;
const EXAMPLE = 'Wedding reception in Bandra for 200 guests on 14 Feb 2027, budget ₹10 lakh';

/**
 * Planning chat with dynamic questions. The user can describe the whole event in
 * one sentence; the backend (/chat/brief) extracts what it can, checks it against
 * planning benchmarks, and asks only for what is missing, with options that fit
 * the event type, city and guest count.
 */
export function ChatPlanner({ onGenerate, onCancel }) {
  const [isOpen, setIsOpen] = useState(true);
  const [guideOpen, setGuideOpen] = useState(false);
  const [messages, setMessages] = useState([]);
  const [answers, setAnswers] = useState({});
  const [brief, setBrief] = useState([]);
  const [next, setNext] = useState(null);
  const [warnings, setWarnings] = useState([]);
  const [dismissed, setDismissed] = useState([]);
  const [ready, setReady] = useState(false);
  const [draft, setDraft] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const historyRef = useRef(null);
  const inputRef = useRef(null);

  const apply = (result, { userText, withPrompt = true } = {}) => {
    setAnswers(result.answers);
    setBrief(result.brief);
    setNext(result.next);
    setWarnings(result.warnings);
    setReady(result.ready);
    const prompt = withPrompt && result.next ? result.next.prompt : '';
    const text = [result.reply, prompt].filter(Boolean).join('\n');
    setMessages(current => [...current, ...(userText ? [{ role: 'user', text: userText }] : []), { role: 'assistant', text }]);
  };

  const send = async (body, userText) => {
    setBusy(true);
    setError('');
    try {
      const result = await briefTurn({ answers, dismissed, ...body });
      apply(result, { userText });
      return result;
    } catch {
      setError('The planning assistant is unavailable. Check that the API is running, then try again.');
      return null;
    } finally {
      setBusy(false);
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  };

  useEffect(() => {
    briefTurn({ message: '', answers: {} })
      .then(result => {
        setNext(result.next);
        setMessages([{ role: 'assistant', text: `Tell me about your event: type, city, guests, budget and date. One sentence is fine, and I'll ask only for what's missing.\n${result.next?.prompt || ''}` }]);
      })
      .catch(() => setError('The planning assistant is unavailable. Check that the API is running, then try again.'));
  }, []);

  useEffect(() => {
    historyRef.current?.scrollTo({ top: historyRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, warnings]);

  const submitText = event => {
    event.preventDefault();
    const text = draft.trim();
    if (!text || busy) return;
    setDraft('');
    send({ message: text, ask: next?.field && answers[next.field] ? next.field : undefined }, text);
  };

  const chooseOption = option => send({ field: next.field, value: option.value }, option.label);
  const applyFix = (warning, option) => send({ patch: option.patch }, option.label);
  const keepAsIs = async warning => {
    const nextDismissed = [...dismissed, warning.id];
    setDismissed(nextDismissed);
    setWarnings(current => current.filter(w => w.id !== warning.id));
    setMessages(current => [...current, { role: 'user', text: 'Keep it as it is' }, { role: 'assistant', text: 'Noted. The plan will flag it as a risk.' }]);
  };
  const editField = field => send({ ask: field }, `Change ${brief.find(item => item.field === field)?.label.toLowerCase() || field}`);

  const generate = async () => {
    setIsGenerating(true);
    try {
      await onGenerate({
        name: answers.name,
        date: answers.date,
        location: answers.location,
        attendees: Number(answers.attendees),
        budget: Number(answers.budget),
        objective: `${answers.eventType}: ${answers.objective}`,
      });
    } finally {
      setIsGenerating(false);
    }
  };

  const filled = brief.length;
  const status = guideOpen ? 'Verified planning knowledge' : ready ? 'Brief ready to generate' : `${filled} of ${TOTAL_FIELDS} details`;

  return <aside className={`chatbot-dock ${isOpen ? 'is-open' : ''}`} aria-label="Event planning chatbot">
    {isOpen && <section className={`chatbot-window ${guideOpen ? 'guide-open' : ''}`}>
      <div className="chatbot-topline"><div><span>EP</span><div><strong>EventPilot Planner</strong><small>{status}</small></div></div><div className="chatbot-header-actions"><button className="chatbot-guide-toggle" onClick={() => setGuideOpen(open => !open)}>{guideOpen ? 'Brief' : 'Guide'}</button><button onClick={() => setIsOpen(false)} aria-label="Minimize planner">-</button></div></div>
      <div className="chatbot-progress"><i style={{ width: `${filled / TOTAL_FIELDS * 100}%` }} /></div>
      {guideOpen && <KnowledgeGuide onClose={() => setGuideOpen(false)} />}
      <div className="chat-layout">
        <section className="chat-panel" aria-label="Planning conversation">
          <div className="chat-history" ref={historyRef} aria-live="polite">
            {messages.map((message, index) => <div className={`chat-message ${message.role}`} key={index}><span>{message.role === 'assistant' ? 'EP' : 'You'}</span><p className="chat-text">{message.text}</p></div>)}
            {messages.length === 1 && !filled && <button className="brief-example" onClick={() => { setDraft(EXAMPLE); inputRef.current?.focus(); }}>Try: “{EXAMPLE}”</button>}
            {warnings.map(warning => <div className="brief-warning" role="status" key={warning.id}><p>{warning.message}</p><div>{warning.options.map(option => <button key={option.label} disabled={busy} onClick={() => applyFix(warning, option)}>{option.label}</button>)}<button className="ghost" disabled={busy} onClick={() => keepAsIs(warning)}>Keep as is</button></div></div>)}
          </div>

          {filled > 0 && !ready && <div className="brief-strip" aria-label="Brief so far">{brief.map(item => <button key={item.field} title={`Change ${item.label.toLowerCase()}`} onClick={() => editField(item.field)} disabled={busy}><small>{item.label}</small>{item.display}</button>)}</div>}

          {ready ? <div className="chat-summary">
            <div className="chat-summary-heading"><div><p className="eyebrow">READY TO GENERATE</p><h2>Planning brief</h2></div></div>
            {brief.map(item => <div key={item.field}><span>{item.label}</span><strong>{item.display}</strong><button aria-label={`Edit ${item.label}`} onClick={() => editField(item.field)}>Edit</button></div>)}
            <button className="button primary" disabled={isGenerating || busy} onClick={generate}>{isGenerating ? 'Starting the planning team...' : 'Generate event plan'}</button>
          </div> : <div className="chat-composer">
            {next?.options?.length > 0 && <><p className="chat-composer-label">Suggested · {next.label}</p><div className="suggestion-row">{next.options.map(option => <button disabled={busy} key={option.value} title={option.hint || option.label} onClick={() => chooseOption(option)}>{option.label}{option.hint && <small>{option.hint}</small>}</button>)}</div></>}
            <form onSubmit={submitText}><input ref={inputRef} disabled={busy} value={draft} onChange={event => setDraft(event.target.value)} placeholder={next?.placeholder || 'Describe your event'} aria-label={next?.prompt || 'Describe your event'} autoFocus /><button className="button primary" disabled={busy || !draft.trim()} type="submit">{busy ? 'Checking...' : 'Send'}</button></form>
            {error && <p className="chat-error">{error}</p>}
          </div>}
        </section>
      </div>
      <button className="text-button chat-cancel" onClick={onCancel}>Return to workspace</button>
    </section>}
    <button className="chatbot-launcher" onClick={() => setIsOpen(open => !open)} aria-expanded={isOpen}>{isOpen ? '×' : <><span>EP</span> Plan an event</>}</button>
  </aside>;
}
