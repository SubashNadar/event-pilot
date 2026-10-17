import { useMemo, useState } from 'react';
import { validatePlanningChatTurn } from '../api/eventApi';
import { KnowledgeGuide } from './KnowledgeGuide';
import './chatbotDock.css';

const steps = [
  { field: 'eventType', label: 'Event type', prompt: 'What kind of event are you planning?', options: ['Wedding reception', 'Workshop', 'Conference', 'Birthday celebration'] },
  { field: 'name', label: 'Event name', prompt: 'Great. What should we call this event?', placeholder: 'e.g. Meera and Karthik Wedding Reception' },
  { field: 'date', label: 'Event date', prompt: 'When will it take place?', type: 'date' },
  { field: 'location', label: 'Location', prompt: 'Where will it be held?', options: ['Bengaluru', 'Mumbai', 'Delhi NCR', 'Hyderabad'], placeholder: 'City or neighbourhood' },
  { field: 'attendees', label: 'Attendees', prompt: 'How many guests or attendees are you expecting?', options: ['50', '100', '200', '350'], placeholder: 'Enter a number', type: 'number' },
  { field: 'budget', label: 'Budget', prompt: 'What is the total budget in INR?', options: ['250000', '500000', '1000000', '1500000'], placeholder: 'Enter total INR budget', type: 'number' },
  { field: 'objective', label: 'Objective', prompt: 'Finally, what outcome should the plan prioritize?', options: ['Guest experience and smooth operations', 'Learning and attendee engagement', 'Elegant celebration and hospitality'], placeholder: 'Describe the event outcome' },
];

const displayValue = (field, value) => field === 'budget' ? `₹${new Intl.NumberFormat('en-IN').format(Number(value || 0))}` : value;

export function ChatPlanner({ onGenerate, onCancel }) {
  const [isOpen, setIsOpen] = useState(true);
  const [guideOpen, setGuideOpen] = useState(false);
  const [stepIndex, setStepIndex] = useState(0);
  const [answers, setAnswers] = useState({});
  const [draft, setDraft] = useState('');
  const [error, setError] = useState('');
  const [assistantReplies, setAssistantReplies] = useState({});
  const [isChecking, setIsChecking] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const complete = stepIndex === steps.length;
  const step = steps[stepIndex];
  const messages = useMemo(() => steps.slice(0, Math.min(stepIndex + 1, steps.length)).flatMap((item, index) => {
    const result = [{ role: 'assistant', text: item.prompt }];
    if (index < stepIndex) { result.push({ role: 'user', text: displayValue(item.field, answers[item.field]) }); if (assistantReplies[index]) result.push({ role: 'assistant', text: assistantReplies[index] }); }
    return result;
  }), [answers, assistantReplies, stepIndex]);

  const submitAnswer = async value => {
    const answer = String(value ?? draft).trim();
    if (!answer) return setError(`Please provide ${step.label.toLowerCase()} to continue.`);
    setIsChecking(true);
    try {
      const result = await validatePlanningChatTurn(step.field, answer, answers);
      if (!result.accepted) return setError(result.clarification || result.reply);
      setAnswers(current => ({ ...current, [step.field]: answer }));
      setAssistantReplies(current => ({ ...current, [stepIndex]: result.reply }));
      setDraft('');
      setError('');
      setStepIndex(current => current + 1);
    } catch {
      setError('The planning assistant is unavailable. Check that the API is running, then try again.');
    } finally {
      setIsChecking(false);
    }
  };

  const editAnswer = index => {
    setDraft(answers[steps[index].field] || '');
    setAnswers(current => Object.fromEntries(Object.entries(current).filter(([field]) => steps.findIndex(step => step.field === field) < index)));
    setStepIndex(index);
    setAssistantReplies(current => Object.fromEntries(Object.entries(current).filter(([key]) => Number(key) < index)));
    setError('');
  };

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

  return <aside className={`chatbot-dock ${isOpen ? 'is-open' : ''}`} aria-label="Event planning chatbot">
    {isOpen && <section className={`chatbot-window ${guideOpen ? 'guide-open' : ''}`}>
    <div className="chatbot-topline"><div><span>EP</span><div><strong>EventPilot Planner</strong><small>{guideOpen ? 'Verified planning knowledge' : complete ? 'Brief ready to generate' : `Question ${stepIndex + 1} of ${steps.length}`}</small></div></div><div className="chatbot-header-actions"><button className="chatbot-guide-toggle" onClick={() => setGuideOpen(open => !open)}>{guideOpen ? 'Brief' : 'Guide'}</button><button onClick={() => setIsOpen(false)} aria-label="Minimize planner">-</button></div></div>
    <div className="chatbot-progress"><i style={{ width: `${stepIndex / steps.length * 100}%` }} /></div>{guideOpen && <KnowledgeGuide onClose={() => setGuideOpen(false)} />}<div className="chat-layout">
      <section className="chat-panel" aria-label="Planning conversation"><div className="chat-history">{messages.map((message, index) => <div className={`chat-message ${message.role}`} key={`${message.role}-${index}`}><span>{message.role === 'assistant' ? 'EP' : 'You'}</span><p>{message.text}</p></div>)}{complete && <div className="chat-message assistant"><span>EP</span><p>I have everything needed. Review the brief below, then generate the plan.</p></div>}</div>
        {complete ? <div className="chat-summary"><div className="chat-summary-heading"><div><p className="eyebrow">READY TO GENERATE</p><h2>Planning brief</h2></div><button className="text-button" onClick={() => editAnswer(0)}>Edit answers</button></div>{steps.map((item, index) => <div key={item.field}><span>{item.label}</span><strong>{displayValue(item.field, answers[item.field])}</strong><button aria-label={`Edit ${item.label}`} onClick={() => editAnswer(index)}>Edit</button></div>)}<button className="button primary" disabled={isGenerating} onClick={generate}>{isGenerating ? 'Generating multi-agent plan...' : 'Generate event plan'}</button></div> : <div className="chat-composer"><p className="chat-composer-label">Suggested replies</p><div className="suggestion-row">{step.options?.map(option => <button disabled={isChecking} key={option} onClick={() => submitAnswer(option)}>{step.field === 'budget' ? displayValue('budget', option) : option}</button>)}</div><form onSubmit={event => { event.preventDefault(); submitAnswer(); }}><input disabled={isChecking} type={step.type || 'text'} value={draft} onChange={event => setDraft(event.target.value)} placeholder={step.placeholder || 'Type your answer'} autoFocus /><button className="button primary" disabled={isChecking} type="submit">{isChecking ? 'Checking...' : 'Continue'}</button></form>{error && <p className="chat-error">{error}</p>}</div>}
      </section></div><button className="text-button chat-cancel" onClick={onCancel}>Return to workspace</button>
    </section>}<button className="chatbot-launcher" onClick={() => setIsOpen(open => !open)} aria-expanded={isOpen}>{isOpen ? '×' : <><span>EP</span> Plan an event</>}</button>
  </aside>;
}
