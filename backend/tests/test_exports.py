"""The final plan downloads as a PDF blueprint and a PPTX brochure."""

import io

from conftest import create_event, wait_for

PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


def test_plan_exports_as_pdf_and_pptx(client):
    event = create_event(client, location="Pune", attendees=120, budget=1500000)
    run_id = client.post(f"/api/v1/events/{event['id']}/runs", json={}).json()["run_id"]
    assert wait_for(client, run_id, {"completed", "error", "paused"})["run"]["status"] == "completed"

    pdf = client.get(f"/api/v1/events/{event['id']}/exports/pdf")
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf" and pdf.content.startswith(b"%PDF")
    assert 'filename="' in pdf.headers["content-disposition"] and pdf.headers["content-disposition"].endswith('-plan.pdf"')

    pptx = client.get(f"/api/v1/events/{event['id']}/exports/pptx")
    assert pptx.status_code == 200 and pptx.headers["content-type"] == PPTX
    from pptx import Presentation

    slides = Presentation(io.BytesIO(pptx.content)).slides
    assert len(slides) == 7  # cover, overview, venue, budget, agenda, risks, next steps


def test_export_without_a_plan_is_404(client):
    event = create_event(client, location="Pune", attendees=50, budget=900000)
    assert client.get(f"/api/v1/events/{event['id']}/exports/pdf").status_code == 404
