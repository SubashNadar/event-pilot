"""Render the EventPilot LangGraph topology as a local PNG.

LangGraph's default Mermaid PNG helper may use an external rendering service.
This renderer keeps the workflow definition on the local backend while creating
the static architecture image used by the Planning Run UI.
"""

from io import BytesIO
from typing import Any

from PIL import Image, ImageDraw, ImageFont


BG = "#FAF9F5"
INK = "#17312E"
TEAL = "#167C75"
MINT = "#E9F4EF"
LIME = "#D8F06A"
ORANGE = "#D97732"
LINE = "#AFCAC2"


def _font(size: int, bold: bool = False):
    try:
        name = "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf"
        return ImageFont.truetype(name, size)
    except OSError:
        return ImageFont.load_default()


def _center(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], value: str, font, fill: str) -> None:
    left, top, right, bottom = box
    bounds = draw.textbbox((0, 0), value, font=font)
    draw.text(((left + right - (bounds[2] - bounds[0])) / 2, (top + bottom - (bounds[3] - bounds[1])) / 2), value, font=font, fill=fill)


def _node(draw: ImageDraw.ImageDraw, x: int, y: int, title: str, detail: str, fill: str, outline: str) -> tuple[int, int, int, int]:
    box = (x, y, x + 218, y + 94)
    draw.rounded_rectangle(box, radius=16, fill=fill, outline=outline, width=3)
    _center(draw, (x + 8, y + 20, x + 210, y + 48), title, _font(19, True), INK)
    _center(draw, (x + 8, y + 53, x + 210, y + 77), detail, _font(13), TEAL if outline != ORANGE else ORANGE)
    return box


def _arrow(draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int]) -> None:
    draw.line((start, end), fill=TEAL, width=4)
    x, y = end
    if abs(end[0] - start[0]) >= abs(end[1] - start[1]):
        points = [(x, y), (x - 14, y - 8), (x - 14, y + 8)] if x >= start[0] else [(x, y), (x + 14, y - 8), (x + 14, y + 8)]
    else:
        points = [(x, y), (x - 8, y - 14), (x + 8, y - 14)] if y >= start[1] else [(x, y), (x - 8, y + 14), (x + 8, y + 14)]
    draw.polygon(points, fill=TEAL)


def render_workflow_png(graph_mermaid: str, steps: list[dict[str, Any]]) -> bytes:
    """Return a local PNG for the current compiled graph and declared step list."""
    # Accessing Mermaid confirms this is based on the compiled topology. The local
    # renderer intentionally does not send its text to an external service.
    if "event_manager" not in graph_mermaid or "review_plan" not in graph_mermaid:
        raise ValueError("The compiled workflow is missing required EventPilot nodes")

    image = Image.new("RGB", (1780, 980), BG)
    draw = ImageDraw.Draw(image)
    draw.text((70, 52), "EVENTPILOT", font=_font(22, True), fill=TEAL)
    draw.text((70, 92), "Compiled LangGraph workflow", font=_font(38, True), fill=INK)
    draw.text((70, 146), "Static architecture diagram generated locally from the backend graph definition.", font=_font(19), fill="#5E726E")

    parallel = [step for step in steps if step.get("group") == "parallel"]
    sequential = [step for step in steps if step.get("group") != "parallel"]
    start = _node(draw, 70, 455, "Event brief", "shared state", LIME, TEAL)
    specialist_boxes = []
    for index, step in enumerate(parallel):
        x = 370 + (index % 3) * 270
        y = 270 + (index // 3) * 210
        title = str(step["title"]).replace("Find a ", "").replace("Draft the ", "").replace("Build the ", "")
        specialist_boxes.append(_node(draw, x, y, title, str(step.get("agent", "specialist")), MINT, TEAL))
    for box in specialist_boxes:
        _arrow(draw, (start[2], (start[1] + start[3]) // 2), (box[0], (box[1] + box[3]) // 2))

    manager_x = 1210
    manager = _node(draw, manager_x, 455, "Event Manager", "synthesis", MINT, TEAL)
    for box in specialist_boxes:
        _arrow(draw, (box[2], (box[1] + box[3]) // 2), (manager[0], (manager[1] + manager[3]) // 2))
    review = _node(draw, 1490, 455, "Review", "checks and routing", "#FFF1E7", ORANGE)
    _arrow(draw, (manager[2], (manager[1] + manager[3]) // 2), (review[0], (review[1] + review[3]) // 2))

    final = _node(draw, 1490, 680, "Final plan", "human review", LIME, TEAL)
    _arrow(draw, ((review[0] + review[2]) // 2, review[3]), ((final[0] + final[2]) // 2, final[1]))
    replan = next((step for step in sequential if step.get("id") == "replan"), None)
    if replan:
        replan_box = _node(draw, 1210, 680, "Re-plan", "one bounded retry", "#FFF1E7", ORANGE)
        _arrow(draw, ((review[0] + review[2]) // 2, review[3]), ((replan_box[0] + replan_box[2]) // 2, replan_box[1]))
        _arrow(draw, (replan_box[0], (replan_box[1] + replan_box[3]) // 2), (manager[0], manager[3]))
    draw.text((70, 900), "Six specialists work in parallel, converge through the Event Manager, then pass a review gate before human approval.", font=_font(17), fill="#5E726E")

    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


if __name__ == "__main__":
    # Writes the LangGraph-rendered PNG to docs/workflow-graph.png:
    #   cd backend && .venv\Scripts\python.exe -m app.services.workflow_diagram
    from pathlib import Path

    from app.graphs.event_workflow import STEPS, build_graph

    compiled = build_graph().compile().get_graph()
    target = Path(__file__).resolve().parents[3] / "docs" / "workflow-graph.png"
    target.write_bytes(render_workflow_png(compiled.draw_mermaid(), STEPS))
    print(f"Wrote {target}")
