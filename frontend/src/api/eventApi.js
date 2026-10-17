const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8001/api/v1';

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options
  });

  if (!response.ok) {
    throw new Error((await response.json().catch(() => null))?.detail || 'Unable to reach the planning API.');
  }

  return response.json();
}

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
