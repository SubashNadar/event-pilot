import { errorMessage } from './lib/http';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Download, Eye, Moon, Sparkles, Sun } from 'lucide-react';
import { jsPDF } from 'jspdf';
import { buildEventPlan, initialEvent } from './data/planData';
import { Sidebar } from './components/Sidebar';
import { PlanWorkspace } from './components/PlanWorkspace';
import { EventBrief } from './components/EventBrief';
import { ChatPlanner } from './components/ChatPlanner';
import LatestPlanWithAI from './components/LatestPlanWithAI';
import NoPlanYet from './components/NoPlanYet';
import { EventsBoard } from './components/EventsBoard';
import { RunActionsContext } from './run/runActions';
import { API_BASE_URL } from './lib/config';
import PlanHistory from './components/PlanHistory';
import { CHANGE_TOPICS, PlanChat } from './components/PlanChat';
import { useTheme } from './lib/theme';
import { BRIEF_SESSION_KEY, createEvent as createApiEvent, getEvent, getPlan, linkChatSession, listEvents, updateEvent } from './api/eventApi';
import { RunPanel, latestRun, usePlanRun } from './run';
import { toUiPlan } from './api/planAdapter';
import { useAgent } from './hooks/useAgentStream';

const money = value => `₹${new Intl.NumberFormat('en-IN').format(value)}`;
const formatDate = date => new Date(`${date}T00:00:00`).toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
const toUiEvent = event => ({ name: event.name, date: event.event_date, location: event.location, attendees: event.attendees, budget: event.budget, objective: event.objective });
const workspaceKey = eventId => `eventpilot-workspace-${eventId}`;
const timeAgo = iso => {
  const minutes = Math.max(0, Math.round((Date.now() - new Date(iso.endsWith('Z') || iso.includes('+') ? iso : `${iso}Z`).getTime()) / 60000));
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  return hours < 24 ? `${hours} hr ago` : `${Math.round(hours / 24)} days ago`;
};
// A brief edit on a planned event, said as a change request so only the affected agents re-run.
const describeBriefChange = (before, after) => {
  const parts = [];
  if (after.name !== before.name) parts.push(`change the event name to ${after.name}`);
  if (after.date !== before.date) parts.push(`move the event date to ${after.date}`);
  if (after.location !== before.location) parts.push(`change the location to ${after.location}`);
  if (Number(after.attendees) !== Number(before.attendees)) parts.push(`change the guest count to ${after.attendees} guests`);
  if (Number(after.budget) !== Number(before.budget)) parts.push(`set the total budget to ₹${after.budget}`);
  if ((after.objective || '') !== (before.objective || '')) parts.push(`change the objective to: ${after.objective}`);
  return parts.length ? `Please ${parts.join('; ')}.` : '';
};
const clock = ms => new Date(ms).toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit', hour12: true });
// Turn the live run's finished steps into Agent activity rows: [time, agent, detail, marker].
const runActivities = run => (run?.steps || [])
  .filter(step => step.endedAt && ['completed', 'skipped', 'failed'].includes(step.status))
  .sort((a, b) => b.endedAt - a.endedAt)
  .map(step => [clock(step.endedAt), step.agent, step.status === 'completed' ? (step.summary?.did?.[0] || step.title) : step.status === 'skipped' ? `Skipped “${step.title}”: ${step.error}` : `Needs your input: ${step.recovery?.summary || step.error}`, step.agent.charAt(0)]);
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

/** The owner's way into a change: pick what to change, then finish the sentence in the plan chat. */
function ChangeBar({ onChange }) {
  return <section className="change-bar" aria-label="Change the plan"><div><strong><Sparkles size={16} aria-hidden="true" /> Want something different?</strong><span>Pick what to change and say it in your own words. Only the agents it affects re-run, and you approve the result.</span></div><div className="change-chips">{CHANGE_TOPICS.map(topic => <button key={topic.key} type="button" onClick={() => onChange(topic.prompt)}><span aria-hidden="true">{topic.emoji}</span>{topic.label}</button>)}</div></section>;
}

function ChangeRecap({ changes, approved, openRiskCount, onDismiss, onApprove, onReviewRisks }) {
  return <section className="change-recap" role="status"><div><p className="eyebrow">JUST CHANGED</p><strong>{approved ? 'You approved the changed plan.' : 'Your change is in. Check it, then approve the plan again.'}</strong>{changes.length > 0 && <ul>{changes.slice(0, 6).map(line => <li key={line}>{line}</li>)}</ul>}</div><footer>{!approved && (openRiskCount ? <button type="button" className="button primary" onClick={onReviewRisks}>Review decisions</button> : <button type="button" className="button primary" onClick={onApprove}>Approve changed plan</button>)}<button type="button" className="text-button" onClick={onDismiss}>Dismiss</button></footer></section>;
}

function Overview({ event, eventId, plan, forecast, setPlanTab, setView, activities, approved, openRiskCount, riskState, onApprove, onPreview, onExport, hasRun, onChangePlan, lastChanges, onDismissChanges }) {
  const under = event.budget - forecast;
  const primaryRisk = plan.risks[0]; const primaryRiskRecorded = Boolean(riskState[primaryRisk.title]);
  return <section className="view active"><div className="title-row"><div><p className="eyebrow">{eventId ? `EVENT · ${eventId.slice(0, 8).toUpperCase()}` : 'LOCAL DRAFT · NOT SAVED'}</p><h1>{event.name}</h1><p className="event-meta">{formatDate(event.date)} <span /> {event.location} <span /> {event.attendees} attendees</p></div><div className="title-actions"><button className="button change-action" onClick={() => onChangePlan('')}><Sparkles size={15} aria-hidden="true" /> Change plan</button><button className="button secondary pdf-action" onClick={onPreview}><Eye size={15} /> Preview PDF</button><button className="button secondary pdf-action" disabled={!approved} title={approved ? 'Download the approved blueprint' : 'Approve the plan before exporting'} onClick={onExport}><Download size={15} /> {approved ? 'Export PDF' : 'Export after approval'}</button><button className="button primary" disabled={approved} onClick={onApprove}>{approved ? 'Approved ✓' : 'Approve plan'}</button></div></div>
    {lastChanges && <ChangeRecap changes={lastChanges} approved={approved} openRiskCount={openRiskCount} onDismiss={onDismissChanges} onApprove={onApprove} onReviewRisks={() => setPlanTab('risks')} />}
    <div className="status-strip"><span className="status-icon">✓</span><div><strong>{approved ? 'Plan is approved for execution' : openRiskCount ? 'Plan is ready for review' : 'Plan is ready for approval'}</strong><span>{approved ? 'The final blueprint is ready to export. You can still change the plan; changes come back to you for approval.' : openRiskCount ? `${openRiskCount} decision${openRiskCount === 1 ? '' : 's'} need your attention before approval.` : 'All risk actions are complete. You can approve the plan.'}</span></div>{!approved && openRiskCount > 0 && <button onClick={() => setPlanTab('risks')}>Review decisions <span>→</span></button>}</div>
    <ChangeBar onChange={onChangePlan} />
    <div className="metric-grid"><article className="metric-card"><p>Planning status</p><strong className="status-ready">{approved ? 'Approved' : openRiskCount ? 'Ready for review' : 'Ready to approve'}</strong><small>{plan.generatedAt ? `Last agent update ${timeAgo(plan.generatedAt)}` : 'Saved plan'}</small></article><article className="metric-card"><p>Budget forecast</p><strong>{money(forecast)}</strong><small>{money(Math.abs(under))} {under >= 0 ? 'under target' : 'over target'}</small></article><article className="metric-card"><p>Plan confidence</p><strong>{plan.confidence}<span>%</span></strong><div className="confidence-bar"><i style={{ width: `${plan.confidence}%` }} /></div><small>Based on current event assumptions</small></article><article className="metric-card"><p>Open risks</p><strong className="risk-number">{openRiskCount}</strong><small>{openRiskCount ? 'Actions required' : 'All actions recorded'}</small></article></div>
    <div className="content-grid"><section className="panel plan-health"><div className="panel-heading"><div><p className="eyebrow">PLAN HEALTH</p><h2>Cross-team readiness</h2></div><button className="text-button" onClick={() => setView('plan')}>Open workspace →</button></div><div className="health-list"><div><span className="health-symbol good">✓</span><div><strong>Venue and capacity</strong><small>{plan.venue.name} supports {event.attendees} guests</small></div><em>{plan.venue.status}</em></div><div><span className="health-symbol good">✓</span><div><strong>Budget allocation</strong><small>Contingency reserve is included in the plan</small></div><em>On target</em></div><div><span className={`health-symbol ${primaryRiskRecorded ? 'good' : 'warn'}`}>{primaryRiskRecorded ? '✓' : '!'}</span><div><strong>{primaryRisk.title}</strong><small>{primaryRiskRecorded ? primaryRisk.resolved : primaryRisk.detail}</small></div><button className="small-action" onClick={() => setPlanTab('risks')}>{primaryRiskRecorded ? 'View' : 'Review'}</button></div><div><span className="health-symbol info">↗</span><div><strong>{plan.marketing.title}</strong><small>{plan.marketing.checks[0]}</small></div><button className="small-action" onClick={() => setPlanTab('marketing')}>View</button></div></div></section><section className="panel agent-panel"><div className="panel-heading"><div><p className="eyebrow">MULTI-AGENT TEAM</p><h2>Live planning activity</h2></div><button className="text-button" onClick={() => setView(hasRun ? 'run' : 'activity')}>{hasRun ? 'How this plan was made →' : 'View all →'}</button></div><ol className="agent-feed">{activities.slice(0, 3).map((activity, index) => <li key={`${activity[0]}-${index}`}><span className={`feed-avatar ${['finance','manager','logistics'][index]}`}>{activity[3]}</span><div><strong>{activity[1]}</strong><p>{activity[2]}</p><small>{activity[0]}</small></div></li>)}</ol></section></div>
    <section className="panel agenda-panel"><div className="panel-heading"><div><p className="eyebrow">EVENT DAY</p><h2>Draft agenda</h2></div><button className="text-button" onClick={() => setPlanTab('schedule')}>Full schedule →</button></div><div className="agenda">{plan.overviewAgenda.map(row => <div key={row[0]}><time>{row[0]}</time><span /><p><strong>{row[1]}</strong><small>{row[2]}</small></p></div>)}</div></section>
  </section>;
}

function Activity({ activities }) { return <section className="view active"><div className="view-heading"><p className="eyebrow">PLANNING RUN</p><h1>Agent activity</h1><p>Human-readable activity from the planning workflow. This interface intentionally omits private chain-of-thought.</p></div><section className="panel activity-log">{activities.map((activity, index) => <article className="activity-entry" key={`${activity[0]}-${index}`}><time>{activity[0]}</time><span className="activity-marker">{activity[3]}</span><div><h3>{activity[1]}</h3><p>{activity[2]}</p></div></article>)}</section></section>; }

function PlanHub({ tab, setTab, event, eventId, plan, forecast, reduced, onReduce, onRestore, riskState, onRecordRisk, setView, approved, openRiskCount, onApprove, onPreview, onExport, activities, hasRun, onSaveBrief, onReplan, awaitingDecision, onReviewInChat }) {
  const sections = [['overview', 'Overview'], ['logistics', 'Logistics'], ['budget', 'Budget'], ['schedule', 'Schedule'], ['marketing', 'Marketing'], ['risks', 'Risks']];
  const editBrief = () => { setTab('overview'); setTimeout(() => document.getElementById('brief-card')?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 80); };
  return <section className="plan-hub">
    <header className="ws-header">
      <div>
        <p className="board-kicker">Plan workspace</p>
        <h1 className="ws-title">{event.name}</h1>
        <p className="board-meta">{formatDate(event.date)} · {event.location} · {event.attendees} guests</p>
      </div>
      <div className="ws-actions">
        <button type="button" className="board-btn" onClick={editBrief}>Edit brief</button>
        <button type="button" className="board-btn primary" onClick={onReplan} disabled={!eventId}>Re-plan</button>
        <button type="button" className="board-btn" onClick={onPreview}>Preview PDF</button>
        <button type="button" className="board-btn" disabled={!approved} onClick={onExport}>Export</button>
        <button type="button" className="board-btn primary" onClick={onApprove} disabled={approved}>{approved ? 'Approved' : 'Approve plan'}</button>
      </div>
    </header>
    {awaitingDecision && <div className="decision-banner" role="status"><span><strong>Your decision is needed.</strong> Approve this plan, or send changes back to the agents.</span><button type="button" className="board-btn primary" onClick={onReviewInChat}>Review in chat</button></div>}
    <nav className="ws-tabs" role="tablist" aria-label="Plan sections">
      {sections.map(([key, label]) => <button key={key} type="button" role="tab" aria-selected={tab === key} className={tab === key ? 'active' : ''} onClick={() => setTab(key)}>{label}</button>)}
    </nav>
    {tab === 'overview'
      ? <>
          <Overview event={event} eventId={eventId} plan={plan} forecast={forecast} setPlanTab={setTab} setView={setView} activities={activities} approved={approved} openRiskCount={openRiskCount} riskState={riskState} onApprove={onApprove} onPreview={onPreview} onExport={onExport} hasRun={hasRun} />
          <div id="brief-card" className="ws-card">
            <p className="board-kicker">Event brief</p>
            <p className="board-meta">Change any detail, then save. Saving re-plans the event and the agents' steps appear in the chat.</p>
            <EventBrief event={event} onSave={onSaveBrief} />
          </div>
        </>
      : <PlanWorkspace tab={tab} setTab={setTab} event={event} plan={plan} forecast={forecast} reduced={reduced} onReduce={onReduce} onRestore={onRestore} riskState={riskState} onRecordRisk={onRecordRisk} money={money} />}
  </section>;
}

export default function App() {
  const [navOpen, setNavOpen] = useState(false);
  const [event, setEvent] = useState(initialEvent); const [eventId, setEventId] = useState(null); const [events, setEvents] = useState([]); const [apiPlan, setApiPlan] = useState(null); const [view, setView] = useState('events');
  const [latestRunStatus, setLatestRunStatus] = useState(null);
  useEffect(() => {
    if (!eventId) { setLatestRunStatus(null); return; }
    fetch(`${API_BASE_URL}/events/${eventId}/runs/latest`).then(r => (r.ok ? r.json() : null)).then(run => setLatestRunStatus(run ? run.status : null)).catch(() => setLatestRunStatus(null));
  }, [eventId, view]); const [plannerKey, setPlannerKey] = useState(0); const [planTab, setPlanTab] = useState('overview'); const [forecast, setForecast] = useState(464000); const [reduced, setReduced] = useState(false); const [budgetBeforeReduction, setBudgetBeforeReduction] = useState(null); const [activities, setActivities] = useState(buildEventPlan(initialEvent).activity); const [toast, setToast] = useState(''); const [saveStatus, setSaveStatus] = useState('Checking saved events'); const [approved, setApproved] = useState(false); const [riskState, setRiskState] = useState({}); const [userActivities, setUserActivities] = useState([]); const planRun = usePlanRun(); const liveRunId = useRef(null); const appliedRunId = useRef(null); const plan = apiPlan || buildEventPlan(event); const openRiskCount = plan.risks.filter(risk => !riskState[risk.title]).length;
  const { isStreaming, stop: stopChat, newSession: abandonChat, state: chatState, replan: replanInChat, openSession: openChatSession } = useAgent();
  const [pendingNavigation, setPendingNavigation] = useState(null); const [historyEventId, setHistoryEventId] = useState(null);
  const [theme, toggleTheme] = useTheme();
  // The change panel: open state, the sentence it opens with, and the last change's recap.
  const [changeOpen, setChangeOpen] = useState(false); const [changeSeed, setChangeSeed] = useState(null); const [lastChanges, setLastChanges] = useState(null);
  const openChange = (text = '', send = false) => setChangeSeed({ text, send, nonce: Date.now() });
  const legacyPlanning = Boolean(planRun.run && !['completed', 'stopped', 'error'].includes(planRun.run.status));
  // Brief collection pauses while waiting for a reply, but it is still an unfinished planning session.
  const chatBriefInProgress = chatState.sessionId === null && chatState.messages.length > 0;
  // Chat state can remain mounted after opening a saved overview. It should guard
  // navigation only while the user is actually in the Plan with AI experience.
  const chatPlanningActive = view === 'home' && !historyEventId && (isStreaming || chatBriefInProgress);
  const planningActive = legacyPlanning || chatPlanningActive;
  const notify = message => { setToast(message); window.setTimeout(() => setToast(''), 2600); };
  const addActivity = (agent, detail, marker = 'M') => setUserActivities(items => [[clock(Date.now()), agent, detail, marker], ...items]);
  const liveActivities = useMemo(() => runActivities(planRun.run), [planRun.run]);
  const displayActivities = [...userActivities, ...(liveActivities.length ? liveActivities : activities)];
  const requestNavigation = (nextView, beforeNavigate) => { if (nextView === 'overview' && historyEventId) { void loadSavedEvent(historyEventId); return; } if (nextView === view) { beforeNavigate?.(); return; } /* The run keeps going and its state is saved, so moving between screens never needs a prompt. */ beforeNavigate?.(); setView(nextView); };
  const navigateFromSidebar = nextView => { if (nextView === 'home' && historyEventId) { setPendingNavigation(null); setView('home'); return; } requestNavigation(nextView); };
  const openPlanWithAiFromSidebar = () => { if (legacyPlanning) { requestNavigation('home'); return; } setPendingNavigation(null); setView('home'); };
  const selectPlanTab = tab => requestNavigation('plan', () => { setPlanTab(tab); window.scrollTo({ top: 0, behavior: 'smooth' }); });
  const requestNewPlan = () => openChatPlanner();
  const requestEventSelection = id => { if (planningActive) { setPendingNavigation({ nextView: 'overview', beforeNavigate: () => loadSavedEvent(id) }); return; } loadSavedEvent(id); };
  const applyApiPlan = (serverPlan, brief) => { const nextPlan = toUiPlan(serverPlan, buildEventPlan(brief)); setApiPlan(nextPlan); setForecast(serverPlan.budget_forecast); setActivities(nextPlan.activity); };
  const refreshEvents = () => listEvents().then(savedEvents => { setEvents(savedEvents); setSaveStatus('All changes saved'); }).catch(error => setSaveStatus(errorMessage(error)));
  const saveWorkspaceState = (id, nextRiskState, nextApproved) => { if (!id) return; localStorage.setItem(workspaceKey(id), JSON.stringify({ riskState: nextRiskState, approved: nextApproved })); };
  const loadSavedEvent = async (id, openOverview = true) => { try { const [savedEvent, savedPlan] = await Promise.all([getEvent(id), getPlan(id).catch(error => { if (error.status === 404) return null; throw error; })]); const brief = toUiEvent(savedEvent); const nextPlan = savedPlan ? toUiPlan(savedPlan, buildEventPlan(brief)) : buildEventPlan(brief); const savedWorkspace = JSON.parse(localStorage.getItem(workspaceKey(id)) || '{}'); setEvent(brief); setEventId(savedEvent.id); setApiPlan(savedPlan ? nextPlan : null); setForecast(savedPlan?.budget_forecast || Math.round(brief.budget * .928)); setActivities(nextPlan.activity); setRiskState(normalizeRiskState(savedWorkspace.riskState, nextPlan.risks)); setApproved(Boolean(savedWorkspace.approved)); setReduced(false); setBudgetBeforeReduction(null); setUserActivities([]); setLastChanges(null); setChangeOpen(false); appliedRunId.current = null; liveRunId.current = null; latestRun(id).then(run => { if (!run) { planRun.reset(); return; } appliedRunId.current = run.id; planRun.attach(run.id); if (run.status === 'completed' && run.operation === 'plan-generation') setApproved(true); }).catch(() => planRun.reset()); if (openOverview) setView('overview'); } catch (error) { notify(errorMessage(error)); } };
  useEffect(() => { listEvents().then(savedEvents => { setEvents(savedEvents); setSaveStatus('All changes saved'); setView('events'); }).catch(error => { setSaveStatus(errorMessage(error)); setView('events'); }); }, []);
  const startPlanningRun = async (id, options = {}) => { const runId = await planRun.start(id, options); liveRunId.current = runId; setView('run'); return runId; };
  // When a run delivers its plan, load it into the workspace (also replays for saved events).
  useEffect(() => { const run = planRun.run; if (!run?.plan || appliedRunId.current === `${run.runId}:applied` || (eventId && run.eventId && run.eventId !== eventId)) return; appliedRunId.current = `${run.runId}:applied`; applyApiPlan(run.plan, event); if (run.operation === 'plan-generation') setApproved(true); if (liveRunId.current === run.runId) { refreshEvents(); notify(run.operation === 'plan-edit' ? 'Plan updated.' : 'Your plan is ready. Review it when you like.'); } }, [planRun.run?.plan]);
  // A plan edit from the plan chat: follow its run here without leaving the current view.
  const followEditRun = runId => { liveRunId.current = runId; planRun.attach(runId); };
  // A plan-chat edit saves both a revised brief and a revised plan. Reload both
  // from the API so the workspace cannot remain on the pre-edit snapshot.
  const reloadEditedPlan = (changes = []) => {
    if (!eventId) return;
    setLastChanges(changes);
    Promise.all([getEvent(eventId), getPlan(eventId)])
      .then(([savedEvent, savedPlan]) => {
        const brief = toUiEvent(savedEvent);
        const nextPlan = toUiPlan(savedPlan, buildEventPlan(brief));
        setEvent(brief);
        setApiPlan(nextPlan);
        setForecast(savedPlan.budget_forecast);
        setActivities(nextPlan.activity);
        setRiskState(current => normalizeRiskState(current, nextPlan.risks));
        setApproved(false);
        // Persist it too, or a reload would show the edited plan as still approved.
        setRiskState(current => { saveWorkspaceState(eventId, current, false); return current; });
        notify('Your plan changes are now visible. Review them before approving again.');
      })
      .catch(() => notify('The update finished, but the revised plan could not be reloaded. Refresh and try again.'));
    refreshEvents();
  };
  const syncBudgetPlan = async brief => { try { let currentEventId = eventId; if (!currentEventId) { const savedEvent = await createApiEvent(brief); currentEventId = savedEvent.id; setEventId(currentEventId); } await startPlanningRun(currentEventId, { operation: 'budget-revision', budget: brief.budget }); } catch (error) { notify(errorMessage(error)); } };
  const reduceBudget = () => { if (reduced) return; const nextBudget = Math.round(event.budget * .8); const nextEvent = { ...event, budget: nextBudget }; setBudgetBeforeReduction(event.budget); setReduced(true); setEvent(nextEvent); setForecast(Math.round(nextBudget * .98)); setApiPlan(null); addActivity('Budget & Finance', 'Started a revision for a 20% reduced budget.', '₹'); syncBudgetPlan(nextEvent); notify('Revising the plan for the reduced budget…'); };
  const restoreBudget = () => { if (!reduced || budgetBeforeReduction === null) return; const nextEvent = { ...event, budget: budgetBeforeReduction }; setEvent(nextEvent); setForecast(Math.round(budgetBeforeReduction * .928)); setReduced(false); setBudgetBeforeReduction(null); setApiPlan(null); addActivity('Budget & Finance', 'Started a revision back to the original budget.', '₹'); syncBudgetPlan(nextEvent); notify('Restoring the original budget…'); };
  const saveEvent = async (updated, chatSessionId) => { const fallbackPlan = buildEventPlan(updated); const previousId = eventId; setEvent(updated); setApiPlan(null); setForecast(Math.round(updated.budget * .928)); setActivities([['Now', 'Event Manager', `Generated a ${fallbackPlan.type} plan from the revised event brief.`, 'M'], ...fallbackPlan.activity]); setReduced(false); setBudgetBeforeReduction(null); setRiskState({}); setApproved(false); setUserActivities([]); try { const savedEvent = previousId ? await updateEvent(previousId, updated) : await createApiEvent(updated); setEventId(savedEvent.id); localStorage.removeItem(workspaceKey(savedEvent.id)); if (chatSessionId) linkChatSession(chatSessionId, savedEvent.id).catch(() => notify('The event was saved, but its conversation could not be linked.')); refreshEvents(); await startPlanningRun(savedEvent.id); } catch (error) { setSaveStatus(errorMessage(error)); notify(errorMessage(error)); throw error; } };
  const saveBriefAsChange = async updated => { const message = describeBriefChange(event, updated); if (!message) { notify('Nothing in the brief changed.'); return; } openChange(message, true); setView('overview'); };
  const recordRiskAction = (risk, action) => { if (riskState[risk.title]) return; const nextRiskState = { ...riskState, [risk.title]: action }; setRiskState(nextRiskState); saveWorkspaceState(eventId, nextRiskState, approved); addActivity('Risk & Operations', `Recorded ${action.toLowerCase()} for: ${risk.title}.`, 'R'); notify(`${action} recorded.`); };
  const approve = () => { if (openRiskCount) { selectPlanTab('risks'); notify('Complete the remaining risk actions before approval.'); return; } setApproved(true); saveWorkspaceState(eventId, riskState, true); addActivity('Event Manager', 'Plan approved by the event owner and marked ready for execution.'); notify('Plan approved. Your final blueprint is ready to export.'); };
  const previewPlan = () => { createApprovedBlueprintPdf({ event, plan, forecast, reduced, riskState, isApproved: approved, preview: true }); notify('Blueprint preview opened in a new tab.'); };
  const exportPlan = () => { if (!approved) return notify('Approve the plan before exporting.'); createApprovedBlueprintPdf({ event, plan, forecast, reduced, riskState, isApproved: true }); notify('Designed blueprint PDF downloaded.'); };
  const openChatPlanner = () => { try { localStorage.removeItem(BRIEF_SESSION_KEY); } catch { /* storage unavailable */ }  setHistoryEventId(null); setEventId(null); setApiPlan(null); setRiskState({}); setApproved(false); setUserActivities([]); planRun.reset(); setPlannerKey(current => current + 1); setView('home'); };
  const leavePlanning = async () => { const destination = pendingNavigation; setPendingNavigation(null); if (chatBriefInProgress) abandonChat(); else stopChat(); destination?.beforeNavigate?.(); if (destination) setView(destination.nextView); };
  const greetingText = (() => { const h = new Date().getHours(); return h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening'; })();
  const runActions = {
    onEditBrief: () => { planRun.cancel().catch(() => undefined); setPendingNavigation(null); setView('brief'); },
    onStartOver: () => { planRun.cancel().catch(() => undefined); setPendingNavigation(null); setView('home'); },
  };
  const hasPlanForBoard = Boolean(apiPlan);
  const budgetUsed = event.budget ? Math.min(100, Math.round((forecast / event.budget) * 100)) : 0;
  const boardGlance = (
    <div className="board-panel">
      <p className="board-kicker">{hasPlanForBoard ? 'Plan at a glance' : 'Your brief'}</p>
      <h2 className="board-title">{hasPlanForBoard ? event.name : 'New plan'}</h2>
      {hasPlanForBoard && <p className="board-meta">{event.location} · {formatDate(event.date)}</p>}
      {hasPlanForBoard ? (<>
        <div className="board-kv"><span>Approved budget</span><span>{money(event.budget)}</span><span>Forecast</span><span>{money(forecast)}</span><span>Confidence</span><span>{plan.confidence}%</span><span>Open risks</span><span>{openRiskCount}</span></div>
        <div className="board-bar" role="img" aria-label={`Forecast uses ${budgetUsed} percent of the budget`}><i style={{ width: `${budgetUsed}%` }} /></div>
        <ul className="board-list" aria-label="Recent agent activity">
          {displayActivities.slice(0, 4).map((activity, index) => Array.isArray(activity) ? <li key={index}><strong>{activity[1]}</strong><span>{activity[2]}</span></li> : null)}
        </ul>
      </>) : (
        <p className="board-meta">Answer the questions in the chat. Your brief fills in here, and the plan's budget and risks appear once it is generated.</p>
      )}
    </div>
  );
  return <div className={`app-shell ${view === 'home' || view === 'events' ? '' : 'has-glance'}`}><Sidebar history={<PlanHistory onHistoryOpen={id => { setHistoryEventId(id); void loadSavedEvent(id); }} />} view={view} hasEvent={Boolean(eventId)} online={saveStatus === 'All changes saved'} setView={navigateFromSidebar} setPlanTab={selectPlanTab} onNewEvent={requestNewPlan} onOpenPlanWithAi={openPlanWithAiFromSidebar} events={events} activeEventId={eventId} onSelectEvent={requestEventSelection} onChangePlan={apiPlan && eventId ? () => { if (!['overview', 'plan', 'brief'].includes(view)) setView('overview'); openChange(''); } : undefined} run={planRun.run} counts={{ logistics: plan.logistics.length, budget: plan.budgetLabels.length, schedule: plan.agenda.length, marketing: plan.marketing.steps.length, risks: openRiskCount }} /><main className={`main-content ${view === 'home' ? 'planner-main-content' : ''}`}><header className={`topbar ${view === 'events' || view === 'home' ? 'is-home' : ''}`}>{(view === 'events' || view === 'home') && <div className="greet"><strong>{greetingText}, Subash</strong><span>Your planning board. Plans and decisions in one place.</span></div>}<div className="crumb"><span>Events</span><b>/</b><strong>{view === 'home' ? 'Plan with AI' : view === 'run' ? `${event.name} · planning run` : event.name}</strong></div><div className="topbar-actions"><span className="saved-state">{saveStatus}</span><button type="button" className="theme-toggle" onClick={toggleTheme} aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'} title={theme === 'dark' ? 'Light mode' : 'Dark mode'}>{theme === 'dark' ? <Sun size={16} aria-hidden="true" /> : <Moon size={16} aria-hidden="true" />}</button></div></header>{view === 'events' && <EventsBoard events={events} onOpen={id => { void loadSavedEvent(id); }} />}{view === 'home' && <LatestPlanWithAI onPlanReady={id => { setHistoryEventId(null); void loadSavedEvent(id); }} onHistoryOpen={setHistoryEventId} selectedHistoryEventId={historyEventId} />}{view === 'run' && <RunActionsContext.Provider value={runActions}><RunPanel planRun={planRun} eventName={event.name} onReviewPlan={() => requestNavigation('overview')} onRestart={eventId ? () => startPlanningRun(eventId).catch(error => notify(errorMessage(error))) : undefined} /></RunActionsContext.Provider>}{view === 'overview' && !apiPlan && <NoPlanYet eventName={event.name} runStatus={planRun.run?.status} onGenerate={() => eventId && startPlanningRun(eventId).catch(error => notify(errorMessage(error)))} onReviewRun={() => setView('run')} />}{view === 'overview' && apiPlan && <Overview event={event} eventId={eventId} plan={plan} forecast={forecast} setPlanTab={selectPlanTab} setView={requestNavigation} activities={displayActivities} approved={approved} openRiskCount={openRiskCount} riskState={riskState} onApprove={approve} onPreview={previewPlan} onExport={exportPlan} hasRun={Boolean(planRun.run)} onChangePlan={openChange} lastChanges={lastChanges} onDismissChanges={() => setLastChanges(null)} />}{view === 'brief' && <EventBrief event={event} eventId={eventId} hasPlan={Boolean(apiPlan && eventId)} onSave={apiPlan && eventId ? saveBriefAsChange : saveEvent} />}{view === 'plan' && !apiPlan && <NoPlanYet eventName={event.name} runStatus={planRun.run?.status} onGenerate={() => eventId && startPlanningRun(eventId).catch(error => notify(errorMessage(error)))} onReviewRun={() => setView('run')} />}{view === 'plan' && apiPlan && <PlanWorkspace tab={planTab} setTab={setPlanTab} event={event} plan={plan} forecast={forecast} reduced={reduced} onReduce={reduceBudget} onRestore={restoreBudget} riskState={riskState} onRecordRisk={recordRiskAction} money={money} onChange={openChange} />}{view === 'activity' && <Activity activities={displayActivities} />}</main>{['overview', 'plan', 'brief'].includes(view) && eventId && apiPlan && <PlanChat eventId={eventId} run={planRun.run} open={changeOpen} onOpenChange={setChangeOpen} seed={changeSeed} onSeedUsed={() => setChangeSeed(null)} onEditRun={followEditRun} onOpenRun={() => requestNavigation('run')} onPlanUpdated={reloadEditedPlan} />}<div className={`toast ${toast ? 'show' : ''}`} role="status">{toast}</div>{pendingNavigation && <div className="planning-leave-modal" role="dialog" aria-modal="true" aria-labelledby="leave-title"><div><p className="eyebrow">PLANNING IN PROGRESS</p><h2 id="leave-title">Leave this planning run?</h2><p>The agents keep working in the background, and any decision waiting for you stays open. Come back from this event to see the run and continue it.</p><footer><button className="button secondary" onClick={() => setPendingNavigation(null)}>Keep planning</button><button className="button primary" onClick={() => void leavePlanning()}>Leave the run</button></footer></div></div>}</div>;
}
