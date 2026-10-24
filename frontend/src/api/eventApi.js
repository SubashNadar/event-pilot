import { request } from '../lib/http';

export function createEvent(event) {
  return request('/events', {
    method: 'POST',
    body: JSON.stringify({
      name: event.name,
      event_date: event.date,
      location: event.location,
      attendees: Number(event.attendees),
      budget: Number(event.budget),
      objective: event.objective
    })
  });
}

const toPayload = event => ({
  name: event.name,
  event_date: event.date,
  location: event.location,
  attendees: Number(event.attendees),
  budget: Number(event.budget),
  objective: event.objective
});

export function listEvents() {
  return request('/events');
}

export function getEvent(eventId) {
  return request(`/events/${eventId}`);
}

export function updateEvent(eventId, event) {
  return request(`/events/${eventId}`, {
    method: 'PUT',
    body: JSON.stringify(toPayload(event))
  });
}

export function getPlan(eventId) {
  return request(`/events/${eventId}/plan`);
}

export function generatePlan(eventId) {
  return request(`/events/${eventId}/plan`, { method: 'POST' });
}

export function reviseBudget(eventId, budget) {
  return request(`/events/${eventId}/revisions/budget`, {
    method: 'POST',
    body: JSON.stringify({ budget })
  });
}

export function validatePlanningChatTurn(field, value, answers) {
  return request('/chat/planning-turn', {
    method: 'POST',
    body: JSON.stringify({ field, value: String(value), answers })
  });
}

export function queryKnowledge(question) {
  return request('/rag/query', {
    method: 'POST',
    body: JSON.stringify({ question })
  });
}

export function briefTurn(body) {
  return request('/chat/brief', {
    method: 'POST',
    body: JSON.stringify(body)
  });
}

// Saved conversations
export const BRIEF_SESSION_KEY = 'eventpilot.briefSession';

export function getChatSession(sessionId) {
  return request(`/chat/sessions/${encodeURIComponent(sessionId)}`);
}

export function linkChatSession(sessionId, eventId) {
  return request(`/chat/sessions/${encodeURIComponent(sessionId)}/event`, {
    method: 'POST',
    body: JSON.stringify({ event_id: eventId })
  });
}

export function getEventChat(eventId) {
  return request(`/events/${eventId}/chat`);
}

export function sendPlanChat(eventId, message, sessionId) {
  return request(`/events/${eventId}/chat`, {
    method: 'POST',
    body: JSON.stringify({ message, session_id: sessionId || undefined })
  });
}
