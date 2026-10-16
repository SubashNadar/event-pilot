export const initialEvent = {
  name: 'AI Leadership Workshop',
  date: '2026-11-21',
  location: 'Bengaluru',
  attendees: 200,
  budget: 500000,
  objective: 'Build practical AI leadership skills for emerging managers and create peer connections.'
};

const birthdayPlan = event => ({
  type: 'birthday',
  venue: { name: 'Private celebration venue', area: `${event.location} · accommodates ${event.attendees} guests`, status: 'Shortlist ready' },
  logistics: ['Decor and photo backdrop', 'Cake table, music, and dance area', 'Dinner seating and guest welcome desk'],
  checkpoints: ['Venue options shortlisted', 'Catering requirement noted', 'Confirm cake and music package'],
  budgetLabels: ['Venue and music', 'Food and beverages', 'Cake and desserts', 'Decor and lighting', 'Photography', 'Contingency'],
  budgetShares: [28, 31, 8, 14, 11, 8],
  reducedShares: [27, 32, 8, 12, 10, 11],
  agenda: [['6:00 PM', 'Guest arrival and welcome drinks', 'Operations'], ['6:30 PM', 'Games and photo time', 'Host'], ['7:15 PM', 'Cake cutting and speeches', 'Programme'], ['8:00 PM', 'Dinner service', 'Catering'], ['9:00 PM', 'Music, dance, and closing', 'Entertainment']],
  overviewAgenda: [['6:00 PM', 'Guest arrival and welcome drinks', '30 min · Welcome area'], ['6:30 PM', 'Games and photo time', '45 min · Celebration space'], ['7:15 PM', 'Cake cutting and speeches', '45 min · Main stage'], ['8:00 PM', 'Dinner and music', '120 min · Dining area']],
  marketing: { title: 'Guest communication plan', description: 'Keep invitations personal and use RSVP reminders to confirm catering, seating, and dietary requirements.', steps: [['Week 1', 'Send digital invitation and RSVP link'], ['Week 2', 'Share reminder and collect meal preferences'], ['Week 3', 'Send venue, dress code, and arrival details']], checks: ['Guest list and RSVP tracker prepared', 'Invitation message drafted', 'Approve return-gift quantity'] },
  risks: [{ level: 'High', title: 'Weather disruption for an outdoor venue', detail: 'Reserve a covered space or indoor fallback before confirming the venue.', resolved: 'Covered venue alternative and backup seating are assigned.' }, { level: 'Medium', title: 'RSVP count changes close to the event', detail: 'Confirm final catering quantity three days before the celebration.' }],
  activity: [['10:42 AM', 'Budget & Finance', 'Prepared the celebration budget and contingency reserve.', '₹'], ['10:36 AM', 'Event Manager', 'Created the birthday event plan from the current brief.', 'M'], ['10:30 AM', 'Logistics', `Shortlisted private celebration venues in ${event.location}.`, 'L'], ['10:15 AM', 'Schedule Coordination', 'Drafted the cake-cutting, dinner, and music schedule.', 'S'], ['9:58 AM', 'Marketing & Promotion', 'Prepared the invitation and RSVP communication plan.', 'P']],
  confidence: 84
});

const standardPlan = event => ({
  type: 'standard',
  venue: { name: 'The Terrace Hall', area: `${event.location} · ${event.attendees + 20} seated capacity`, status: 'Held' },
  logistics: ['Full-day rental including standard AV', 'Four breakout rooms and registration lounge', 'Accessible entrance and nearby metro access'],
  checkpoints: ['Venue hold placed', 'Catering quote received', 'Confirm keynote travel plan'],
  budgetLabels: ['Venue and AV', 'Catering', 'Programme and speakers', 'Promotion', 'Operations', 'Contingency'],
  budgetShares: [34, 21, 14, 11, 10, 10], reducedShares: [36, 20, 15, 10, 9, 10],
  agenda: [['8:00 AM', 'Vendor load-in and AV check', 'Logistics'], ['9:00 AM', 'Registration and breakfast', 'Operations'], ['10:00 AM', 'Keynote: Leading with AI', 'Programme'], ['11:00 AM', 'Practical leadership lab', 'Facilitators'], ['4:30 PM', 'Closing and feedback collection', 'Marketing']],
  overviewAgenda: [['9:00 AM', 'Registration and breakfast', '60 min · Arrival lounge'], ['10:00 AM', 'Keynote: Leading with AI', '45 min · Main stage'], ['11:00 AM', 'Practical leadership lab', '90 min · Breakout rooms'], ['2:00 PM', 'Applied AI roundtables', '120 min · Workshop floor']],
  marketing: { title: 'Launch campaign', description: 'Position the workshop as a practical leadership lab rather than an introductory AI session.', steps: [['Week 1', 'Landing page, partner outreach, speaker announcement'], ['Week 2-3', 'LinkedIn campaign and manager referral sequence'], ['Week 4', 'Last-call and attendee preparation email']], checks: ['Audience definition approved', 'Content calendar drafted', 'Approve promotion spend'] },
  risks: [{ level: 'High', title: 'Keynote travel disruption', detail: 'Remote fallback and local host must be confirmed by 31 Oct.', resolved: 'Remote keynote fallback and local host are assigned.' }, { level: 'Medium', title: 'Registration volume below target', detail: 'Activate partner referral campaign if signups are below 100 at week two.' }],
  activity: [['10:42 AM', 'Budget & Finance', 'Updated catering estimate after the venue selection.', '₹'], ['10:36 AM', 'Event Manager', 'Flagged keynote fallback for your decision.', 'M'], ['10:30 AM', 'Logistics', 'Placed a soft hold on The Terrace Hall.', 'L'], ['10:15 AM', 'Schedule Coordination', 'Reserved a 30-minute AV contingency before the keynote.', 'S'], ['9:58 AM', 'Marketing & Promotion', 'Drafted the partner referral sequence for review.', 'P']],
  confidence: 86
});

export function buildEventPlan(event) {
  return /birthday|celebration|party/i.test(`${event.name} ${event.objective}`) ? birthdayPlan(event) : standardPlan(event);
}
