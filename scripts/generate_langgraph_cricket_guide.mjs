import { jsPDF } from '../frontend/node_modules/jspdf/dist/jspdf.es.min.js';
import { writeFileSync } from 'node:fs';

const pdf = new jsPDF({ unit: 'mm', format: 'a4' });
const width = 210;
const height = 297;
const margin = 18;
const navy = [20, 49, 47];
const teal = [25, 117, 109];
const lime = [215, 237, 116];
const ink = [28, 47, 45];
const muted = [92, 111, 106];
const paper = [248, 249, 246];

const clean = value => String(value).replace(/[–—]/g, '-');
const lines = (text, maxWidth, size = 10) => {
  pdf.setFontSize(size);
  return pdf.splitTextToSize(clean(text), maxWidth);
};
const footer = page => {
  pdf.setDrawColor(215, 226, 220);
  pdf.line(margin, 283, width - margin, 283);
  pdf.setFont('helvetica', 'normal');
  pdf.setFontSize(8);
  pdf.setTextColor(...muted);
  pdf.text('EVENTPILOT | LANGGRAPH EXPLAINER', margin, 289);
  pdf.text(`PAGE ${page}`, width - margin, 289, { align: 'right' });
};
const heading = (eyebrow, title, subtitle) => {
  pdf.setFillColor(...paper);
  pdf.rect(0, 0, width, height, 'F');
  pdf.setTextColor(...teal);
  pdf.setFont('helvetica', 'bold');
  pdf.setFontSize(9);
  pdf.text(eyebrow, margin, 24);
  pdf.setTextColor(...ink);
  pdf.setFont('times', 'bold');
  pdf.setFontSize(28);
  pdf.text(title, margin, 42);
  pdf.setTextColor(...muted);
  pdf.setFont('helvetica', 'normal');
  pdf.setFontSize(10.5);
  pdf.text(lines(subtitle, 155, 10.5), margin, 53);
};
const box = (x, y, w, h, label, body, accent = teal) => {
  pdf.setFillColor(255, 255, 255);
  pdf.setDrawColor(216, 227, 221);
  pdf.roundedRect(x, y, w, h, 2, 2, 'FD');
  pdf.setFillColor(...accent);
  pdf.roundedRect(x, y, 5, h, 2, 2, 'F');
  pdf.setTextColor(...accent);
  pdf.setFont('helvetica', 'bold');
  pdf.setFontSize(8);
  pdf.text(label.toUpperCase(), x + 11, y + 12);
  pdf.setTextColor(...ink);
  pdf.setFont('helvetica', 'normal');
  pdf.setFontSize(9.3);
  pdf.text(lines(body, w - 19, 9.3), x + 11, y + 23);
};

// Cover
pdf.setFillColor(...navy);
pdf.rect(0, 0, width, height, 'F');
pdf.setFillColor(...lime);
pdf.circle(184, 30, 27, 'F');
pdf.setDrawColor(69, 101, 94);
pdf.circle(184, 30, 36, 'S');
pdf.circle(184, 30, 45, 'S');
pdf.setTextColor(...lime);
pdf.setFont('helvetica', 'bold');
pdf.setFontSize(9);
pdf.text('EVENTPILOT | COURSE 4 EXPLAINER', margin, 31);
pdf.setTextColor(244, 248, 246);
pdf.setFont('times', 'bold');
pdf.setFontSize(35);
pdf.text(['LangGraph,', 'explained like', 'a cricket match.'], margin, 68);
pdf.setTextColor(193, 211, 204);
pdf.setFont('helvetica', 'normal');
pdf.setFontSize(12);
pdf.text(lines('Using the Meera and Karthik Wedding Reception plan as the working example.', 130, 12), margin, 130);
pdf.setDrawColor(74, 105, 98);
pdf.line(margin, 185, width - margin, 185);
[['EVENT', 'Meera and Karthik Wedding Reception'], ['SCALE', '350 guests | Whitefield, Bengaluru'], ['PLAN STATUS', 'Ready for review | 4 open decisions']].forEach(([label, value], index) => {
  const y = 204 + index * 20;
  pdf.setTextColor(...lime);
  pdf.setFont('helvetica', 'bold');
  pdf.setFontSize(8);
  pdf.text(label, margin, y);
  pdf.setTextColor(237, 244, 241);
  pdf.setFont('helvetica', 'normal');
  pdf.setFontSize(10);
  pdf.text(value, 58, y);
});
pdf.setTextColor(193, 211, 204);
pdf.setFontSize(9);
pdf.text('A simple guide to explain the graph during your project demo.', margin, 266);

// Page 2
pdf.addPage();
heading('01 | THE SIMPLE IDEA', 'LangGraph is the match plan.', 'It defines who works next, what information they receive, and what happens when a check finds a problem.');
box(margin, 77, 174, 34, 'In cricket', 'A captain does not ask every player to do every job. The bowler bowls, the wicketkeeper watches close chances, the scorer tracks runs, and the umpire checks decisions.', [217, 137, 61]);
box(margin, 120, 174, 34, 'In EventPilot', 'Each specialist agent owns a planning discipline. LangGraph is the captain’s match plan that sends the wedding brief to the right specialists and brings their decisions together.', teal);
pdf.setTextColor(...ink);
pdf.setFont('times', 'bold');
pdf.setFontSize(21);
pdf.text('Why not one AI prompt?', margin, 177);
pdf.setFont('helvetica', 'normal');
pdf.setFontSize(10);
pdf.setTextColor(...muted);
pdf.text(lines('One large prompt can produce an answer, but it is difficult to check who made each decision, whether the budget was respected, or what should happen when a risk is unresolved. LangGraph makes those steps explicit and repeatable.', 165, 10), margin, 188);
pdf.setFillColor(232, 243, 237);
pdf.roundedRect(margin, 226, 174, 30, 2, 2, 'F');
pdf.setTextColor(...teal);
pdf.setFont('helvetica', 'bold');
pdf.setFontSize(9);
pdf.text('ONE-SENTENCE DEMO EXPLANATION', margin + 10, 238);
pdf.setTextColor(...ink);
pdf.setFont('helvetica', 'normal');
pdf.setFontSize(11);
pdf.text(lines('“LangGraph is our match plan: it coordinates the agents, checks their combined work, and only sends the plan forward when it is ready for human review.”', 154, 11), margin + 10, 248);
footer(2);

// Page 3
pdf.addPage();
heading('02 | WHAT HAPPENED TO THIS WEDDING PLAN', 'The graph is a team sheet.', 'The same wedding brief is shared as controlled state, then each specialist returns a focused recommendation.');
const agents = [
  ['Logistics Lead', 'Ground staff', 'Venue capacity, parking, entry and exit flow, vendor arrival windows.'],
  ['Budget and Finance', 'Scorekeeper', 'Budget allocation, contingency reserve, and total forecast.'],
  ['Schedule Coordinator', 'Match referee', 'Reception timeline, photography windows, dinner flow, and transitions.'],
  ['Requirements Agent', 'Team manager', 'Family coordination, accessibility, guest hospitality, and event needs.'],
  ['Marketing Agent', 'Communications lead', 'Invitations, RSVP reminders, arrival details, and guest updates.'],
  ['Risk Operations', 'Rain-plan captain', 'RSVP variance, weather, AV/power, safety, and fallback actions.'],
];
agents.forEach(([agent, cricket, detail], index) => {
  const col = index % 2;
  const row = Math.floor(index / 2);
  const x = margin + col * 88;
  const y = 76 + row * 52;
  pdf.setFillColor(255, 255, 255);
  pdf.setDrawColor(217, 227, 222);
  pdf.roundedRect(x, y, 80, 44, 2, 2, 'FD');
  pdf.setTextColor(...teal);
  pdf.setFont('helvetica', 'bold');
  pdf.setFontSize(9);
  pdf.text(agent, x + 8, y + 12);
  pdf.setTextColor(203, 120, 47);
  pdf.setFontSize(8);
  pdf.text(`Cricket role: ${cricket}`, x + 8, y + 20);
  pdf.setTextColor(...muted);
  pdf.setFont('helvetica', 'normal');
  pdf.setFontSize(8.5);
  pdf.text(lines(detail, 64, 8.5), x + 8, y + 29);
});
pdf.setTextColor(...ink);
pdf.setFont('times', 'bold');
pdf.setFontSize(20);
pdf.text('Then the captain and umpire act.', margin, 249);
pdf.setTextColor(...muted);
pdf.setFont('helvetica', 'normal');
pdf.setFontSize(10);
pdf.text(lines('The Event Manager acts like the captain: it combines the specialist reports into one plan. The Review node acts like the third umpire: it checks the numbers, schedule labels, and required outputs. If a problem is found, the reflection path corrects the plan before it reaches you.', 165, 10), margin, 260);
footer(3);

// Page 4
pdf.addPage();
heading('03 | HOW TO READ YOUR SCREEN', 'Ready for review is not the same as approved.', 'Your dashboard shows that the graph has completed its planning run, but it deliberately leaves decisions to the event owner.');
box(margin, 77, 82, 46, 'Budget forecast: INR 12,00,000', 'The finance agent and review step kept the forecast aligned with the budget ceiling. This is like the scoreboard confirming the total is correct.', teal);
box(110, 77, 82, 46, 'Plan confidence: 90%', 'This is a planning signal based on current assumptions. It is not a guarantee; late RSVP changes or vendor changes can still affect the event.', [102, 172, 128]);
box(margin, 132, 82, 46, 'Open risks: 4', 'These are captain decisions, not system failures. Example: RSVP variance needs a catering fallback, because the guest count can still change.', [217, 137, 61]);
box(110, 132, 82, 46, 'Approve plan', 'Approval is the match captain saying the chosen tactics are accepted. Export becomes available only after required risk actions are recorded.', [217, 137, 61]);
pdf.setTextColor(...ink);
pdf.setFont('times', 'bold');
pdf.setFontSize(20);
pdf.text('Your 60-second demo script', margin, 207);
const script = [
  '“I entered a wedding brief for 350 guests in Whitefield with a INR 12 lakh budget.”',
  '“LangGraph sends that shared brief to specialist agents, just like a cricket captain assigns roles to a team.”',
  '“The Event Manager combines their recommendations, and the Review node checks the combined plan like a third umpire.”',
  '“The dashboard is ready for review, but the four risks still require my decision. That human approval gate is intentional.”',
  '“After I record risk actions and approve, I can export the final event blueprint.”',
];
script.forEach((item, index) => {
  const y = 221 + index * 11;
  pdf.setFillColor(...teal);
  pdf.circle(margin + 3, y - 2.5, 3, 'F');
  pdf.setTextColor(255, 255, 255);
  pdf.setFont('helvetica', 'bold');
  pdf.setFontSize(7);
  pdf.text(String(index + 1), margin + 3, y - .3, { align: 'center' });
  pdf.setTextColor(...ink);
  pdf.setFont('helvetica', 'normal');
  pdf.setFontSize(9.2);
  pdf.text(lines(item, 155, 9.2), margin + 11, y);
});
footer(4);

writeFileSync(new URL('../docs/LangGraph-Cricket-Wedding-Guide.pdf', import.meta.url), Buffer.from(pdf.output('arraybuffer')));
