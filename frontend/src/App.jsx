import { useEffect, useState } from 'react';
import { jsPDF } from 'jspdf';
import { buildEventPlan, initialEvent } from './data/planData';
import { Sidebar } from './components/Sidebar';
import { PlanWorkspace } from './components/PlanWorkspace';
import { EventBrief } from './components/EventBrief';
import { ChatPlanner } from './components/ChatPlanner';
import { HomeWelcome } from './components/HomeWelcome';
import { createEvent as createApiEvent, generatePlan, getEvent, getPlan, listEvents, reviseBudget, updateEvent } from './api/eventApi';
import { toUiPlan } from './api/planAdapter';

const money = value => `₹${new Intl.NumberFormat('en-IN').format(value)}`;
const formatDate = date => new Date(`${date}T00:00:00`).toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
const toUiEvent = event => ({ name: event.name, date: event.event_date, location: event.location, attendees: event.attendees, budget: event.budget, objective: event.objective });
const workspaceKey = eventId => `eventpilot-workspace-${eventId}`;
const normalizeRiskState = (state, risks) => Object.fromEntries(risks.flatMap((risk, index) => {
  const recorded = state?.[risk.title] || (index === 0 && state?.fallback ? 'Set fallback' : '') || (index === 1 && state?.monitoring ? 'Monitor' : '');
  return recorded ? [[risk.title, recorded]] : [];
}));

function createApprovedBlueprintPdf({ event, plan, forecast, reduced, riskState, isApproved, preview = false }) {
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
  const blueprintLabel = isApproved ? 'APPROVED EVENT BLUEPRINT' : 'DRAFT EVENT BLUEPRINT';
  const allocationColors = [[20, 111, 105], [224, 166, 66], [202, 102, 82], [74, 119, 168], [110, 150, 129], [132, 99, 158]];
  const cleanText = value => String(value || '').replace(/[–—]/g, '-');
  const title = cleanText(event.name);
  const footer = page => {
    pdf.setDrawColor(210, 214, 208);
    pdf.line(margin, 283, pageWidth - margin, 283);
    pdf.setTextColor(...muted);
    pdf.setFont('helvetica', 'normal');
    pdf.setFontSize(8);
    pdf.text(`EVENTPILOT  |  ${blueprintLabel}`, margin, 289);
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
  pdf.text(`${blueprintLabel}  |  EVENTPILOT`, margin, 31);
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
  pdf.text(isApproved ? 'READY FOR EXECUTION' : 'PREVIEW - AWAITING APPROVAL', pageWidth - margin, 267, { align: 'right' });

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

  // Page three measures variable AI text before placing the two operational columns.
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
  const cappedLines = (text, width, size, maximum) => {
    const lines = wrapped(text, width, size);
    if (lines.length <= maximum) return lines;
    return [...lines.slice(0, maximum - 1), `${lines[maximum - 1].slice(0, -3)}...`];
  };
  const venueNameLines = cappedLines(plan.venue.name, 82, 14, 4);
  const venueDetailLines = cappedLines(plan.venue.area, 82, 9.5, 7);
  const logisticsLines = cappedLines(plan.logistics.join('. ') + '.', 82, 9.5, 6);
  pdf.setFont('times', 'bold');
  pdf.setFontSize(14);
  pdf.text(venueNameLines, margin, 77);
  let venueY = 77 + venueNameLines.length * 6;
  pdf.setFont('helvetica', 'normal');
  pdf.setFontSize(9.5);
  pdf.setTextColor(...muted);
  pdf.text(venueDetailLines, margin, venueY + 5);
  venueY += venueDetailLines.length * 4.4 + 9;
  pdf.text(logisticsLines, margin, venueY);
  venueY += logisticsLines.length * 4.4;
  pdf.setTextColor(...teal);
  pdf.setFont('helvetica', 'bold');
  pdf.setFontSize(8);
  pdf.text('MARKETING READINESS', 112, 66);
  pdf.setTextColor(...ink);
  const marketingTitleLines = cappedLines(plan.marketing.title, 80, 12, 3);
  const marketingDescriptionLines = cappedLines(plan.marketing.description, 80, 9.5, 8);
  pdf.setFont('helvetica', 'bold');
  pdf.setFontSize(12);
  pdf.text(marketingTitleLines, 112, 77);
  pdf.setTextColor(...muted);
  pdf.setFont('helvetica', 'normal');
  pdf.setFontSize(9.5);
  pdf.text(marketingDescriptionLines, 112, 77 + marketingTitleLines.length * 5.2 + 5);
  const columnEnd = Math.max(venueY, 77 + marketingTitleLines.length * 5.2 + 5 + marketingDescriptionLines.length * 4.4);
  pdf.setDrawColor(214, 218, 210);
  pdf.line(margin, Math.min(columnEnd + 16, 267), pageWidth - margin, Math.min(columnEnd + 16, 267));
  footer(3);

  // A dedicated execution page prevents an unusually detailed venue from colliding with agenda rows.
  pdf.addPage();
  pdf.setFillColor(...paper);
  pdf.rect(0, 0, pageWidth, pageHeight, 'F');
  pdf.setTextColor(...teal);
  pdf.setFont('helvetica', 'bold');
  pdf.setFontSize(9);
  pdf.text('03  |  EVENT EXECUTION', margin, 25);
  pdf.setTextColor(...ink);
  pdf.setFont('times', 'bold');
  pdf.setFontSize(27);
  pdf.text('Agenda and risk decisions', margin, 42);
  pdf.setTextColor(...teal);
  pdf.setFont('helvetica', 'bold');
  pdf.setFontSize(8);
  pdf.text('EVENT-DAY AGENDA', margin, 61);
  let agendaY = 73;
  plan.agenda.slice(0, 5).forEach(row => {
    const activityLines = cappedLines(row[1], 79, 9.5, 2);
    const ownerLines = cappedLines(row[2], 63, 8.5, 2);
    const rowHeight = Math.max(activityLines.length * 4.8, ownerLines.length * 4.2, 8) + 7;
    pdf.setTextColor(...teal);
    pdf.setFont('helvetica', 'bold');
    pdf.setFontSize(9);
    pdf.text(cleanText(row[0]), margin, agendaY);
    pdf.setTextColor(...ink);
    pdf.setFontSize(9.5);
    pdf.text(activityLines, 47, agendaY);
    pdf.setTextColor(...muted);
    pdf.setFont('helvetica', 'normal');
    pdf.setFontSize(8.5);
    pdf.text(ownerLines, 129, agendaY);
    agendaY += rowHeight;
  });
  pdf.setDrawColor(214, 218, 210);
  pdf.line(margin, agendaY + 4, pageWidth - margin, agendaY + 4);
  pdf.setTextColor(...teal);
  pdf.setFont('helvetica', 'bold');
  pdf.setFontSize(8);
  const riskHeadingY = agendaY + 18;
  pdf.text('RISK DECISIONS', margin, riskHeadingY);
  let riskY = riskHeadingY + 13;
  plan.risks.slice(0, 5).forEach(risk => {
    const recorded = Boolean(riskState[risk.title]);
    const riskLines = cappedLines(risk.title, 135, 9, 2);
    pdf.setFillColor(...(recorded ? [219, 236, 225] : [252, 231, 212]));
    pdf.roundedRect(margin, riskY - 5, 24, 7, 1.5, 1.5, 'F');
    pdf.setTextColor(...(recorded ? teal : [168, 88, 31]));
    pdf.setFont('helvetica', 'bold');
    pdf.setFontSize(7.2);
    pdf.text(recorded ? 'RECORDED' : 'PENDING', margin + 12, riskY, { align: 'center' });
    pdf.setTextColor(...ink);
    pdf.setFontSize(9);
    pdf.text(riskLines, 47, riskY);
    riskY += Math.max(13, riskLines.length * 4.6 + 6);
  });
  pdf.setFillColor(...navy);
  pdf.roundedRect(margin, 263, 174, 13, 2, 2, 'F');
  pdf.setTextColor(242, 246, 245);
  pdf.setFont('helvetica', 'bold');
  pdf.setFontSize(9);
  pdf.text(isApproved ? 'APPROVED BY THE EVENT OWNER  |  READY FOR CONTROLLED EXECUTION' : 'PREVIEW ONLY  |  COMPLETE RISK DECISIONS BEFORE APPROVAL', margin + 7, 271.5);
  footer(4);
  if (preview) {
    window.open(pdf.output('bloburl'), '_blank', 'noopener,noreferrer');
    return;
  }
  pdf.save(`${title.replace(/[^a-z0-9]+/gi, '-').toLowerCase()}-approved-blueprint.pdf`);
}

function Overview({ event, plan, forecast, setPlanTab, setView, activities, approved, openRiskCount, riskState, onApprove, onPreview, onExport }) {
  const under = event.budget - forecast;
  const primaryRisk = plan.risks[0]; const primaryRiskRecorded = Boolean(riskState[primaryRisk.title]);
  return <section className="view active"><div className="title-row"><div><p className="eyebrow">EVENT #EP-2048</p><h1>{event.name}</h1><p className="event-meta">{formatDate(event.date)} <span /> {event.location} <span /> {event.attendees} attendees</p></div><div className="title-actions"><button className="button secondary" onClick={onPreview}>Preview PDF</button><button className="button secondary" disabled={!approved} title={approved ? 'Download the approved blueprint' : 'Approve the plan before exporting'} onClick={onExport}>{approved ? '↓ Export PDF' : 'Export after approval'}</button><button className="button primary" disabled={approved} onClick={onApprove}>{approved ? 'Approved ✓' : 'Approve plan'}</button></div></div>
    <div className="status-strip"><span className="status-icon">✓</span><div><strong>{approved ? 'Plan is approved for execution' : openRiskCount ? 'Plan is ready for review' : 'Plan is ready for approval'}</strong><span>{approved ? 'The final blueprint is ready to export.' : openRiskCount ? `${openRiskCount} decision${openRiskCount === 1 ? '' : 's'} need your attention before approval.` : 'All risk actions are complete. You can approve the plan.'}</span></div>{!approved && openRiskCount > 0 && <button onClick={() => setPlanTab('risks')}>Review decisions <span>→</span></button>}</div>
    <div className="metric-grid"><article className="metric-card"><p>Planning status</p><strong className="status-ready">{approved ? 'Approved' : openRiskCount ? 'Ready for review' : 'Ready to approve'}</strong><small>Last agent update 2 min ago</small></article><article className="metric-card"><p>Budget forecast</p><strong>{money(forecast)}</strong><small>{money(Math.abs(under))} {under >= 0 ? 'under target' : 'over target'}</small></article><article className="metric-card"><p>Plan confidence</p><strong>{plan.confidence}<span>%</span></strong><div className="confidence-bar"><i style={{ width: `${plan.confidence}%` }} /></div><small>Based on current event assumptions</small></article><article className="metric-card"><p>Open risks</p><strong className="risk-number">{openRiskCount}</strong><small>{openRiskCount ? 'Actions required' : 'All actions recorded'}</small></article></div>
    <div className="content-grid"><section className="panel plan-health"><div className="panel-heading"><div><p className="eyebrow">PLAN HEALTH</p><h2>Cross-team readiness</h2></div><button className="text-button" onClick={() => setView('plan')}>Open workspace →</button></div><div className="health-list"><div><span className="health-symbol good">✓</span><div><strong>Venue and capacity</strong><small>{plan.venue.name} supports {event.attendees} guests</small></div><em>{plan.venue.status}</em></div><div><span className="health-symbol good">✓</span><div><strong>Budget allocation</strong><small>Contingency reserve is included in the plan</small></div><em>On target</em></div><div><span className={`health-symbol ${primaryRiskRecorded ? 'good' : 'warn'}`}>{primaryRiskRecorded ? '✓' : '!'}</span><div><strong>{primaryRisk.title}</strong><small>{primaryRiskRecorded ? primaryRisk.resolved : primaryRisk.detail}</small></div><button className="small-action" onClick={() => setPlanTab('risks')}>{primaryRiskRecorded ? 'View' : 'Review'}</button></div><div><span className="health-symbol info">↗</span><div><strong>{plan.marketing.title}</strong><small>{plan.marketing.checks[0]}</small></div><button className="small-action" onClick={() => setPlanTab('marketing')}>View</button></div></div></section><section className="panel agent-panel"><div className="panel-heading"><div><p className="eyebrow">MULTI-AGENT TEAM</p><h2>Live planning activity</h2></div><button className="text-button" onClick={() => setView('activity')}>View all →</button></div><ol className="agent-feed">{activities.slice(0, 3).map((activity, index) => <li key={`${activity[0]}-${index}`}><span className={`feed-avatar ${['finance','manager','logistics'][index]}`}>{activity[3]}</span><div><strong>{activity[1]}</strong><p>{activity[2]}</p><small>{index === 0 ? '2 min ago' : index === 1 ? '8 min ago' : '14 min ago'}</small></div></li>)}</ol></section></div>
    <section className="panel agenda-panel"><div className="panel-heading"><div><p className="eyebrow">EVENT DAY</p><h2>Draft agenda</h2></div><button className="text-button" onClick={() => setPlanTab('schedule')}>Full schedule →</button></div><div className="agenda">{plan.overviewAgenda.map(row => <div key={row[0]}><time>{row[0]}</time><span /><p><strong>{row[1]}</strong><small>{row[2]}</small></p></div>)}</div></section>
  </section>;
}

function Activity({ activities }) { return <section className="view active"><div className="view-heading"><p className="eyebrow">PLANNING RUN</p><h1>Agent activity</h1><p>Human-readable activity from the planning workflow. This interface intentionally omits private chain-of-thought.</p></div><section className="panel activity-log">{activities.map((activity, index) => <article className="activity-entry" key={`${activity[0]}-${index}`}><time>{activity[0]}</time><span className="activity-marker">{activity[3]}</span><div><h3>{activity[1]}</h3><p>{activity[2]}</p></div></article>)}</section></section>; }

export default function App() {
  const [event, setEvent] = useState(initialEvent); const [eventId, setEventId] = useState(null); const [events, setEvents] = useState([]); const [apiPlan, setApiPlan] = useState(null); const [view, setView] = useState('home'); const [plannerKey, setPlannerKey] = useState(0); const [planTab, setPlanTab] = useState('logistics'); const [forecast, setForecast] = useState(464000); const [reduced, setReduced] = useState(false); const [budgetBeforeReduction, setBudgetBeforeReduction] = useState(null); const [activities, setActivities] = useState(buildEventPlan(initialEvent).activity); const [toast, setToast] = useState(''); const [saveStatus, setSaveStatus] = useState('Checking saved events'); const [approved, setApproved] = useState(false); const [riskState, setRiskState] = useState({}); const plan = apiPlan || buildEventPlan(event); const openRiskCount = plan.risks.filter(risk => !riskState[risk.title]).length;
  const notify = message => { setToast(message); window.setTimeout(() => setToast(''), 2600); };
  const addActivity = (agent, detail, marker = 'M') => setActivities(items => [[new Date().toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit', hour12: true }), agent, detail, marker], ...items]);
  const selectPlanTab = tab => { setPlanTab(tab); setView('plan'); window.scrollTo({ top: 0, behavior: 'smooth' }); };
  const applyApiPlan = (serverPlan, brief) => { const nextPlan = toUiPlan(serverPlan, buildEventPlan(brief)); setApiPlan(nextPlan); setForecast(serverPlan.budget_forecast); setActivities(nextPlan.activity); };
  const refreshEvents = () => listEvents().then(savedEvents => { setEvents(savedEvents); setSaveStatus('All changes saved'); }).catch(() => setSaveStatus('API unavailable - local draft only'));
  const saveWorkspaceState = (id, nextRiskState, nextApproved) => { if (!id) return; localStorage.setItem(workspaceKey(id), JSON.stringify({ riskState: nextRiskState, approved: nextApproved })); };
  const loadSavedEvent = async id => { try { const [savedEvent, savedPlan] = await Promise.all([getEvent(id), getPlan(id).catch(() => null)]); const brief = toUiEvent(savedEvent); const nextPlan = savedPlan ? toUiPlan(savedPlan, buildEventPlan(brief)) : buildEventPlan(brief); const savedWorkspace = JSON.parse(localStorage.getItem(workspaceKey(id)) || '{}'); setEvent(brief); setEventId(savedEvent.id); setApiPlan(savedPlan ? nextPlan : null); setForecast(savedPlan?.budget_forecast || Math.round(brief.budget * .928)); setActivities(nextPlan.activity); setRiskState(normalizeRiskState(savedWorkspace.riskState, nextPlan.risks)); setApproved(Boolean(savedWorkspace.approved)); setReduced(false); setBudgetBeforeReduction(null); setView('overview'); } catch { notify('Unable to load this saved event.'); } };
  useEffect(() => { listEvents().then(savedEvents => { setEvents(savedEvents); setSaveStatus('All changes saved'); setView('home'); }).catch(() => { setSaveStatus('API unavailable - local draft only'); setView('home'); }); }, []);
  const syncBudgetPlan = async brief => { try { let currentEventId = eventId; if (!currentEventId) { const savedEvent = await createApiEvent(brief); currentEventId = savedEvent.id; setEventId(currentEventId); } applyApiPlan(await reviseBudget(currentEventId, brief.budget), brief); refreshEvents(); } catch { setApiPlan(null); notify('API unavailable. Showing the local planning fallback.'); } };
  const reduceBudget = () => { if (reduced) return; const nextBudget = Math.round(event.budget * .8); const nextEvent = { ...event, budget: nextBudget }; setBudgetBeforeReduction(event.budget); setReduced(true); setEvent(nextEvent); setForecast(Math.round(nextBudget * .98)); setApiPlan(null); addActivity('Budget & Finance', 'Created a revised plan for a 20% reduced budget.', '₹'); syncBudgetPlan(nextEvent); notify('Budget revision complete. Version 04 is ready for review.'); };
  const restoreBudget = () => { if (!reduced || budgetBeforeReduction === null) return; const nextEvent = { ...event, budget: budgetBeforeReduction }; setEvent(nextEvent); setForecast(Math.round(budgetBeforeReduction * .928)); setReduced(false); setBudgetBeforeReduction(null); setApiPlan(null); addActivity('Budget & Finance', 'Restored the original budget scenario.', '₹'); syncBudgetPlan(nextEvent); notify('Original budget restored.'); };
  const saveEvent = async updated => { const fallbackPlan = buildEventPlan(updated); const previousId = eventId; setEvent(updated); setApiPlan(null); setForecast(Math.round(updated.budget * .928)); setActivities([['Now', 'Event Manager', `Generated a ${fallbackPlan.type} plan from the revised event brief.`, 'M'], ...fallbackPlan.activity]); setReduced(false); setBudgetBeforeReduction(null); setRiskState({}); setApproved(false); setView('overview'); try { const savedEvent = previousId ? await updateEvent(previousId, updated) : await createApiEvent(updated); const serverPlan = await generatePlan(savedEvent.id); setEventId(savedEvent.id); localStorage.removeItem(workspaceKey(savedEvent.id)); applyApiPlan(serverPlan, updated); refreshEvents(); notify('Plan generated by the EventPilot API.'); } catch { setSaveStatus('API unavailable - local draft only'); notify('API unavailable. Start the backend, then save again to add this event.'); } };
  const recordRiskAction = (risk, action) => { if (riskState[risk.title]) return; const nextRiskState = { ...riskState, [risk.title]: action }; setRiskState(nextRiskState); saveWorkspaceState(eventId, nextRiskState, approved); addActivity('Risk & Operations', `Recorded ${action.toLowerCase()} for: ${risk.title}.`, 'R'); notify(`${action} recorded.`); };
  const approve = () => { if (openRiskCount) { selectPlanTab('risks'); notify('Complete the remaining risk actions before approval.'); return; } setApproved(true); saveWorkspaceState(eventId, riskState, true); addActivity('Event Manager', 'Plan approved by the event owner and marked ready for execution.'); notify('Plan approved. Your final blueprint is ready to export.'); };
  const previewPlan = () => { createApprovedBlueprintPdf({ event, plan, forecast, reduced, riskState, isApproved: approved, preview: true }); notify('Blueprint preview opened in a new tab.'); };
  const exportPlan = () => { if (!approved) return notify('Approve the plan before exporting.'); createApprovedBlueprintPdf({ event, plan, forecast, reduced, riskState, isApproved: true }); notify('Designed blueprint PDF downloaded.'); };
  const openChatPlanner = () => { setEventId(null); setApiPlan(null); setRiskState({}); setApproved(false); setPlannerKey(current => current + 1); setView('home'); };
  return <div className="app-shell"><Sidebar view={view} setView={setView} setPlanTab={selectPlanTab} onNewEvent={openChatPlanner} events={events} activeEventId={eventId} onSelectEvent={loadSavedEvent} /><main className="main-content"><header className="topbar"><div className="crumb"><span>Events</span><b>/</b><strong>{view === 'home' ? 'Start a plan' : event.name}</strong></div><div className="topbar-actions"><span className="saved-state">{saveStatus}</span><button className="icon-button" aria-label="Notifications" onClick={() => notify(`${openRiskCount} risk action${openRiskCount === 1 ? '' : 's'} require attention.`)}>♧<span className="notification-dot" /></button><button className="avatar" aria-label="Account">BI</button></div></header>{view === 'home' && <><HomeWelcome onStartPlanning={openChatPlanner} /><ChatPlanner key={plannerKey} onGenerate={saveEvent} onCancel={() => setView(eventId ? 'overview' : 'home')} /></>}{view === 'overview' && <Overview event={event} plan={plan} forecast={forecast} setPlanTab={selectPlanTab} setView={setView} activities={activities} approved={approved} openRiskCount={openRiskCount} riskState={riskState} onApprove={approve} onPreview={previewPlan} onExport={exportPlan} />}{view === 'brief' && <EventBrief event={event} onSave={saveEvent} />}{view === 'plan' && <PlanWorkspace tab={planTab} setTab={setPlanTab} event={event} plan={plan} forecast={forecast} reduced={reduced} onReduce={reduceBudget} onRestore={restoreBudget} riskState={riskState} onRecordRisk={recordRiskAction} money={money} />}{view === 'activity' && <Activity activities={activities} />}</main><div className={`toast ${toast ? 'show' : ''}`} role="status">{toast}</div></div>;
}
