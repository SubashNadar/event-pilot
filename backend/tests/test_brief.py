"""Dynamic brief intake through POST /api/v1/chat/brief (rule-based mode)."""

from datetime import date, timedelta

from conftest import TestClient  # noqa: F401  (fixture module import)


def turn(client, **body):
    response = client.post("/api/v1/chat/brief", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def test_one_sentence_fills_five_fields_and_asks_only_whats_left(client):
    result = turn(client, message="Wedding reception in Bandra for 200 guests on 14 Feb 2027, budget 10 lakh")
    assert result["answers"] == {"eventType": "Wedding", "location": "Bandra West, Mumbai", "attendees": "200", "budget": "1000000", "date": "2027-02-14"}
    assert result["missing"] == ["objective", "name"] and not result["ready"]
    assert result["reply"].startswith("Got it: a wedding, in Bandra West, Mumbai, for 200 guests")
    question = result["next"]
    assert question["field"] == "objective" and question["prompt"] == "What matters most for this wedding?"
    assert question["options"][0]["label"] == "Smooth guest hospitality and dining for both families"


def test_questions_and_options_adapt_to_what_is_known(client):
    first = turn(client, message="")
    assert first["next"]["field"] == "eventType"
    step = turn(client, field="eventType", value="team retreat", answers=first["answers"])
    assert step["answers"]["eventType"] == "Corporate offsite"
    assert step["next"]["prompt"] == "Where will the corporate offsite be held?"
    assert [o["value"] for o in step["next"]["options"]][:2] == ["Goa", "Jaipur"]  # destinations first for offsites
    step = turn(client, field="location", value="Goa", answers=step["answers"])
    assert step["next"]["prompt"] == "How many guests are you expecting in Goa?"
    assert [o["value"] for o in step["next"]["options"]] == ["20", "40", "80", "150"]
    step = turn(client, message="40", answers=step["answers"])  # plain reply answers the question on screen
    assert step["answers"]["attendees"] == "40"
    budget = step["next"]
    assert budget["prompt"] == "What's the total budget for 40 guests in Goa?"
    assert [o["label"] for o in budget["options"]] == ["₹2.5L", "₹4L", "₹7.5L"]
    assert "₹6,000/guest" in budget["options"][0]["hint"]


def test_low_budget_warning_with_quick_fixes_and_dismiss(client):
    result = turn(client, message="wedding in Mumbai for 350 guests, budget 2.5 lakh")
    warning = result["warnings"][0]
    assert warning["id"] == "budget_low" and "₹714 a head" in warning["message"]
    fix = warning["options"][0]
    fixed = turn(client, patch=fix["patch"], answers=result["answers"])
    assert fixed["answers"]["budget"] == fix["patch"]["budget"] and not fixed["warnings"]
    kept = turn(client, answers=result["answers"], dismissed=["budget_low"])
    assert not kept["warnings"]


def test_validation_errors_and_date_suggestions(client):
    past = (date.today() - timedelta(days=3)).isoformat()
    result = turn(client, field="date", value=past, answers={"eventType": "Birthday party"})
    assert result["errors"]["date"] == "That date has passed. Please choose a future date."
    assert result["next"]["field"] == "location"
    dates = turn(client, ask="date", answers={"eventType": "Birthday party"})["next"]
    assert dates["prompt"] == "When is it? A birthday party usually needs about 3 weeks to plan."
    first = date.fromisoformat(dates["options"][0]["value"])
    assert first.weekday() == 5 and first >= date.today() + timedelta(weeks=3)


def test_unknown_city_warns_and_ready_when_complete(client):
    answers = {"eventType": "Conference", "location": "Shillong", "attendees": "300", "budget": "12000000", "date": "2027-06-12", "objective": "Strong speaker line-up and networking"}
    result = turn(client, message="North East Tech Summit", answers=answers)
    assert result["answers"]["name"] == "North East Tech Summit"
    assert result["ready"] and result["next"] is None
    assert any(w["id"] == "city_not_in_catalog" for w in result["warnings"])
    assert [item["display"] for item in result["brief"]][3] == "₹1.2Cr (₹1,20,00,000)"


def test_editing_a_field_reasks_it_then_moves_on(client):
    answers = {"eventType": "Workshop", "location": "Pune", "attendees": "60", "budget": "200000", "date": "2027-03-13", "objective": "Hands-on learning with exercises", "name": "Pune AI Workshop"}
    ask = turn(client, ask="attendees", answers=answers)
    assert ask["next"]["field"] == "attendees" and not ask["ready"]
    done = turn(client, message="90", ask="attendees", answers=answers)
    assert done["answers"]["attendees"] == "90" and done["ready"] and done["next"] is None
