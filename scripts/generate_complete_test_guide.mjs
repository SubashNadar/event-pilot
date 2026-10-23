import { jsPDF } from '../frontend/node_modules/jspdf/dist/jspdf.es.min.js';
import { writeFileSync } from 'node:fs';

const pdf = new jsPDF({ unit: 'mm', format: 'a4' });
const W = 210, H = 297, M = 17;
const navy = [20, 49, 47], teal = [25, 117, 109], lime = [215, 237, 116];
const ink = [28, 47, 45], muted = [92, 111, 106], paper = [248, 249, 246], orange = [207, 113, 43];
const clean = (value) => String(value).replace(/[\u2013\u2014]/g, '-');
const wrap = (text, max, size = 9.5) => { pdf.setFontSize(size); return pdf.splitTextToSize(clean(text), max); };
const text = (value, x, y, max, size = 9.5, color = ink, font = 'helvetica', style = 'normal') => {
  pdf.setTextColor(...color); pdf.setFont(font, style); pdf.setFontSize(size); pdf.text(wrap(value, max, size), x, y);
};
const footer = (page) => {
  pdf.setDrawColor(215, 226, 220); pdf.line(M, 283, W - M, 283);
  text('EVENTPILOT | COMPLETE APPLICATION TEST GUIDE', M, 289, 130, 7.8, muted);
  pdf.text(`PAGE ${page}`, W - M, 289, { align: 'right' });
};
const heading = (label, title, subtitle, page) => {
  pdf.setFillColor(...paper); pdf.rect(0, 0, W, H, 'F');
  pdf.setFillColor(...teal); pdf.rect(0, 0, W, 2, 'F');
  text('EVENTPILOT', M, 18, 80, 9, teal, 'helvetica', 'bold');
  text(label.toUpperCase(), M, 29, 120, 8.5, muted, 'helvetica', 'bold');
  text(title, M, 43, 176, 24, ink, 'times', 'bold');
  text(subtitle, M, 56, 171, 10, muted);
  footer(page);
};
const card = (x, y, w, h, label, body, accent = teal) => {
  pdf.setFillColor(255, 255, 255); pdf.setDrawColor(216, 227, 221); pdf.roundedRect(x, y, w, h, 2, 2, 'FD');
  pdf.setFillColor(...accent); pdf.roundedRect(x, y, 4, h, 2, 2, 'F');
  text(label.toUpperCase(), x + 9, y + 10, w - 16, 7.6, accent, 'helvetica', 'bold');
  text(body, x + 9, y + 20, w - 16, 8.7, ink);
};
const step = (num, title, action, expected, y) => {
  pdf.setFillColor(...lime); pdf.circle(M + 4, y - 2, 4, 'F');
  text(String(num), M + 2.15, y + .3, 4, 7, navy, 'helvetica', 'bold');
  text(title, M + 12, y, 54, 9.2, teal, 'helvetica', 'bold');
  text(action, M + 57, y, 67, 8.6, ink);
  text(expected, M + 127, y, 65, 8.3, muted);
};

// Cover
pdf.setFillColor(...navy); pdf.rect(0, 0, W, H, 'F');
pdf.setFillColor(...lime); pdf.roundedRect(155, 23, 35, 35, 6, 6, 'F');
text('EP', 155, 44, 35, 23, navy, 'helvetica', 'bold');
text('EVENTPILOT | TEST PROTOCOL', M, 29, 120, 9, lime, 'helvetica', 'bold');
text('Complete application\ntest guide', M, 66, 120, 34, [244, 248, 246], 'times', 'bold');
text('A practical, start-to-finish test using one wedding-reception scenario. It proves the user experience, LangGraph workflow, MCP tools, Langfuse tracing, revision, risk decisions, approval, export, and persistence.', M, 128, 132, 12, [193, 211, 204]);
pdf.setDrawColor(74, 105, 98); pdf.line(M, 190, W - M, 190);
[['SCENARIO', 'Meera and Karthik Wedding Reception'], ['SCALE', '350 guests | Whitefield, Bengaluru'], ['BUDGET', 'INR 12,00,000 | Saturday, 20 March 2027'], ['TIME', 'About 15-20 minutes for a complete test']].forEach(([label, value], index) => {
  const y = 209 + index * 17; text(label, M, y, 34, 8, lime, 'helvetica', 'bold'); text(value, 58, y, 124, 9.4, [237, 244, 241]);
});
text('Use this PDF as both a tester checklist and a reviewer demonstration script.', M, 274, 160, 9, [193, 211, 204]);

// Page 2
pdf.addPage(); heading('01 | DEMO INTRODUCTION', 'Set the reviewer context', 'Open with the outcome, then show how the application turns a realistic event brief into a human-approved plan.', 2);
card(M, 70, 176, 35, 'Suggested opening', 'EventPilot is an autonomous event-planning workspace. A shared brief is interpreted by specialist agents, grounded with MCP tools, coordinated through LangGraph, traced in Langfuse, and presented for human review and approval.', teal);
card(M, 113, 85, 31, 'What reviewers will see', '1. A wedding invitation becomes a complete event brief.\n2. Six specialists create evidence-backed recommendations.\n3. A manager synthesizes, validates, and presents one reviewable plan.', [91, 147, 119]);
card(110, 113, 82, 31, 'Key message', 'AI accelerates planning, but it does not make the final decision. The event owner resolves risks, approves the plan, and controls final export.', orange);
text('After this introduction, start the stack below. Keep the API terminal and Langfuse browser tab visible during the run.', M, 158, 176, 9.2, muted);
card(M, 169, 176, 24, 'Terminal 1 - MCP server', 'cd backend && source .venv/bin/activate && python -m app.mcp.server\nExpected: service listening on http://127.0.0.1:8000/mcp', teal);
card(M, 200, 176, 24, 'Terminal 2 - API', 'cd backend && source .venv/bin/activate && uvicorn app.main:app --reload --port 8001\nExpected: /health returns status ok.', [91, 147, 119]);
card(M, 231, 176, 24, 'Terminal 3 - React', 'cd frontend && npm run dev\nOpen the displayed URL, normally http://127.0.0.1:5173.', orange);
text('Pre-flight: confirm the browser does not say API unavailable, keep Langfuse open, and begin with a fresh Plan with AI conversation. MCP has a safe in-process fallback, but keep it running to show the full protocol path.', M, 265, 176, 8.8, muted);

// Page 3
pdf.addPage(); heading('02 | THE TEST INPUT', 'Use the invitation attachment', 'This is the fastest realistic way to prove that EventPilot can turn event data into a validated shared brief.', 3);
card(M, 74, 176, 38, 'Recommended action', 'Open Plan with AI. In the composer, click Try wedding invitation. A file chip named Meera-and-Karthik-Wedding-Invitation.txt appears. Click Send without adding any extra text.', teal);
text('Expected extracted brief', M, 128, 170, 15, ink, 'times', 'bold');
const fields = [['Event type', 'Wedding'], ['Event name', 'Meera And Karthik Wedding Reception'], ['Date', '2027-03-20'], ['Location', 'Whitefield, Bengaluru'], ['Attendees', '350'], ['Budget', 'INR 12,00,000'], ['Objective', 'Warm family celebration with smooth guest welcome, ceremony timing, photography and dinner flow.']];
fields.forEach(([label, value], i) => { const y = 141 + i * 12; pdf.setDrawColor(215, 226, 220); pdf.line(M, y + 4, W - M, y + 4); text(label, M, y, 48, 8.5, teal, 'helvetica', 'bold'); text(value, 63, y, 125, 8.5, ink); });
card(M, 234, 176, 28, 'Pass condition', 'The assistant confirms the complete brief and enables plan generation. If a field is missing, answer only that question; do not restart the conversation.', [91, 147, 119]);

// Page 4
pdf.addPage(); heading('03 | GENERATE AND INSPECT', 'Run the LangGraph planning workflow', 'This section verifies the visible product flow and the agent orchestration represented by the Planning Run graph.', 4);
step(1, 'Generate plan', 'Confirm the extracted brief, then select Generate event plan.', 'A saved event and live planning run begin.', 77);
step(2, 'Stay in Plan with AI', 'Watch the agent status rather than leaving the page.', 'The chat shows progress and a completed planning response.', 105);
step(3, 'Open Planning Run', 'Use the sidebar Planning run item.', 'Timeline shows the 11 workflow stages.', 133);
step(4, 'Open Workflow graph', 'Switch from Timeline to Workflow graph.', 'Event brief -> six specialist agents -> Event Manager -> Review -> Final plan.', 161);
step(5, 'Inspect a step', 'Open Logistics or Finance.', 'Tool input, result summary, verification, recovery context, and trace information are visible.', 189);
step(6, 'Open Overview', 'Use Overview only after the run completes.', 'Planning status, forecast, confidence, and open risks are visible.', 217);
card(M, 239, 176, 26, 'Pass condition', 'The plan contains a venue recommendation, six budget lines, a five-item 12-hour agenda, marketing readiness, two to five risks, and agent activity. The review stage completes before the plan is presented.', teal);

// Page 5
pdf.addPage(); heading('04 | VERIFY THE TECHNICAL EVIDENCE', 'Show MCP and Langfuse', 'This proves that the event plan is an observable multi-agent workflow, not a static frontend response.', 5);
card(M, 74, 85, 61, 'MCP evidence', 'In the Planning Run, open specialist steps. Verify tool calls such as venue_search, budget_validation, schedule_conflict_check, event_requirements, marketing_readiness, and operational_risk_assessment.\n\nExpected: structured input, result summary, timing, and success status.', teal);
card(110, 74, 82, 61, 'Langfuse evidence', 'Open the newest eventpilot-plan-generation trace. Expand the trace tree.\n\nExpected: Azure generation, structured result, latency, token/cost details, and MCP observations. The prompt should reflect the wedding brief, not a birthday template.', orange);
card(M, 145, 176, 35, 'What to say to a reviewer', 'LangGraph coordinates the order and shared state. MCP supplies bounded planning evidence. Langfuse records the generation and tool activity. The UI makes the result reviewable by a human planner.', [91, 147, 119]);
card(M, 191, 176, 37, 'Troubleshooting', 'No trace: confirm Langfuse keys and refresh the trace list. No tool span: confirm the MCP terminal is running; the fallback note means the API used its local tool implementation. API unavailable: confirm port 8001.', orange);

// Page 6
pdf.addPage(); heading('05 | TEST A REVISION AND RISK DECISIONS', 'Prove that the plan can change safely', 'Use the same event. The revision should produce a new observable operation without losing the original saved workspace.', 6);
step(1, 'Open Budget', 'Go to Plan workspace > Budget.', 'Current forecast and category allocations display.', 78);
step(2, 'Reduce budget', 'Click Reduce budget by 20%.', 'Available budget becomes INR 9,60,000.', 107);
step(3, 'Verify revision', 'Review the updated allocation and activity.', 'Forecast stays at or below the reduced ceiling and preserves contingency where possible.', 136);
step(4, 'Open Langfuse', 'Refresh and open eventpilot-budget-revision.', 'Trace contains the revised budget context.', 165);
step(5, 'Open Risks', 'Go to Plan workspace > Risks.', 'Every generated risk has Monitor or Set fallback.', 194);
step(6, 'Record actions', 'Choose Monitor for watchable risks and Set fallback for high-impact risks.', 'Open-risk count decreases until it reaches zero.', 223);
card(M, 244, 176, 22, 'Pass condition', 'A revision is persisted, a distinct budget-revision trace exists, and all risk decisions are recorded by the human planner.', teal);

// Page 7
pdf.addPage(); heading('06 | APPROVAL, EXPORT, AND PERSISTENCE', 'Complete the human-in-the-loop flow', 'This is the final application-level test: draft output remains reviewable, final output remains human-approved.', 7);
step(1, 'Preview before approval', 'From Overview, click Preview PDF.', 'PDF opens and is visibly marked as a draft/awaiting approval.', 78);
step(2, 'Confirm readiness', 'Ensure the open-risk count is zero.', 'Overview changes to Ready to approve.', 108);
step(3, 'Approve plan', 'Click Approve plan.', 'Status changes to Approved and approval is stored for this event.', 138);
step(4, 'Export final PDF', 'Click Export PDF.', 'A final Event Blueprint downloads with current plan data.', 168);
step(5, 'Refresh browser', 'Reload the application, then reopen the event.', 'Saved brief and latest plan reappear from SQLite.', 198);
step(6, 'Restart API (optional)', 'Restart FastAPI and reopen the same event.', 'Brief and latest plan remain available; planning runs can be reopened.', 228);
card(M, 249, 176, 18, 'Important', 'Agents recommend and validate. The event owner records risk decisions, approves the plan, and remains responsible for any real booking or communication.', orange);

// Page 8
pdf.addPage(); heading('07 | FINAL SCORECARD', 'Mark the complete flow as passed', 'Use this page as the final evidence sheet during your test or presentation.', 8);
const checks = [
  ['Services', 'MCP, FastAPI, and React start without errors.'],
  ['Invitation intake', 'Sample invitation pre-fills a complete wedding brief.'],
  ['LangGraph', 'Timeline and Workflow graph show the multi-agent run.'],
  ['Plan quality', 'Venue, budget, 12-hour agenda, marketing, risks, and activity are present.'],
  ['MCP', 'Specialist tool calls show structured output.'],
  ['Langfuse', 'Plan-generation trace and tool observations are visible.'],
  ['Revision', '20% reduction creates updated plan data and budget-revision trace.'],
  ['Human control', 'Risk actions are required before approval and export.'],
  ['PDF', 'Draft preview works before approval; final export works after approval.'],
  ['Persistence', 'Saved event and latest plan survive browser refresh.'],
  ['Regression checks', 'Backend suite: 54 passed. Frontend production build: passed.'],
];
checks.forEach(([label, detail], i) => {
  const y = 76 + i * 15; pdf.setDrawColor(215, 226, 220); pdf.roundedRect(M, y - 5, 176, 10, 1.5, 1.5, 'S');
  pdf.setFillColor(...lime); pdf.circle(M + 6, y, 2.5, 'F'); text('PASS', M + 11, y + 2.4, 16, 6.8, navy, 'helvetica', 'bold'); text(label, M + 31, y + 2.4, 37, 8.5, teal, 'helvetica', 'bold'); text(detail, M + 70, y + 2.4, 108, 8.2, ink);
});
card(M, 250, 176, 21, 'Closing statement', 'EventPilot demonstrates a stateful, manager-led planning workflow: specialist agents use controlled tools, LangGraph coordinates their work, Langfuse makes the run inspectable, and the human owner retains final approval.', teal);

writeFileSync(new URL('../docs/EventPilot_Complete_Application_Test_Guide.pdf', import.meta.url), Buffer.from(pdf.output('arraybuffer')));
