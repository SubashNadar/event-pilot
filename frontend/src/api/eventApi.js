const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';

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

export function generatePlan(eventId) {
  return request(`/events/${eventId}/plan`, { method: 'POST' });
}

export function reviseBudget(eventId, budget) {
  return request(`/events/${eventId}/revisions/budget`, {
    method: 'POST',
    body: JSON.stringify({ budget })
  });
}
