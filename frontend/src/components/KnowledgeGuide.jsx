import { useState } from 'react';
import { queryKnowledge } from '../api/eventApi';
import './knowledgeGuide.css';

const suggestions = [
  'What should we confirm for an event with more than 150 guests?',
  'When should we finalize catering numbers?',
  'What should a wedding reception communication include?'
];

export function KnowledgeGuide({ onClose }) {
  const [question, setQuestion] = useState('');
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const ask = async value => {
    const nextQuestion = value.trim();
    if (!nextQuestion) return;
    setLoading(true);
    setError('');
    try {
      setResult(await queryKnowledge(nextQuestion));
      setQuestion(nextQuestion);
    } catch (requestError) {
      setError(requestError.message || 'The knowledge guide is unavailable right now.');
    } finally {
      setLoading(false);
    }
  };

  return <section className="knowledge-guide" aria-label="Verified planning knowledge guide">
    <div className="knowledge-guide-heading"><div><p className="eyebrow">VERIFIED PLANNING KNOWLEDGE</p><h2>Ask the planning guide</h2><p>Answers are grounded in EventPilot reference documents.</p></div><button onClick={onClose}>Back to brief</button></div>
    {!result && <div className="knowledge-suggestions">{suggestions.map(suggestion => <button key={suggestion} onClick={() => ask(suggestion)}>{suggestion}</button>)}</div>}
    {result && <article className={`knowledge-answer ${result.grounded ? 'grounded' : ''}`}><span>{result.grounded ? 'Verified answer' : 'No verified source'}</span><p>{result.answer}</p>{result.citations.length > 0 && <div className="knowledge-citations"><strong>Sources</strong>{result.citations.map(citation => <div key={`${citation.source}-${citation.excerpt}`}><b>{citation.title}</b><small>{citation.source} · {Math.round(citation.relevance * 100)}% relevance</small></div>)}</div>}</article>}
    <form className="knowledge-composer" onSubmit={event => { event.preventDefault(); ask(question); }}><input value={question} onChange={event => setQuestion(event.target.value)} placeholder="Ask a planning question" aria-label="Ask the planning guide" /><button className="button primary" disabled={loading} type="submit">{loading ? 'Searching...' : 'Ask'}</button></form>{error && <p className="knowledge-error">{error}</p>}
  </section>;
}
