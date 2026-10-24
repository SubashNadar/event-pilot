"""Render the EventPilot LangGraph topology as a local swimlane PNG.

LangGraph's default Mermaid PNG helper may use an external rendering service.
This renderer keeps the workflow definition on the local backend while creating
the static architecture image used by the Planning Run UI.

Four swimlanes match the step `lane` values in `app.graphs.event_workflow.STEPS`:

    RECEPTIONIST      receptionist ─▶ (brief handed to the manager)
    EVENT MANAGER     manager_intake ─▶ logistics (first) ─▶ specialists
                      coordination ─▶ event_manager ─▶ review_plan ─▶ approval
    SPECIALIST AGENTS logistics ─▶ finance, schedule, requirements, marketing, risk
    YOU (EVENT OWNER) approval ─▶ recommendations ─▶ END

Dashed orange lines are the feedback loops: the manager re-plans flagged
specialists, and the owner sends the plan back to the manager to re-split.
"""

import math
from io import BytesIO
from typing import Any

from PIL import Image, ImageDraw, ImageFont


W, H = 1800, 920
BG = "#FAF9F5"
PAPER = "#FFFFFF"
INK = "#17312E"
MUTED = "#5E726E"
TEAL = "#167C75"
MINT = "#E9F4EF"
LIME = "#D8F06A"
ORANGE = "#D97732"
GATE = "#FFF1E7"
LANE_LINE = "#DCE5E1"
GROUP_FILL = "#F3F8F5"

NODE_H = 104
FONT_FILES = {
    False: ["arial.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf", "DejaVuSans.ttf"],
    True: ["arialbd.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf", "DejaVuSans-Bold.ttf"],
}

# Swimlane bands (top, bottom) and their labels, top to bottom.
LANES = [
    ((196, 292), "RECEPTIONIST"),
    ((300, 446), "EVENT MANAGER"),
    ((454, 638), "SPECIALIST AGENTS"),
    ((646, 760), "YOU (EVENT OWNER)"),
]


def _font(size: int, bold: bool = False):
    for name in FONT_FILES[bold]:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:  # Pillow 10.1+ can scale its built-in font
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, width: int) -> list[str]:
    lines, current = [], ""
    for word in text.split():
        trial = f"{current} {word}".strip()
        if not current or draw.textlength(trial, font=font) <= width:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _center(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], value: str, font, fill: str) -> None:
    left, top, right, bottom = box
    bounds = draw.textbbox((0, 0), value, font=font)
    draw.text(((left + right - (bounds[2] - bounds[0])) / 2, (top + bottom - (bounds[3] - bounds[1])) / 2), value, font=font, fill=fill)


def _node(draw: ImageDraw.ImageDraw, x: int, y: int, w: int, title: str, detail: str, fill: str, outline: str, h: int = NODE_H) -> tuple[int, int, int, int]:
    box = (x, y, x + w, y + h)
    draw.rounded_rectangle(box, radius=16, fill=fill, outline=outline, width=3)
    title_font = _font(20, True)
    lines = _wrap(draw, title, title_font, w - 20)
    block = len(lines) * 26 + 6 + 22
    top = y + (h - block) // 2
    for index, line in enumerate(lines):
        _center(draw, (x, top + index * 26, x + w, top + (index + 1) * 26), line, title_font, INK)
    detail_top = top + len(lines) * 26 + 6
    _center(draw, (x, detail_top, x + w, detail_top + 22), detail, _font(16), ORANGE if outline == ORANGE else TEAL)
    return box


def _dash(draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int], fill: str, dash: int = 14, gap: int = 8) -> None:
    (x0, y0), (x1, y1) = start, end
    length = math.hypot(x1 - x0, y1 - y0)
    ux, uy = (x1 - x0) / length, (y1 - y0) / length
    position = 0.0
    while position < length:
        stop = min(position + dash, length)
        draw.line(((x0 + ux * position, y0 + uy * position), (x0 + ux * stop, y0 + uy * stop)), fill=fill, width=4)
        position += dash + gap


def _arrow(draw: ImageDraw.ImageDraw, *points: tuple[int, int], color: str = TEAL, dashed: bool = False) -> None:
    """Draw a polyline ending in an arrowhead that points along its last segment."""
    if dashed:
        for start, end in zip(points, points[1:]):
            _dash(draw, start, end, color)
    else:
        draw.line(points, fill=color, width=4, joint="curve")
    (x0, y0), (x1, y1) = points[-2], points[-1]
    if abs(x1 - x0) >= abs(y1 - y0):
        d = 1 if x1 >= x0 else -1
        head = [(x1, y1), (x1 - d * 16, y1 - 9), (x1 - d * 16, y1 + 9)]
    else:
        d = 1 if y1 >= y0 else -1
        head = [(x1, y1), (x1 - 9, y1 - d * 16), (x1 + 9, y1 - d * 16)]
    draw.polygon(head, fill=color)


def render_workflow_png(graph_mermaid: str, steps: list[dict[str, Any]]) -> bytes:
    """Return a local PNG for the current compiled graph and declared step list."""
    # Accessing Mermaid confirms this is based on the compiled topology. The local
    # renderer intentionally does not send its text to an external service.
    if "event_manager" not in graph_mermaid or "review_plan" not in graph_mermaid:
        raise ValueError("The compiled workflow is missing required EventPilot nodes")

    by_id = {step["id"]: step for step in steps}
    specialists = [step for step in steps if step.get("group") == "parallel" and step["id"] != "logistics_agent"]

    image = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(image)
    draw.text((40, 30), "EVENTPILOT", font=_font(20, True), fill=TEAL)
    draw.text((40, 56), "How one planning run flows, lane by lane", font=_font(36, True), fill=INK)
    draw.text((40, 106), "Each box is a step in backend/app/graphs/event_workflow.py. Read left to right. Dashed orange lines are feedback loops.", font=_font(18), fill=MUTED)

    # Swimlanes: one band per role, labelled at its left edge.
    for (top, bottom), label in LANES:
        draw.rounded_rectangle((24, top, 1776, bottom), radius=18, fill=PAPER, outline=LANE_LINE, width=2)
        draw.text((48, top + 10), label, font=_font(14, True), fill=TEAL)

    # Lane 1: the receptionist takes the brief in and hands it to the manager.
    receive = _node(draw, 250, 222, 210, by_id["receptionist"]["title"], by_id["receptionist"]["agent"], LIME, TEAL, h=72)

    # Lane 2: the manager splits the work, then the venue goes first.
    split = _node(draw, 250, 310, 210, by_id["manager_intake"]["title"], by_id["manager_intake"]["agent"], PAPER, TEAL, h=86)
    _arrow(draw, ((receive[0] + receive[2]) // 2, receive[3]), ((split[0] + split[2]) // 2, split[1]))

    # Lane 3: logistics picks the venue, then the five specialists run in parallel inside one group.
    logistics = _node(draw, 250, 478, 210, by_id["logistics_agent"]["title"], by_id["logistics_agent"]["agent"], LIME, TEAL, h=88)
    _arrow(draw, ((split[0] + split[2]) // 2, split[3]), ((logistics[0] + logistics[2]) // 2, logistics[1]))
    group = (486, 468, 1514, 626)
    draw.rounded_rectangle(group, radius=18, fill=GROUP_FILL, outline=TEAL, width=2)
    draw.text((group[0] + 14, group[1] + 8), "RUN IN PARALLEL, once the venue is chosen", font=_font(14, True), fill=TEAL)
    _arrow(draw, (logistics[2], 522), (group[0], 522))
    specialist_boxes = []
    for index, step in enumerate(specialists):
        box = _node(draw, 500 + index * 200, 504, 180, step["title"], step["agent"], MINT, TEAL, h=92)
        specialist_boxes.append(box)

    # Lane 2 again: the manager combines the specialists' reports, then reviews the plan.
    combine = _node(draw, 895, 310, 210, by_id["event_manager"]["title"], by_id["event_manager"]["agent"], PAPER, TEAL, h=86)
    _arrow(draw, (1000, group[1]), (1000, combine[3]))  # the group's reports flow up to the manager
    review = _node(draw, 1185, 310, 230, by_id["review_plan"]["title"], "Rules and LLM judge", GATE, ORANGE, h=86)
    _arrow(draw, (combine[2], 353), (review[0], 353))

    # The review loop: not met, so the manager re-plans the flagged parts and feeds back to the specialists.
    replan = _node(draw, 1470, 310, 230, by_id["replan"]["title"], "Feedback loop", GATE, ORANGE, h=86)
    _arrow(draw, (review[2], 353), (replan[0], 353), color=ORANGE, dashed=True)
    draw.text((review[2] + 6, 300), "not met", font=_font(15, True), fill=ORANGE)
    _arrow(draw, ((replan[0] + replan[2]) // 2, replan[3]), ((replan[0] + replan[2]) // 2, 540), (group[2], 540), color=ORANGE, dashed=True)
    draw.text(((replan[0] + replan[2]) // 2 + 12, 462), "feedback to the", font=_font(15, True), fill=ORANGE)
    draw.text(((replan[0] + replan[2]) // 2 + 12, 482), "flagged specialists", font=_font(15, True), fill=ORANGE)

    # Lane 4: the review passes, so the owner approves; approval leads to the summary.
    approval = (1185, 672, 1415, 744)
    draw.rounded_rectangle(approval, radius=18, fill=INK)
    _center(draw, approval, "Your approval", _font(19, True), PAPER)
    _arrow(draw, (1290, review[3]), (1290, approval[1]))  # passes through the gap between specialist boxes
    draw.text((1296, 404), "all checks met", font=_font(15, True), fill=TEAL)
    recommend = _node(draw, 1500, 662, 210, by_id["recommendations"]["title"], by_id["recommendations"]["agent"], PAPER, TEAL, h=86)
    _arrow(draw, (approval[2], 708), (recommend[0], 708))
    draw.text((approval[2] + 6, 684), "approved", font=_font(15, True), fill=TEAL)

    # The owner sends the plan back: the route runs round the left margin to the manager, who re-splits it.
    _arrow(draw, (approval[0], 708), (40, 708), (40, 353), (split[0], 353), color=ORANGE, dashed=True)
    draw.text((300, 682), "not OK: the owner sends it back, and the manager re-splits it", font=_font(15, True), fill=ORANGE)

    # Legend and reading notes.
    legend = [(LIME, "Starts the run"), (MINT, "Runs in parallel"), (PAPER, "Sequential step"), (GATE, "Review and feedback loop"), (INK, "Your decision")]
    for index, (color, label) in enumerate(legend):
        x = 40 + [0, 240, 470, 700, 1010][index]
        draw.rounded_rectangle((x, 790, x + 28, 810), radius=6, fill=color, outline=ORANGE if color == GATE else TEAL, width=2)
        draw.text((x + 40, 786), label, font=_font(17), fill=INK)
    draw.text((40, 840), "The receptionist hands the brief to the Event Manager, who splits it. Logistics picks the venue first; the other five specialists then run in parallel.", font=_font(17), fill=MUTED)
    draw.text((40, 868), "The manager reviews the combined plan. Problems go back only to the specialists they flag, for up to 2 re-plans per round.", font=_font(17), fill=MUTED)
    draw.text((40, 896), "Nothing is final until you approve. If you send it back, the manager re-splits your feedback until you and the manager both agree.", font=_font(17), fill=MUTED)

    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


if __name__ == "__main__":
    # Writes the LangGraph-rendered PNG next to this module:
    #   cd backend && .venv\Scripts\python.exe -m app.services.workflow_diagram
    from pathlib import Path

    from app.graphs.event_workflow import STEPS, build_graph

    compiled = build_graph().compile().get_graph()
    target = Path(__file__).resolve().parent / "workflow-graph.png"
    target.write_bytes(render_workflow_png(compiled.draw_mermaid(), STEPS))
    print(f"Wrote {target}")
