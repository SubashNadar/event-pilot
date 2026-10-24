import { useEffect, useMemo, useState } from 'react';
import { API_BASE_URL } from '../lib/config';

const LABEL = {
  logistics_agent: 'Logistics',
  finance_agent: 'Budget & Finance',
  schedule_agent: 'Schedule',
  requirements_agent: 'Requirements',
  marketing_agent: 'Marketing',
  risk_operations_agent: 'Risk & Operations',
  coordination: 'Coordination',
  event_manager: 'Event Manager',
  review_plan: 'Review',
  replan: 'Re-plan',
  recommendations: 'Recommendations'
};

const STATUS_TEXT = { pending: 'Waiting', running: 'Running', completed: 'Done', failed: 'Failed', skipped: 'Skipped' };

async function loadLatestRun(eventId) {
  const latest = await fetch(`${API_BASE_URL}/events/${eventId}/runs/latest`);
  if (latest.status === 404) return null;
  if (!latest.ok) throw new Error('run unavailable');
  const { id } = await latest.json();
  const snapshot = await fetch(`${API_BASE_URL}/runs/${id}`);
  if (!snapshot.ok) throw new Error('run unavailable');
  return snapshot.json();
}

/**
 * Groups a run's events into passes. Each re-plan starts a new pass, and the pass
 * records why: the review problems that triggered it.
 */
function buildPasses(events) {
  const passes = [];
  let pass = null;
  let reviewIssues = null;
  const open = (name, reason) => {
    pass = { name, reason, nodes: [], byId: {} };
    passes.push(pass);
  };
  const nodeFor = stepId => {
    if (!pass) open('Pass 1', null);
    let node = pass.byId[stepId];
    if (!node) {
      node = { id: stepId, status: 'pending', attempts: 0, reason: '', did: [] };
      pass.byId[stepId] = node;
      pass.nodes.push(node);
    }
    return node;
  };
  const notes = [];
  for (const event of events) {
    if (event.type === 'step_started') {
      if (event.stepId === 'replan' && pass) open(`Pass ${passes.length + 1}`, reviewIssues || 'The review found problems to fix');
      const node = nodeFor(event.stepId);
      node.status = 'running';
      node.attempts = Math.max(node.attempts, event.attempt || 1);
    } else if (event.type === 'step_completed') {
      const node = nodeFor(event.stepId);
      node.status = 'completed';
      node.did = event.summary?.did || [];
      node.reason = event.summary?.verification?.reason || '';
      if (event.stepId === 'review_plan') {
        const passed = event.summary?.verification?.passed;
        reviewIssues = passed ? null : node.reason;
      }
    } else if (event.type === 'step_failed') {
      const node = nodeFor(event.stepId);
      node.status = 'failed';
      node.reason = event.error || '';
    } else if (event.type === 'step_skipped') {
      const node = nodeFor(event.stepId);
      node.status = 'skipped';
      node.reason = event.reason || '';
    } else if (event.type === 'recovery_chosen' || event.type === 'run_resumed') {
      const node = nodeFor(event.stepId);
      node.reason = `You chose: ${event.label}`;
    } else if (event.type === 'notice') {
      notes.push(event.message);
    }
  }
  return { passes, notes };
}

export default function AgentFlow({ eventId }) {
  const [state, setState] = useState({ phase: 'loading' });

  useEffect(() => {
    let alive = true;
    if (!eventId) {
      setState({ phase: 'empty' });
      return undefined;
    }
    setState({ phase: 'loading' });
    loadLatestRun(eventId)
      .then(data => alive && setState(data ? { phase: 'ready', ...data } : { phase: 'empty' }))
      .catch(() => alive && setState({ phase: 'error' }));
    return () => { alive = false; };
  }, [eventId]);

  const { passes, notes } = useMemo(() => (state.events ? buildPasses(state.events) : { passes: [], notes: [] }), [state.events]);

  if (state.phase === 'loading') return <section className="flow-page"><p className="board-meta">Loading the latest run…</p></section>;
  if (state.phase === 'empty') return <section className="flow-page"><h1 className="ws-title">Agent activity</h1><p className="board-meta">No planning run yet. Save the brief or press Re-plan to start one.</p></section>;
  if (state.phase === 'error') return <section className="flow-page"><h1 className="ws-title">Agent activity</h1><p className="board-meta">The run could not be loaded. Check that the backend is running.</p></section>;

  const status = state.run?.status;
  const end = status === 'completed' ? 'Plan ready. The review passed.'
    : status === 'cancelled' ? 'Stopped by you before the plan finished.'
    : status === 'error' ? `The run stopped: ${state.run?.error || 'unexpected error'}`
    : status === 'paused' ? 'Waiting for your answer on a failed step.'
    : 'Still running.';

  return <section className="flow-page" aria-label="Agent activity">
    <header className="ws-header">
      <div>
        <p className="board-kicker">Agent activity</p>
        <h1 className="ws-title">How the plan was made</h1>
        <p className="board-meta">{passes.length} pass{passes.length === 1 ? '' : 'es'} · run {status}</p>
      </div>
    </header>
    <ol className="flow">
      {passes.map(pass => <li key={pass.name} className="flow-pass">
        <h2 className="flow-pass-title">{pass.name}</h2>
        {pass.reason && <p className="flow-why"><strong>Why:</strong> {pass.reason}</p>}
        <div className="flow-nodes">
          {pass.nodes.map(node => <article key={node.id} className={`flow-node ${node.status}`}>
            <header><strong>{LABEL[node.id] || node.id}</strong><span className="flow-status">{STATUS_TEXT[node.status]}</span></header>
            {node.reason && <p>{node.reason}</p>}
            {node.did.length > 0 && <ul>{node.did.map((item, index) => <li key={index}>{item}</li>)}</ul>}
          </article>)}
        </div>
      </li>)}
    </ol>
    {notes.map((note, index) => <p key={index} className="flow-note">{note}</p>)}
    <p className="flow-end"><strong>End:</strong> {end}</p>
  </section>;
}
