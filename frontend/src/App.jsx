import { useState } from 'react';
import { jsPDF } from 'jspdf';
import { buildEventPlan, initialEvent } from './data/planData';
import { Sidebar } from './components/Sidebar';
import { PlanWorkspace } from './components/PlanWorkspace';
import { EventBrief } from './components/EventBrief';
import { createEvent as createApiEvent, generatePlan, reviseBudget } from './api/eventApi';
import { toUiPlan } from './api/planAdapter';

const money = value => `₹${new Intl.NumberFormat('en-IN').format(value)}`;
const formatDate = date => new Date(`${date}T00:00:00`).toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });

function createApprovedBlueprintPdf({ event, plan, forecast, reduced, riskState }) {
  const pdf = new jsPDF({ unit: 'mm', format: 'a4' });
  const pageWidth = 210;
  const pageHeight = 297;
  const margin = 18;
  const navy = [14, 30, 49];
  const ink = [25, 43, 55];
  const teal = [20, 111, 105];
  const amber = [224, 166, 66];
  const paper = [248, 246, 240];
  const muted = [93, 108, 115];
  const shares = reduced ? plan.reducedShares : plan.budgetShares;
  const reserve = event.budget - forecast;
  const allocationColors = [[20, 111, 105], [224, 166, 66], [202, 102, 82], [74, 119, 168], [110, 150, 129], [132, 99, 158]];
  const cleanText = value => String(value || '').replace(/[–—]/g, '-');
  const title = cleanText(event.name);
  const footer = page => {
    pdf.setDrawColor(210, 214, 208);
    pdf.line(margin, 283, pageWidth - margin, 283);
    pdf.setTextColor(...muted);
    pdf.setFont('helvetica', 'normal');
    pdf.setFontSize(8);
    pdf.text('EVENTPILOT  |  APPROVED EVENT BLUEPRINT', margin, 289);
    pdf.text(`PAGE ${page}`, pageWidth - margin, 289, { align: 'right' });
  };
  const wrapped = (text, width, size = 10) => {
    pdf.setFontSize(size);
    return pdf.splitTextToSize(cleanText(text), width);
  };

  // Cover: deliberately spacious, so the event remains the first thing a reader sees.
  pdf.setFillColor(...navy);
  pdf.rect(0, 0, pageWidth, pageHeight, 'F');
  pdf.setFillColor(...amber);
  pdf.circle(188, 25, 31, 'F');
  pdf.setDrawColor(55, 76, 98);
  pdf.setLineWidth(.45);
  pdf.circle(188, 25, 39, 'S');
  pdf.circle(188, 25, 47, 'S');
  pdf.setTextColor(...amber);
  pdf.setFont('helvetica', 'bold');
  pdf.setFontSize(9);
  pdf.text('APPROVED EVENT BLUEPRINT  |  EVENTPILOT', margin, 31);
  pdf.setTextColor(226, 234, 236);
  pdf.setFont('times', 'bold');
  pdf.setFontSize(39);
  const titleLines = wrapped(title, 152, 39);
  pdf.text(titleLines, margin, 82);
  const titleEnd = 82 + (titleLines.length - 1) * 14;
  pdf.setTextColor(183, 202, 209);
  pdf.setFont('helvetica', 'normal');
  pdf.setFontSize(12);
  pdf.text(wrapped(event.objective, 135, 12), margin, titleEnd + 21);
  pdf.setDrawColor(94, 123, 140);
  pdf.line(margin, 180, pageWidth - margin, 180);
  const facts = [
    ['DATE', formatDate(event.date)],
    ['CITY', event.location],
    ['ATTENDEES', `${event.attendees} invited guests`],
  ];
  facts.forEach(([label, value], index) => {
    const x = margin + index * 58;
    pdf.setTextColor(...amber);
    pdf.setFont('helvetica', 'bold');
    pdf.setFontSize(8);
    pdf.text(label, x, 197);
    pdf.setTextColor(238, 242, 243);
    pdf.setFont('helvetica', 'normal');
    pdf.setFontSize(11);
    pdf.text(wrapped(value, 50, 11), x, 208);
  });
  pdf.setTextColor(183, 202, 209);
  pdf.setFontSize(9);
  pdf.text('Prepared by the EventPilot autonomous planning team', margin, 267);
  pdf.text('READY FOR EXECUTION', pageWidth - margin, 267, { align: 'right' });

  // Page two gives budget decisions a visual, review-friendly story.
  pdf.addPage();
  pdf.setFillColor(...paper);
  pdf.rect(0, 0, pageWidth, pageHeight, 'F');
  pdf.setTextColor(...teal);
  pdf.setFont('helvetica', 'bold');
  pdf.setFontSize(9);
  pdf.text('01  |  STRATEGY AND INVESTMENT', margin, 25);
  pdf.setTextColor(...ink);
  pdf.setFont('times', 'bold');
  pdf.setFontSize(29);
  pdf.text('Where every rupee goes', margin, 42);
  pdf.setTextColor(...muted);
  pdf.setFont('helvetica', 'normal');
  pdf.setFontSize(10.5);
  pdf.text(wrapped('A practical allocation built around the approved event budget, with a visible contingency reserve.', 145, 10.5), margin, 53);
  const statY = 81;
  [
    ['APPROVED BUDGET', money(event.budget)],
    ['FINAL FORECAST', money(forecast)],
    [reserve >= 0 ? 'RESERVE' : 'OVER BUDGET', money(Math.abs(reserve))],
  ].forEach(([label, value], index) => {
    const x = margin + index * 58;
    pdf.setTextColor(...teal);
    pdf.setFont('helvetica', 'bold');
    pdf.setFontSize(8);
    pdf.text(label, x, statY);
    pdf.setTextColor(...ink);
    pdf.setFont('times', 'bold');
    pdf.setFontSize(19);
    pdf.text(value, x, statY + 12);
  });
  pdf.setDrawColor(214, 218, 210);
  pdf.line(margin, 104, pageWidth - margin, 104);
  let barY = 121;
  plan.budgetLabels.forEach((label, index) => {
    const share = shares[index] || 0;
    const amount = Math.round(forecast * share / 100);
    pdf.setTextColor(...ink);
    pdf.setFont('helvetica', 'bold');
    pdf.setFontSize(10);
    pdf.text(cleanText(label), margin, barY);
    pdf.setTextColor(...muted);
    pdf.setFont('helvetica', 'normal');
    pdf.text(`${money(amount)}  |  ${share}%`, pageWidth - margin, barY, { align: 'right' });
    pdf.setFillColor(224, 226, 220);
    pdf.roundedRect(margin, barY + 5, 174, 5, 2, 2, 'F');
    pdf.setFillColor(...allocationColors[index % allocationColors.length]);
    pdf.roundedRect(margin, barY + 5, Math.max(7, 174 * share / 100), 5, 2, 2, 'F');
    barY += 22;
  });
  pdf.setFillColor(230, 239, 232);
  pdf.roundedRect(margin, 259, 174, 15, 2, 2, 'F');
  pdf.setTextColor(...teal);
  pdf.setFont('helvetica', 'bold');
  pdf.setFontSize(9.5);
  pdf.text(reserve >= 0 ? `${money(reserve)} remains available for approved contingencies.` : `${money(Math.abs(reserve))} requires a final budget adjustment before vendor confirmation.`, margin + 7, 268);
  footer(2);

  // Page three is the execution handoff: venue, timed agenda, risks, and human approval.
  pdf.addPage();
  pdf.setFillColor(...paper);
  pdf.rect(0, 0, pageWidth, pageHeight, 'F');
  pdf.setTextColor(...teal);
  pdf.setFont('helvetica', 'bold');
  pdf.setFontSize(9);
  pdf.text('02  |  EXECUTION HANDOFF', margin, 25);
  pdf.setTextColor(...ink);
  pdf.setFont('times', 'bold');
  pdf.setFontSize(28);
  pdf.text('The plan in motion', margin, 42);
  pdf.setDrawColor(214, 218, 210);
  pdf.line(margin, 52, pageWidth - margin, 52);
  pdf.setTextColor(...teal);
  pdf.setFont('helvetica', 'bold');
  pdf.setFontSize(8);
  pdf.text('VENUE AND LOGISTICS', margin, 66);
  pdf.setTextColor(...ink);
  pdf.setFont('times', 'bold');
  pdf.setFontSize(17);
  pdf.text(wrapped(`${plan.venue.name}, ${plan.venue.area}`, 82, 17), margin, 77);
  pdf.setFont('helvetica', 'normal');
  pdf.setFontSize(9.5);
  pdf.setTextColor(...muted);
  pdf.text(wrapped(plan.logistics.join('. ') + '.', 82, 9.5), margin, 95);
  pdf.setTextColor(...teal);
  pdf.setFont('helvetica', 'bold');
  pdf.setFontSize(8);
  pdf.text('MARKETING READINESS', 112, 66);
  pdf.setTextColor(...ink);
  pdf.setFont('helvetica', 'bold');
  pdf.setFontSize(12);
  pdf.text(wrapped(plan.marketing.title, 80, 12), 112, 77);
  pdf.setTextColor(...muted);
  pdf.setFont('helvetica', 'normal');
  pdf.setFontSize(9.5);
  pdf.text(wrapped(plan.marketing.description, 80, 9.5), 112, 94);
  pdf.setDrawColor(214, 218, 210);
  pdf.line(margin, 114, pageWidth - margin, 114);
  pdf.setTextColor(...teal);
  pdf.setFont('helvetica', 'bold');
  pdf.setFontSize(8);
  pdf.text('EVENT-DAY AGENDA', margin, 128);
  let agendaY = 140;
  plan.agenda.slice(0, 5).forEach(row => {
    pdf.setTextColor(...teal);
    pdf.setFont('helvetica', 'bold');
    pdf.setFontSize(9);
    pdf.text(cleanText(row[0]), margin, agendaY);
    pdf.setTextColor(...ink);
    pdf.setFontSize(10);
    pdf.text(cleanText(row[1]), 47, agendaY);
    pdf.setTextColor(...muted);
    pdf.setFont('helvetica', 'normal');
    pdf.setFontSize(8.5);
    pdf.text(wrapped(row[2], 90, 8.5), 103, agendaY);
    agendaY += 14;
  });
  pdf.setDrawColor(214, 218, 210);
  pdf.line(margin, 214, pageWidth - margin, 214);
  pdf.setTextColor(...teal);
  pdf.setFont('helvetica', 'bold');
  pdf.setFontSize(8);
  pdf.text('RISK DECISIONS', margin, 228);
  let riskY = 240;
  plan.risks.slice(0, 2).forEach((risk, index) => {
    const recorded = index === 0 ? riskState.fallback : riskState.monitoring;
    pdf.setFillColor(...(recorded ? [219, 236, 225] : [252, 231, 212]));
    pdf.roundedRect(margin, riskY - 5, 21, 7, 1.5, 1.5, 'F');
    pdf.setTextColor(...(recorded ? teal : [168, 88, 31]));
    pdf.setFont('helvetica', 'bold');
    pdf.setFontSize(7.5);
    pdf.text(recorded ? 'RECORDED' : 'ACTION', margin + 10.5, riskY, { align: 'center' });
    pdf.setTextColor(...ink);
    pdf.setFontSize(9.5);
    pdf.text(cleanText(risk.title), 45, riskY);
    riskY += 13;
  });
  pdf.setFillColor(...navy);
  pdf.roundedRect(margin, 263, 174, 13, 2, 2, 'F');
  pdf.setTextColor(242, 246, 245);
  pdf.setFont('helvetica', 'bold');
  pdf.setFontSize(9);
  pdf.text('APPROVED BY THE EVENT OWNER  |  READY FOR CONTROLLED EXECUTION', margin + 7, 271.5);
  footer(3);
  pdf.save(`${title.replace(/[^a-z0-9]+/gi, '-').toLowerCase()}-approved-blueprint.pdf`);
}

function Overview({ event, plan, forecast, setPlanTab, setView, activities, approved, openRiskCount, riskState, onApprove, onExport }) {
  const under = event.budget - forecast;
  const primaryRisk = plan.risks[0];
  return <section className="view active"><div className="title-row"><div><p className="eyebrow">EVENT #EP-2048</p><h1>{event.name}</h1><p className="event-meta">{formatDate(event.date)} <span /> {event.location} <span /> {event.attendees} attendees</p></div><div className="title-actions"><button className="button secondary" disabled={!approved} onClick={onExport}>↓ Export PDF</button><button className="button primary" disabled={approved} onClick={onApprove}>{approved ? 'Approved ✓' : 'Approve plan'}</button></div></div>
    <div className="status-strip"><span className="status-icon">✓</span><div><strong>{approved ? 'Plan is approved for execution' : openRiskCount ? 'Plan is ready for review' : 'Plan is ready for approval'}</strong><span>{approved ? 'The final blueprint is ready to export.' : openRiskCount ? `${openRiskCount} decision${openRiskCount === 1 ? '' : 's'} need your attention before approval.` : 'All risk actions are complete. You can approve the plan.'}</span></div>{!approved && openRiskCount > 0 && <button onClick={() => setPlanTab('risks')}>Review decisions <span>→</span></button>}</div>
    <div className="metric-grid"><article className="metric-card"><p>Planning status</p><strong className="status-ready">{approved ? 'Approved' : openRiskCount ? 'Ready for review' : 'Ready to approve'}</strong><small>Last agent update 2 min ago</small></article><article className="metric-card"><p>Budget forecast</p><strong>{money(forecast)}</strong><small>{money(Math.abs(under))} {under >= 0 ? 'under target' : 'over target'}</small></article><article className="metric-card"><p>Plan confidence</p><strong>{plan.confidence}<span>%</span></strong><div className="confidence-bar"><i style={{ width: `${plan.confidence}%` }} /></div><small>Based on current event assumptions</small></article><article className="metric-card"><p>Open risks</p><strong className="risk-number">{openRiskCount}</strong><small>{openRiskCount ? 'Actions required' : 'All actions recorded'}</small></article></div>
    <div className="content-grid"><section className="panel plan-health"><div className="panel-heading"><div><p className="eyebrow">PLAN HEALTH</p><h2>Cross-team readiness</h2></div><button className="text-button" onClick={() => setView('plan')}>Open workspace →</button></div><div className="health-list"><div><span className="health-symbol good">✓</span><div><strong>Venue and capacity</strong><small>{plan.venue.name} supports {event.attendees} guests</small></div><em>{plan.venue.status}</em></div><div><span className="health-symbol good">✓</span><div><strong>Budget allocation</strong><small>Contingency reserve is included in the plan</small></div><em>On target</em></div><div><span className={`health-symbol ${riskState.fallback ? 'good' : 'warn'}`}>{riskState.fallback ? '✓' : '!'}</span><div><strong>{primaryRisk.title}</strong><small>{riskState.fallback ? primaryRisk.resolved : primaryRisk.detail}</small></div><button className="small-action" onClick={() => setPlanTab('risks')}>{riskState.fallback ? 'View' : 'Review'}</button></div><div><span className="health-symbol info">↗</span><div><strong>{plan.marketing.title}</strong><small>{plan.marketing.checks[0]}</small></div><button className="small-action" onClick={() => setPlanTab('marketing')}>View</button></div></div></section><section className="panel agent-panel"><div className="panel-heading"><div><p className="eyebrow">MULTI-AGENT TEAM</p><h2>Live planning activity</h2></div><button className="text-button" onClick={() => setView('activity')}>View all →</button></div><ol className="agent-feed">{activities.slice(0, 3).map((activity, index) => <li key={`${activity[0]}-${index}`}><span className={`feed-avatar ${['finance','manager','logistics'][index]}`}>{activity[3]}</span><div><strong>{activity[1]}</strong><p>{activity[2]}</p><small>{index === 0 ? '2 min ago' : index === 1 ? '8 min ago' : '14 min ago'}</small></div></li>)}</ol></section></div>
    <section className="panel agenda-panel"><div className="panel-heading"><div><p className="eyebrow">EVENT DAY</p><h2>Draft agenda</h2></div><button className="text-button" onClick={() => setPlanTab('schedule')}>Full schedule →</button></div><div className="agenda">{plan.overviewAgenda.map(row => <div key={row[0]}><time>{row[0]}</time><span /><p><strong>{row[1]}</strong><small>{row[2]}</small></p></div>)}</div></section>
  </section>;
}

function Activity({ activities }) { return <section className="view active"><div className="view-heading"><p className="eyebrow">PLANNING RUN</p><h1>Agent activity</h1><p>Human-readable activity from the planning workflow. This interface intentionally omits private chain-of-thought.</p></div><section className="panel activity-log">{activities.map((activity, index) => <article className="activity-entry" key={`${activity[0]}-${index}`}><time>{activity[0]}</time><span className="activity-marker">{activity[3]}</span><div><h3>{activity[1]}</h3><p>{activity[2]}</p></div></article>)}</section></section>; }

export default function App() {
  const [event, setEvent] = useState(initialEvent); const [eventId, setEventId] = useState(null); const [apiPlan, setApiPlan] = useState(null); const [view, setView] = useState('overview'); const [planTab, setPlanTab] = useState('logistics'); const [forecast, setForecast] = useState(464000); const [reduced, setReduced] = useState(false); const [budgetBeforeReduction, setBudgetBeforeReduction] = useState(null); const [activities, setActivities] = useState(buildEventPlan(initialEvent).activity); const [toast, setToast] = useState(''); const [approved, setApproved] = useState(false); const [riskState, setRiskState] = useState({ fallback: false, monitoring: false }); const [newEvent, setNewEvent] = useState(false); const [newEventName, setNewEventName] = useState(''); const plan = apiPlan || buildEventPlan(event); const openRiskCount = Number(!riskState.fallback) + Number(!riskState.monitoring);
  const notify = message => { setToast(message); window.setTimeout(() => setToast(''), 2600); };
  const addActivity = (agent, detail, marker = 'M') => setActivities(items => [[new Date().toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit', hour12: true }), agent, detail, marker], ...items]);
  const selectPlanTab = tab => { setPlanTab(tab); setView('plan'); window.scrollTo({ top: 0, behavior: 'smooth' }); };
  const applyApiPlan = (serverPlan, brief) => { const nextPlan = toUiPlan(serverPlan, buildEventPlan(brief)); setApiPlan(nextPlan); setForecast(serverPlan.budget_forecast); setActivities(nextPlan.activity); };
  const syncBudgetPlan = async brief => { try { let currentEventId = eventId; if (!currentEventId) { const savedEvent = await createApiEvent(brief); currentEventId = savedEvent.id; setEventId(currentEventId); } applyApiPlan(await reviseBudget(currentEventId, brief.budget), brief); } catch { setApiPlan(null); notify('API unavailable. Showing the local planning fallback.'); } };
  const reduceBudget = () => { if (reduced) return; const nextBudget = Math.round(event.budget * .8); const nextEvent = { ...event, budget: nextBudget }; setBudgetBeforeReduction(event.budget); setReduced(true); setEvent(nextEvent); setForecast(Math.round(nextBudget * .98)); setApiPlan(null); addActivity('Budget & Finance', 'Created a revised plan for a 20% reduced budget.', '₹'); syncBudgetPlan(nextEvent); notify('Budget revision complete. Version 04 is ready for review.'); };
  const restoreBudget = () => { if (!reduced || budgetBeforeReduction === null) return; const nextEvent = { ...event, budget: budgetBeforeReduction }; setEvent(nextEvent); setForecast(Math.round(budgetBeforeReduction * .928)); setReduced(false); setBudgetBeforeReduction(null); setApiPlan(null); addActivity('Budget & Finance', 'Restored the original budget scenario.', '₹'); syncBudgetPlan(nextEvent); notify('Original budget restored.'); };
  const saveEvent = async updated => { const fallbackPlan = buildEventPlan(updated); setEvent(updated); setEventId(null); setApiPlan(null); setForecast(Math.round(updated.budget * .928)); setActivities([['Now', 'Event Manager', `Generated a ${fallbackPlan.type} plan from the revised event brief.`, 'M'], ...fallbackPlan.activity]); setReduced(false); setBudgetBeforeReduction(null); setRiskState({ fallback: false, monitoring: false }); setApproved(false); setView('overview'); try { const savedEvent = await createApiEvent(updated); const serverPlan = await generatePlan(savedEvent.id); setEventId(savedEvent.id); applyApiPlan(serverPlan, updated); notify('Plan generated by the EventPilot API.'); } catch { notify('API unavailable. Showing the local planning fallback.'); } };
  const resolveRisk = () => { if (riskState.fallback) return; setRiskState(state => ({ ...state, fallback: true })); addActivity('Risk & Operations', `Recorded a fallback for: ${plan.risks[0].title}.`, 'R'); notify('Risk fallback recorded.'); };
  const monitorRisk = () => { if (riskState.monitoring) return; setRiskState(state => ({ ...state, monitoring: true })); addActivity('Risk & Operations', `Started monitoring: ${plan.risks[1].title}.`, 'R'); notify('Risk monitoring is active.'); };
  const approve = () => { if (openRiskCount) { selectPlanTab('risks'); notify('Complete the remaining risk actions before approval.'); return; } setApproved(true); addActivity('Event Manager', 'Plan approved by the event owner and marked ready for execution.'); notify('Plan approved. Your final blueprint is ready to export.'); };
  const exportPlan = () => { if (!approved) return notify('Approve the plan before exporting.'); createApprovedBlueprintPdf({ event, plan, forecast, reduced, riskState }); notify('Designed blueprint PDF downloaded.'); };
  const createNewEvent = () => { if (!newEventName.trim()) return notify('Add an event name to continue.'); const created = { ...initialEvent, name: newEventName.trim(), objective: 'Create a practical event plan covering venue, budget, schedule, communications, and operational risks.' }; const createdPlan = buildEventPlan(created); setEvent(created); setEventId(null); setApiPlan(null); setForecast(Math.round(created.budget * .928)); setActivities([['Now', 'Event Manager', `Created a ${createdPlan.type} planning brief for ${created.name}.`, 'M'], ...createdPlan.activity]); setReduced(false); setBudgetBeforeReduction(null); setRiskState({ fallback: false, monitoring: false }); setApproved(false); setNewEvent(false); setNewEventName(''); setView('brief'); notify('New event created. Complete the event brief.'); };
  return <div className="app-shell"><Sidebar view={view} setView={setView} setPlanTab={selectPlanTab} onNewEvent={() => setNewEvent(true)} /><main className="main-content"><header className="topbar"><div className="crumb"><span>Events</span><b>/</b><strong>{event.name}</strong></div><div className="topbar-actions"><span className="saved-state">All changes saved</span><button className="icon-button" aria-label="Notifications" onClick={() => notify(`${openRiskCount} risk action${openRiskCount === 1 ? '' : 's'} require attention.`)}>♧<span className="notification-dot" /></button><button className="avatar" aria-label="Account">BI</button></div></header>{view === 'overview' && <Overview event={event} plan={plan} forecast={forecast} setPlanTab={selectPlanTab} setView={setView} activities={activities} approved={approved} openRiskCount={openRiskCount} riskState={riskState} onApprove={approve} onExport={exportPlan} />}{view === 'brief' && <EventBrief event={event} onSave={saveEvent} />}{view === 'plan' && <PlanWorkspace tab={planTab} setTab={setPlanTab} event={event} plan={plan} forecast={forecast} reduced={reduced} onReduce={reduceBudget} onRestore={restoreBudget} riskState={riskState} onResolveRisk={resolveRisk} onMonitorRisk={monitorRisk} money={money} />}{view === 'activity' && <Activity activities={activities} />}</main>{newEvent && <div className="modal-backdrop" role="presentation"><section className="modal" role="dialog" aria-modal="true" aria-label="Start a new event plan"><button className="dialog-close" onClick={() => setNewEvent(false)} aria-label="Close">×</button><p className="eyebrow">NEW EVENT</p><h2>Start an event plan</h2><p>Create a fresh working brief. The planning team will use it as the shared source of truth.</p><label>Event name<input value={newEventName} onChange={e => setNewEventName(e.target.value)} placeholder="e.g. Ananya's birthday celebration" autoFocus /></label><div className="modal-actions"><button className="button secondary" onClick={() => setNewEvent(false)}>Cancel</button><button className="button primary" onClick={createNewEvent}>Create event</button></div></section></div>}<div className={`toast ${toast ? 'show' : ''}`} role="status">{toast}</div></div>;
}
