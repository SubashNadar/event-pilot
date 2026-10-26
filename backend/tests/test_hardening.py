"""Input rules and the unreachable-service memory: bad input gets a clear reason, and a dead web host isn't retried on every call."""

import asyncio

import httpx
import pytest

from app.integrations import http


def _body(**overrides):
    body = {"name": "QA Reception", "event_date": "2027-03-11", "location": "Koramangala, Bengaluru", "attendees": 120, "budget": 1500000, "objective": "A reception for 120 guests."}
    body.update(overrides)
    return body


def test_event_date_in_the_past_is_refused_with_a_reason(client):
    response = client.post("/api/v1/events", json=_body(event_date="2020-01-01"))
    assert response.status_code == 422
    assert "has already passed" in response.text


def test_budget_below_the_minimum_is_refused_with_a_reason(client):
    response = client.post("/api/v1/events", json=_body(budget=1000, attendees=10))
    assert response.status_code == 422
    assert "too low for an event" in response.text


def test_budget_under_500_per_guest_is_refused_with_a_reason(client):
    response = client.post("/api/v1/events", json=_body(budget=60000, attendees=200))
    assert response.status_code == 422
    assert "per guest" in response.text


def test_unreachable_host_is_skipped_after_the_first_failure(monkeypatch):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.host)
        raise httpx.ConnectError("host is down", request=request)

    monkeypatch.setattr(http, "TRANSPORT", httpx.MockTransport(handler))
    monkeypatch.setattr(http.settings, "free_apis_enabled", True)  # the test environment switches web services off by default
    http.clear_cache()

    async def twice():
        for _ in range(2):
            with pytest.raises(http.ServiceUnavailable):
                await http.get_json("https://service-that-is-down.test/lookup", {"q": "venue"}, ttl_s=1)

    asyncio.run(twice())
    assert calls == ["service-that-is-down.test"], "the second call must not wait for the host again"
    http.clear_cache()


def test_only_outside_checks_become_caveats_not_blocking_feedback():
    from app.graphs.event_workflow import _needs_outside_check

    assert _needs_outside_check("Venue availability for 11 Mar is unconfirmed; confirm the booking.")
    assert _needs_outside_check("Get a written quotation before booking the caterer.")
    assert not _needs_outside_check("Lunch sits too late; move it before 1 PM.")
    assert not _needs_outside_check("The budget lines do not add up to the forecast.")
