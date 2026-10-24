"""Render the EventPilot LangGraph topology as a local PNG.

LangGraph's default Mermaid PNG helper may use an external rendering service.
This renderer keeps the workflow definition on the local backend while creating
the static architecture image used by the Planning Run UI.
"""

from io import BytesIO
from pathlib import Path
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


def _poly_arrow(draw: ImageDraw.ImageDraw, points: list[tuple[int, int]], direction: str = "right") -> None:
    """Route connectors through rails so parallel edges never cross node labels."""
    draw.line(points, fill=TEAL, width=4, joint="curve")
    x, y = points[-1]
    heads = {
        "right": [(x, y), (x - 14, y - 8), (x - 14, y + 8)],
        "left": [(x, y), (x + 14, y - 8), (x + 14, y + 8)],
        "up": [(x, y), (x - 8, y + 14), (x + 8, y + 14)],
        "down": [(x, y), (x - 8, y - 14), (x + 8, y - 14)],
    }
    draw.polygon(heads[direction], fill=TEAL)


def render_workflow_png(graph_mermaid: str, steps: list[dict[str, Any]]) -> bytes:
    """Return a local PNG for the current compiled graph and declared step list."""
    # Accessing Mermaid confirms this is based on the compiled topology. The local
    # renderer intentionally does not send its text to an external service.
    if "event_manager" not in graph_mermaid or "review_plan" not in graph_mermaid:
        raise ValueError("The compiled workflow is missing required EventPilot nodes")

    image = Image.new("RGB", (2160, 1040), BG)
    draw = ImageDraw.Draw(image)
    draw.text((70, 52), "EVENTPILOT", font=_font(22, True), fill=TEAL)
    draw.text((70, 92), "Compiled LangGraph workflow", font=_font(38, True), fill=INK)
    draw.text((70, 146), "Static architecture diagram generated locally from the backend graph definition.", font=_font(19), fill="#5E726E")

    parallel = [step for step in steps if step.get("group") == "parallel"]
    sequential = [step for step in steps if step.get("group") != "parallel"]
    draw.rounded_rectangle((335, 235, 1285, 760), radius=20, fill="#F3F8F5", outline=LINE, width=2)
    draw.text((370, 267), "PARALLEL SPECIALIST TEAM", font=_font(16, True), fill=TEAL)
    draw.text((370, 293), "Structured evidence moves through shared rails to avoid connector crossings.", font=_font(14), fill="#5E726E")
    start = _node(draw, 70, 455, "Event brief", "shared state", LIME, TEAL)
    specialist_boxes = []
    for index, step in enumerate(parallel):
        x = 430 + (index % 3) * 280
        y = 370 + (index // 3) * 210
        title = ["Venue & logistics", "Budget allocation", "Event agenda", "Requirements", "Guest communication", "Risk operations"][index]
        specialist_boxes.append(_node(draw, x, y, title, str(step.get("agent", "specialist")), MINT, TEAL))
    input_rail, output_rail = 390, 1255
    draw.line((input_rail, 417, input_rail, 627), fill=TEAL, width=4)
    draw.line((output_rail, 417, output_rail, 627), fill=TEAL, width=4)
    _poly_arrow(draw, [(start[2], 502), (input_rail, 502)], "right")
    for box in specialist_boxes:
        midpoint = (box[1] + box[3]) // 2
        _poly_arrow(draw, [(input_rail, midpoint), (box[0], midpoint)], "right")
        _poly_arrow(draw, [(box[2], midpoint), (output_rail, midpoint)], "right")

    manager_x = 1360
    manager = _node(draw, manager_x, 455, "Event Manager", "synthesis", MINT, TEAL)
    _poly_arrow(draw, [(output_rail, 502), (manager[0], 502)], "right")
    review = _node(draw, 1640, 455, "Review gate", "checks and routing", "#FFF1E7", ORANGE)
    _arrow(draw, (manager[2], (manager[1] + manager[3]) // 2), (review[0], (review[1] + review[3]) // 2))

    final = _node(draw, 1920, 455, "Final plan", "human review", LIME, TEAL)
    _arrow(draw, (review[2], 502), (final[0], 502))
    replan = next((step for step in sequential if step.get("id") == "replan"), None)
    if replan:
        replan_box = _node(draw, 1640, 705, "Re-plan", "one bounded retry", "#FFF1E7", ORANGE)
        _poly_arrow(draw, [(1750, review[3]), (1750, 675), (1750, replan_box[1])], "down")
        _poly_arrow(draw, [(replan_box[0], 752), (1580, 752), (1580, 650), (1470, 650), (1470, manager[3])], "up")
    draw.text((70, 945), "Flow: event brief -> six parallel specialists -> Event Manager -> review gate -> human-approved final plan.", font=_font(17), fill="#5E726E")

    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def main() -> None:
    """Write a shareable local PNG from the current compiled LangGraph graph."""
    from app.graphs.event_workflow import STEPS, build_graph

    graph = build_graph().compile().get_graph()
    destination = Path(__file__).resolve().parents[3] / "docs" / "workflow-graph.png"
    destination.write_bytes(render_workflow_png(graph.draw_mermaid(), STEPS))
    print(f"Wrote {destination.resolve()}")


if __name__ == "__main__":
    main()
