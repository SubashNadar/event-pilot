"""Generate editable reviewer materials for the EventPilot course project."""
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.dml.color import RGBColor as PPTColor
from pptx.util import Inches as PInches, Pt as PPt

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs"
OUT.mkdir(exist_ok=True)
PPT_OUT = OUT / "EventPilot_Reviewer_Presentation.pptx"
DOC_OUT = OUT / "EventPilot_Reviewer_Report.docx"

NAVY = "173B37"
TEAL = "167C75"
MINT = "E9F4EF"
LIME = "D8F06A"
INK = "17312E"
MUTED = "5E726E"
WARM = "FFFDF8"
ORANGE = "D97732"
LINE = "D7E4E0"
WHITE = "FFFFFF"

def rgb(value):
    return PPTColor.from_string(value)

def doc_rgb(value):
    return RGBColor.from_string(value)

def set_cell_shading(cell, fill):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), fill)
    tc_pr.append(shd)

def set_cell_border(cell, color=LINE):
    tc_pr = cell._tc.get_or_add_tcPr()
    borders = tc_pr.first_child_found_in("w:tcBorders")
    if borders is None:
        borders = OxmlElement("w:tcBorders")
        tc_pr.append(borders)
    for edge in ("top", "left", "bottom", "right"):
        tag = qn(f"w:{edge}")
        element = borders.find(tag)
        if element is None:
            element = OxmlElement(f"w:{edge}")
            borders.append(element)
        element.set(qn("w:val"), "single")
        element.set(qn("w:sz"), "6")
        element.set(qn("w:color"), color)

def add_ppt_text(slide, text, x, y, w, h, size=18, color=INK, bold=False,
                 font="Aptos", align=PP_ALIGN.LEFT, valign=MSO_ANCHOR.TOP):
    box = slide.shapes.add_textbox(PInches(x), PInches(y), PInches(w), PInches(h))
    tf = box.text_frame
    tf.clear(); tf.word_wrap = True; tf.vertical_anchor = valign
    p = tf.paragraphs[0]; p.alignment = align
    run = p.add_run(); run.text = text
    run.font.name = font; run.font.size = PPt(size); run.font.bold = bold; run.font.color.rgb = rgb(color)
    return box

def rect(slide, x, y, w, h, fill, line=None, radius=False):
    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE,
                                   PInches(x), PInches(y), PInches(w), PInches(h))
    shape.fill.solid(); shape.fill.fore_color.rgb = rgb(fill)
    shape.line.color.rgb = rgb(line or fill)
    return shape

def base_slide(prs, eyebrow, title, subtitle=""):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    bg = slide.background.fill; bg.solid(); bg.fore_color.rgb = rgb(WARM)
    rect(slide, 0, 0, 13.333, .12, TEAL)
    add_ppt_text(slide, "EVENTPILOT", .62, .32, 2.2, .25, 10, TEAL, True)
    add_ppt_text(slide, eyebrow.upper(), .62, .78, 8.5, .28, 10, MUTED, True, font="Aptos Mono")
    add_ppt_text(slide, title, .62, 1.08, 12.0, .6, 28, INK, True, font="Aptos Display")
    if subtitle:
        add_ppt_text(slide, subtitle, .62, 1.75, 11.7, .5, 13, MUTED)
    add_ppt_text(slide, f"Autonomous Event Planning Team  |  Reviewer Presentation", .62, 7.18, 8, .18, 8, MUTED)
    add_ppt_text(slide, str(len(prs.slides)), 12.25, 7.15, .4, .2, 8, MUTED, align=PP_ALIGN.RIGHT)
    return slide

def card(slide, x, y, w, h, label, body, accent=TEAL):
    rect(slide, x, y, w, h, WHITE, LINE, True)
    rect(slide, x, y, .07, h, accent, accent, True)
    add_ppt_text(slide, label.upper(), x+.22, y+.18, w-.35, .22, 9, accent, True, font="Aptos Mono")
    add_ppt_text(slide, body, x+.22, y+.52, w-.42, h-.64, 13, INK, False)

def node(slide, label, x, y, w=1.55, h=.55, fill=MINT, color=TEAL, sub=""):
    rect(slide, x, y, w, h, fill, color, True)
    add_ppt_text(slide, label, x+.08, y+.12, w-.16, .2, 10, INK, True, align=PP_ALIGN.CENTER)
    if sub:
        add_ppt_text(slide, sub, x+.08, y+.31, w-.16, .15, 7, MUTED, align=PP_ALIGN.CENTER)

def line(slide, x1, y1, x2, y2, color=TEAL):
    connector = slide.shapes.add_connector(1, PInches(x1), PInches(y1), PInches(x2), PInches(y2))
    connector.line.color.rgb = rgb(color); connector.line.width = PPt(1.2)

def build_presentation():
    prs = Presentation(); prs.slide_width = PInches(13.333); prs.slide_height = PInches(7.5)
    # 1 title
    slide = prs.slides.add_slide(prs.slide_layouts[6]); slide.background.fill.solid(); slide.background.fill.fore_color.rgb = rgb(NAVY)
    rect(slide, .65, .8, 1.1, 1.1, LIME, LIME, True)
    add_ppt_text(slide, "EP", .65, 1.08, 1.1, .3, 25, NAVY, True, align=PP_ALIGN.CENTER)
    add_ppt_text(slide, "EventPilot", .65, 2.35, 8, .65, 36, WHITE, True, font="Aptos Display")
    add_ppt_text(slide, "Autonomous Event Planning Team", .65, 3.07, 9, .45, 20, LIME, True)
    add_ppt_text(slide, "A manager-led multi-agent system for creating reviewable, traceable event plans.", .65, 3.7, 9.2, .48, 16, "D8E7E2")
    rect(slide, .65, 5.28, 4.45, .8, TEAL, TEAL, True)
    add_ppt_text(slide, "React  •  FastAPI  •  LangGraph  •  MCP  •  Azure OpenAI  •  Langfuse", .9, 5.56, 4.0, .2, 9, WHITE, True, align=PP_ALIGN.CENTER)
    add_ppt_text(slide, "Course 4 End Project  |  Reviewer Presentation", .65, 6.8, 7, .25, 10, "B5CBC5")
    # 2 problem
    slide = base_slide(prs, "01 / Context", "Why EventPilot?", "Event planning is a coordination problem, not a single-answer problem.")
    card(slide, .65, 2.55, 3.85, 2.55, "Planning pain", "A brief must become aligned decisions about venue, budget, schedule, guests, communication, and operational risk.", ORANGE)
    card(slide, 4.74, 2.55, 3.85, 2.55, "AI risk", "A generic chatbot can produce text, but cannot clearly show delegation, evidence, review checkpoints, or ownership.", TEAL)
    card(slide, 8.83, 2.55, 3.85, 2.55, "Project goal", "Create a practical plan through specialist collaboration, then make every important step inspectable by a reviewer.", "6A9E4E")
    # 3 solution
    slide = base_slide(prs, "02 / Solution", "One brief becomes a governed planning workspace", "The interface turns multi-agent output into actions a planner can review, revise, approve, and export.")
    for i, (t, b) in enumerate([("1. Capture", "Conversational brief: event, date, location, attendees, budget, objective"), ("2. Coordinate", "Specialists work in parallel through a shared LangGraph state"), ("3. Validate", "Manager synthesis and bounded review/reflection protect constraints"), ("4. Decide", "Human reviews risks, revises budget, approves, and exports")]):
        x = .65 + i*3.08; rect(slide, x, 2.75, 2.62, 2.15, WHITE, LINE, True); rect(slide, x+.2, 2.98, .44, .44, LIME, LIME, True)
        add_ppt_text(slide, str(i+1), x+.2, 3.1, .44, .15, 11, NAVY, True, align=PP_ALIGN.CENTER)
        add_ppt_text(slide, t, x+.2, 3.62, 2.15, .25, 14, INK, True)
        add_ppt_text(slide, b, x+.2, 4.02, 2.16, .65, 10, MUTED)
    # 4 architecture
    slide = base_slide(prs, "03 / Architecture", "A clear separation of experience, orchestration, tools, and evidence")
    layers = [("React workspace", "Brief, chat, plan sections, risks, approval, PDF export", "DFF0EA"), ("FastAPI service", "Typed APIs, persistence, streaming run state", "E9F4EF"), ("LangGraph workflow", "Parallel specialists → manager → review → bounded reflection", "DFF0EA"), ("MCP and integrations", "Controlled planning tools and structured tool results", "E9F4EF"), ("Evidence", "SQLite saved events and Langfuse traces", "DFF0EA")]
    for i,(a,b,c) in enumerate(layers):
        y=2.32+i*.78; rect(slide, .78,y,7.25,.58,c,TEAL,True); add_ppt_text(slide,a,.98,y+.16,2.2,.18,11,TEAL,True); add_ppt_text(slide,b,3.25,y+.16,4.52,.18,10,INK)
    card(slide, 8.45, 2.35, 4.1, 3.55, "Design principle", "The model is not the whole application. Typed state, tool boundaries, validation, persistence, approval, and tracing make the output reviewable.", ORANGE)
    # 5 graph
    slide = base_slide(prs, "04 / LangGraph", "A state machine for coordinated planning", "The Planning Run workflow graph visualizes this orchestration in the UI.")
    node(slide,"Event brief",.7,3.25,1.45,.62,LIME,NAVY,"shared state")
    for i,label in enumerate(["Logistics","Finance","Schedule","Requirements","Marketing","Risk ops"]):
        x=2.65+(i%3)*1.65; y=2.55+(i//3)*1.05; node(slide,label,x,y,1.38,.55,MINT,TEAL,"MCP-assisted"); line(slide,2.15,3.56,x,y+.27)
    node(slide,"Event manager",7.85,3.25,1.6,.62,"DFF0EA",TEAL,"synthesis");
    for y in (2.82,3.87): line(slide,7.6,y,7.85,3.56)
    node(slide,"Review",10.05,3.25,1.25,.62,"FFF1E7",ORANGE,"checks")
    node(slide,"Final plan",11.72,3.25,1.05,.62,LIME,NAVY,"or retry")
    line(slide,9.45,3.56,10.05,3.56); line(slide,11.3,3.56,11.72,3.56)
    add_ppt_text(slide,"If validation detects a budget, arithmetic, or time-format issue, the graph permits one reflection pass with review feedback.",.85,5.35,11.4,.4,12,MUTED,align=PP_ALIGN.CENTER)
    # 6 agents
    slide = base_slide(prs, "05 / Agent team", "Specialists own a discipline; the manager owns the combined decision")
    agents=[("Logistics","Venue capacity, accessibility, travel"),("Budget & Finance","Allocation, guardrails, contingency"),("Schedule","Agenda sequencing and timing checks"),("Requirements","Operational needs by event type and scale"),("Marketing","Guest communication and RSVP readiness"),("Risk & Operations","Crowd flow, fallback and monitoring actions")]
    for i,(a,b) in enumerate(agents): card(slide,.7+(i%3)*4.1,2.35+(i//3)*1.6,3.72,1.25,a,b,TEAL if i!=5 else ORANGE)
    add_ppt_text(slide,"Event Manager: combines bounded specialist reports into one structured plan. Review node: checks the outcome before it reaches the human decision point.",.8,5.82,11.7,.45,13,INK,True,align=PP_ALIGN.CENTER)
    # 7 MCP
    slide = base_slide(prs, "06 / MCP", "Tools ground specialist work in controlled planning evidence", "MCP turns a tool call into a structured, traceable part of the workflow.")
    tools=["Venue search","Budget validation","Schedule conflict check","Event requirements","Marketing readiness","Operational risk assessment"]
    for i,t in enumerate(tools):
        x=.75+(i%3)*4.13; y=2.52+(i//3)*1.14; rect(slide,x,y,3.68,.78,WHITE,LINE,True); rect(slide,x+.18,y+.19,.34,.34,LIME,LIME,True); add_ppt_text(slide,"✓",x+.18,y+.25,.34,.15,10,NAVY,True,align=PP_ALIGN.CENTER); add_ppt_text(slide,t,x+.68,y+.25,2.74,.18,12,INK,True)
    card(slide,.78,5.15,11.8,.82,"Safety boundary","The current MCP tools are deterministic and read-only. Live Maps, email, calendar, and write actions are deliberately deferred until credentials and human approval controls are in place.",ORANGE)
    # 8 frontend
    slide = base_slide(prs, "07 / User experience", "A planning workspace designed for real decisions, not just generated prose")
    steps=[("Plan with AI","Capture a conversational brief and maintain a planning conversation."),("Overview","See planning status, budget, confidence, readiness, and open risks."),("Workspace","Inspect logistics, budget, schedule, marketing, and risk recommendations."),("Planning Run","View timeline or workflow graph; inspect tools, recovery, and trace context."),("Approval & PDF","Preview a draft at any time; allow final export only after explicit approval.")]
    for i,(a,b) in enumerate(steps):
        y=2.22+i*.72; rect(slide,.82,y,.55,.45,LIME,LIME,True); add_ppt_text(slide,str(i+1),.82,y+.14,.55,.12,10,NAVY,True,align=PP_ALIGN.CENTER); add_ppt_text(slide,a,1.63,y+.08,2.3,.18,12,TEAL,True); add_ppt_text(slide,b,4.0,y+.08,7.7,.35,10,INK)
    # 9 quality governance
    slide = base_slide(prs, "08 / Quality and control", "Plan - Act - Check is implemented as a bounded, reviewable loop")
    for i,(a,b,c) in enumerate([("Plan","Manager creates a typed, structured plan.",TEAL),("Act","Specialists use bounded MCP tools and share reports.","6A9E4E"),("Check","Review verifies budget limit, arithmetic, agenda format, and risk count.",ORANGE),("Refine","One retry is permitted with specific review feedback.",TEAL)]):
        x=.72+i*3.12; rect(slide,x,2.7,2.62,1.8,WHITE,LINE,True); rect(slide,x+.18,2.95,.44,.44,c,c,True); add_ppt_text(slide,str(i+1),x+.18,3.08,.44,.12,11,WHITE,True,align=PP_ALIGN.CENTER); add_ppt_text(slide,a,x+.18,3.58,2.1,.2,14,INK,True); add_ppt_text(slide,b,x+.18,3.92,2.1,.42,10,MUTED)
    add_ppt_text(slide,"Human approval remains the final control before an approved PDF can be exported.",.72,5.35,11.8,.3,14,TEAL,True,align=PP_ALIGN.CENTER)
    # 10 observability
    slide = base_slide(prs, "09 / Observability", "Langfuse makes the AI workflow visible without exposing private reasoning")
    card(slide,.72,2.45,3.65,2.5,"What a reviewer sees","Plan-generation and budget-revision traces, Azure generation, structured output, latency, tokens, and cost.",TEAL)
    card(slide,4.83,2.45,3.65,2.5,"What a tool span shows","Tool name, input, result summary, timing, and failures for MCP-backed planning calls.","6A9E4E")
    card(slide,8.94,2.45,3.65,2.5,"Why it matters","A reviewer can connect the user brief to the workflow, AI generation, tool use, and final plan evidence.",ORANGE)
    # 11 demo
    slide = base_slide(prs, "10 / Live demo", "A concise 8-minute reviewer walkthrough", "Suggested scenario: a 350-guest wedding reception in Whitefield, Bengaluru with a ₹12,00,000 budget.")
    demo=[("1 min","Open Plan with AI; enter the brief and identify the captured requirements."),("2 min","Generate the plan; show the Planning Run timeline and Workflow graph."),("2 min","Open the workspace: venue, budget, agenda, marketing, and risk actions."),("1 min","Reduce budget by 20%; show revised values and the new trace."),("1 min","Open Langfuse: generation, model, tool observations, latency and cost."),("1 min","Preview draft PDF; resolve decisions, approve, and export the final PDF.")]
    for i,(time,text) in enumerate(demo):
        y=2.25+i*.56; add_ppt_text(slide,time,.85,y, .7,.2,10,ORANGE,True,font="Aptos Mono"); rect(slide,1.7,y+.03,10.45,.34,WHITE,LINE,True); add_ppt_text(slide,text,1.92,y+.11,10.0,.15,10,INK)
    # 12 requirements
    slide = base_slide(prs, "11 / Delivery status", "The README's core course requirements are implemented")
    rows=[("Multi-agent roles","Six specialist nodes plus event manager"),("State-machine workflow","Compiled LangGraph fan-out, convergence, review and routing"),("Reflection","One bounded retry using review feedback"),("MCP","Internal streamable HTTP server, tools, resource, client and fallback"),("Observability","Langfuse generation, Azure and MCP tool observations"),("Persistence and UI","SQLite saved plans; React workspace, approvals and PDF export")]
    for i,(a,b) in enumerate(rows):
        y=2.22+i*.55; rect(slide,.74,y,.72,.34,LIME,LIME,True); add_ppt_text(slide,"DONE",.74,y+.11,.72,.12,7,NAVY,True,align=PP_ALIGN.CENTER); add_ppt_text(slide,a,1.72,y+.09,2.45,.16,11,TEAL,True); add_ppt_text(slide,b,4.25,y+.09,7.75,.25,10,INK)
    # 13 limitations
    slide = base_slide(prs, "12 / Scope", "Deliberate course-demo boundaries and production next steps")
    card(slide,.72,2.4,3.65,2.75,"Current demo scope","SQLite is suitable for a local course demonstration. MCP tools are deterministic and read-only. Approval is required before final export.",TEAL)
    card(slide,4.83,2.4,3.65,2.75,"Production enhancements","Hosted database, authentication, multi-user roles, live vendor inventory, Map/Calendar/Email integrations, and broader evaluation datasets.","6A9E4E")
    card(slide,8.94,2.4,3.65,2.75,"Why this is credible","The system prioritizes reliable orchestration and inspectability over claiming unsupported real-world booking or autonomous write actions.",ORANGE)
    # 14 close
    slide = base_slide(prs, "13 / Close", "EventPilot demonstrates autonomous coordination with human accountability")
    rect(slide,.72,2.35,11.85,2.2,NAVY,NAVY,True)
    add_ppt_text(slide,"From one event brief to an inspectable, approved plan",1.05,2.85,11.2,.35,23,WHITE,True,font="Aptos Display",align=PP_ALIGN.CENTER)
    add_ppt_text(slide,"LangGraph coordinates the team. MCP provides controlled evidence. Langfuse explains the run. The planner retains the final decision.",1.05,3.52,11.2,.35,13,"D8E7E2",align=PP_ALIGN.CENTER)
    add_ppt_text(slide,"Questions and live demonstration",.72,5.35,11.85,.35,18,TEAL,True,align=PP_ALIGN.CENTER)
    # 15 thank you
    slide = prs.slides.add_slide(prs.slide_layouts[6]); slide.background.fill.solid(); slide.background.fill.fore_color.rgb = rgb(NAVY)
    rect(slide, 0, 0, 13.333, .12, LIME)
    rect(slide, 5.82, 1.55, 1.68, 1.68, LIME, LIME, True)
    add_ppt_text(slide, "EP", 5.82, 2.05, 1.68, .32, 26, NAVY, True, align=PP_ALIGN.CENTER)
    add_ppt_text(slide, "Thank you", 1.0, 3.8, 11.35, .55, 34, WHITE, True, font="Aptos Display", align=PP_ALIGN.CENTER)
    add_ppt_text(slide, "Questions, feedback, and live demonstration", 1.0, 4.53, 11.35, .28, 15, LIME, True, align=PP_ALIGN.CENTER)
    add_ppt_text(slide, "EventPilot | Autonomous Event Planning Team", 1.0, 6.62, 11.35, .22, 10, "B5CBC5", align=PP_ALIGN.CENTER)
    prs.save(PPT_OUT)

def doc_heading(doc, text, level=1):
    p=doc.add_heading(text, level=level); p.style.font.name="Aptos Display"; p.style.font.color.rgb=doc_rgb(INK); return p

def doc_para(doc, text, bold_prefix=None):
    p=doc.add_paragraph(); p.paragraph_format.space_after=Pt(7)
    if bold_prefix and text.startswith(bold_prefix):
        r=p.add_run(bold_prefix); r.bold=True; r.font.color.rgb=doc_rgb(TEAL); p.add_run(text[len(bold_prefix):])
    else: p.add_run(text)
    for r in p.runs: r.font.name="Aptos"; r.font.size=Pt(10.5); r.font.color.rgb=doc_rgb(INK)
    return p

def bullet(doc, text):
    p=doc.add_paragraph(style="List Bullet"); p.add_run(text)
    for r in p.runs: r.font.name="Aptos"; r.font.size=Pt(10.5); r.font.color.rgb=doc_rgb(INK)

def table(doc, headers, rows, widths=None):
    t=doc.add_table(rows=1, cols=len(headers)); t.style="Table Grid"; t.autofit=False
    for i,h in enumerate(headers):
        c=t.rows[0].cells[i]; c.text=h; set_cell_shading(c,NAVY); set_cell_border(c,NAVY); c.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
        for r in c.paragraphs[0].runs: r.font.bold=True; r.font.color.rgb=doc_rgb(WHITE); r.font.size=Pt(9)
        if widths: c.width=Inches(widths[i])
    for ri,row in enumerate(rows):
        cells=t.add_row().cells
        for i,value in enumerate(row):
            cells[i].text=value; set_cell_shading(cells[i], WARM if ri%2==0 else MINT); set_cell_border(cells[i]); cells[i].vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.TOP
            if widths: cells[i].width=Inches(widths[i])
            for p in cells[i].paragraphs:
                for r in p.runs: r.font.name="Aptos"; r.font.size=Pt(8.8); r.font.color.rgb=doc_rgb(INK)
    doc.add_paragraph().paragraph_format.space_after=Pt(2)
    return t

def build_document():
    doc=Document(); sec=doc.sections[0]; sec.top_margin=Inches(.7); sec.bottom_margin=Inches(.7); sec.left_margin=Inches(.78); sec.right_margin=Inches(.78)
    styles=doc.styles; styles['Normal'].font.name='Aptos'; styles['Normal'].font.size=Pt(10.5)
    # Cover
    p=doc.add_paragraph(); p.paragraph_format.space_before=Pt(120); p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    r=p.add_run('EVENTPILOT'); r.bold=True; r.font.name='Aptos Display'; r.font.size=Pt(20); r.font.color.rgb=doc_rgb(TEAL)
    p=doc.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER; r=p.add_run('Autonomous Event Planning Team'); r.bold=True; r.font.name='Aptos Display'; r.font.size=Pt(31); r.font.color.rgb=doc_rgb(INK)
    p=doc.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER; r=p.add_run('Reviewer Project Report'); r.font.size=Pt(17); r.font.color.rgb=doc_rgb(MUTED)
    p=doc.add_paragraph(); p.paragraph_format.space_before=Pt(40); p.alignment=WD_ALIGN_PARAGRAPH.CENTER; r=p.add_run('React  |  FastAPI  |  LangGraph  |  MCP  |  Azure OpenAI  |  Langfuse'); r.bold=True; r.font.size=Pt(11); r.font.color.rgb=doc_rgb(TEAL)
    p=doc.add_paragraph(); p.paragraph_format.space_before=Pt(160); p.alignment=WD_ALIGN_PARAGRAPH.CENTER; r=p.add_run('Course 4 End Project\nPrepared for project review'); r.font.size=Pt(11); r.font.color.rgb=doc_rgb(MUTED)
    doc.add_page_break()
    doc_heading(doc,'Executive Summary',0)
    doc_para(doc,'EventPilot is a manager-led autonomous event-planning application. It transforms a short event brief into a structured, reviewable plan covering venue logistics, budget, schedule, requirements, marketing readiness, and operational risks. The project demonstrates multi-agent coordination rather than a single unstructured AI response.')
    doc_para(doc,'The implementation combines a React planning workspace with a FastAPI service, a compiled LangGraph workflow, controlled MCP planning tools, Azure OpenAI structured generation, SQLite persistence, and Langfuse tracing. The outcome is deliberately human-governed: users review recommendations, choose risk actions, approve the plan, and only then export the final PDF.')
    table(doc,['Reviewer question','Answer'],[
        ('What problem does it solve?','It coordinates the cross-functional decisions required to turn an event brief into an actionable plan.'),
        ('Why is it multi-agent?','Independent specialist roles create bounded reports in parallel; an Event Manager synthesizes their shared state.'),
        ('How is quality controlled?','A review node validates basic plan constraints and permits only one feedback-driven reflection retry.'),
        ('How can it be inspected?','Planning runs, AI generations, and MCP tool calls are visible in Langfuse and in the Planning Run UI.'),
        ('Who has final authority?','The human planner controls risk decisions, approval, and final PDF export.')], [2.1,4.9])
    doc_heading(doc,'1. Project Objective',1)
    doc_para(doc,'The course objective is to demonstrate autonomous multi-agent orchestration using state-machine concepts, specialist delegation, plan-act-check loops, reflection, and observable AI operations. EventPilot applies these concepts to a familiar operational domain: event planning.')
    bullet(doc,'Convert a concise event brief into a complete, structured planning workspace.')
    bullet(doc,'Coordinate distinct specialist responsibilities through a shared state graph.')
    bullet(doc,'Use MCP tools for controlled planning evidence and reliable local demonstrations.')
    bullet(doc,'Validate important plan constraints before human review.')
    bullet(doc,'Make model and tool activity traceable through Langfuse.')
    doc_heading(doc,'2. Solution Overview',1)
    table(doc,['Layer','Implementation','Purpose'],[
        ('Experience','React frontend','Conversational brief capture, saved plans, workspace tabs, risk actions, approval and PDF export.'),
        ('Application service','FastAPI','Typed request/response APIs, planning-run events, retrieval, revisions and persistence.'),
        ('Orchestration','LangGraph','Compiled state graph for parallel specialists, synthesis, review and reflection routing.'),
        ('AI generation','Azure OpenAI with Pydantic output','Creates structured event plans rather than free-form text.'),
        ('Tool boundary','MCP server and client','Provides controlled, structured planning tools and a venue resource.'),
        ('Evidence','Langfuse and SQLite','Records trace metadata and retains saved event briefs and latest plans.')], [1.25,2.1,3.65])
    doc_heading(doc,'3. LangGraph Workflow',1)
    doc_para(doc,'LangGraph is the project’s workflow controller. It keeps a typed shared state and determines which node executes next. This differs from simply calling a model multiple times: the graph explicitly encodes parallel work, convergence, validation, and the bounded refinement path.')
    table(doc,['Stage','Nodes / behavior','Reviewer value'],[
        ('Shared input','Event brief becomes the typed workflow state.','Every specialist starts from the same confirmed facts.'),
        ('Parallel delegation','Logistics, Finance, Schedule, Requirements, Marketing, and Risk & Operations run independently.','Clear responsibility boundaries and efficient orchestration.'),
        ('Manager synthesis','Event Manager combines specialist reports into a structured final-plan candidate.','One coherent output instead of isolated recommendations.'),
        ('Review','Budget total, budget arithmetic, agenda format, and risk count are checked.','Basic constraints are verified before final review.'),
        ('Reflection','If review fails, one retry receives targeted feedback; otherwise the plan completes.','The loop is controlled rather than endlessly self-correcting.'),
        ('Human review','User resolves decisions, approves, then exports.','The application does not autonomously commit real-world actions.')], [1.2,3.2,2.6])
    doc_para(doc,'In the UI, the Planning Run offers both a chronological Timeline and a Workflow graph. This gives reviewers a visual explanation of the LangGraph state machine while still allowing them to open a particular step and inspect tool, validation, recovery, and trace details.')
    doc_heading(doc,'4. Specialist Team and MCP Evidence',1)
    table(doc,['Specialist','Primary responsibility','MCP-assisted evidence'],[
        ('Logistics','Venue suitability, capacity, local accessibility and travel context.','Venue search'),('Budget & Finance','Budget allocation, contingency and budget guardrails.','Budget validation'),('Schedule','12-hour agenda and scheduling conflicts.','Schedule conflict check'),('Requirements','Event-scale operational needs.','Event requirements'),('Marketing','Guest communication and RSVP readiness.','Marketing readiness'),('Risk & Operations','Practical risks, monitoring and fallback actions.','Operational risk assessment')], [1.5,3.35,2.15])
    doc_para(doc,'MCP tools return structured data rather than unbounded external browsing. The current tools are deterministic and read-only to keep the course demonstration reliable and safe. The system also records tool input, result summaries, timings, and errors for each relevant trace.')
    doc_heading(doc,'5. Frontend Planning Experience',1)
    table(doc,['Workflow moment','User experience'],[
        ('Start a plan','Plan with AI captures the brief in a conversational flow and supports recent planning conversation history.'),
        ('Inspect a plan','Overview summarizes readiness, budget forecast, confidence and open risks. Workspace tabs present discipline-specific decisions.'),
        ('Change a plan','A budget reduction creates a revision and refreshes planning outputs while keeping the revised budget traceable.'),
        ('Manage risk','Users can monitor a risk or record a fallback action; these decisions are visible in the plan state.'),
        ('Review the run','Timeline and Workflow graph explain which agents ran, which tools were called, and whether checks passed.'),
        ('Publish safely','Draft PDF preview is available before approval. Final export remains disabled until the human approves the plan.')], [1.55,5.45])
    doc_heading(doc,'6. Observability with Langfuse',1)
    doc_para(doc,'Langfuse provides the operational evidence for a planning run. A reviewer can open the newest eventpilot-plan-generation trace to see the event-specific prompt, Azure model generation, typed structured output, latency, token count, and cost. MCP calls appear as observations with structured input and output summaries.')
    doc_para(doc,'A budget change creates a separate eventpilot-budget-revision trace. This is important because it demonstrates that revisions are not merely frontend calculations: the updated budget context is sent through an observable backend operation and the revised plan is persisted.')
    doc_heading(doc,'7. Recommended Live Demonstration',1)
    table(doc,['Time','Show','Explain'],[
        ('0:00-1:00','Plan with AI','Enter a wedding-reception brief: Whitefield, Bengaluru; 350 attendees; ₹12,00,000 budget.'),
        ('1:00-2:30','Planning Run','Show the Timeline, then switch to Workflow graph. Explain fan-out, manager convergence, review, and bounded reflection.'),
        ('2:30-4:30','Workspace','Open logistics, budget, schedule, marketing and risks. Point to a concrete venue, six budget lines, 12-hour agenda and actions.'),
        ('4:30-5:30','Budget revision','Reduce the budget by 20%; show the changed allocation and contingency-aware forecast.'),
        ('5:30-6:30','Langfuse','Open the newest generation/revision trace and one MCP observation.'),
        ('6:30-8:00','Approval and PDF','Preview the draft, record/resolve decisions as needed, approve, and export the final event blueprint.')], [0.85,1.75,4.4])
    doc_heading(doc,'8. Requirements Traceability',1)
    table(doc,['README/course requirement','Implemented evidence','Status'],[
        ('Stateful agent workflow','Compiled LangGraph state, explicit nodes and routing.','Complete'),('Multi-agent delegation','Six specialist roles fan out and converge through the Event Manager.','Complete'),('Plan-Act-Check loop','Generation, tool-assisted specialist work, manager synthesis, and review node.','Complete'),('Reflection','One bounded retry with review feedback.','Complete'),('MCP integration','Streamable HTTP MCP server, client, controlled tools and venue resource.','Complete'),('Traceability','Langfuse plan, Azure and MCP tool observations.','Complete'),('Frontend workflow','React planning chat, workspace, risk actions, approval and PDF flow.','Complete'),('Persistence','SQLite stores saved briefs and latest plans across backend restarts.','Complete')], [2.1,3.65,.85])
    doc_heading(doc,'9. Scope Boundaries and Next Steps',1)
    table(doc,['Deliberate boundary','Reason','Production next step'],[
        ('SQLite persistence','Appropriate for local course demonstration; not intended for concurrent multi-user production use.','Hosted relational database, tenant isolation and backups.'),('Read-only deterministic MCP tools','Avoids external API cost, credential management and write-action risk during the demo.','Vendor inventory, Maps, calendar, email and payments with explicit user approval.'),('No authentication in current demo','Keeps the course flow focused on agentic planning concepts.','Role-based login, secure sessions and audit permissions.'),('Focused validation','Checks core structural constraints; it is not a full evaluation framework.','Dataset-based evaluations, regression tests and human feedback scoring.')], [1.7,2.55,2.35])
    doc_heading(doc,'10. Reviewer Takeaway',1)
    doc_para(doc,'EventPilot demonstrates the full path from user intent to governed AI output: a shared event brief is delegated to specialists, controlled tools provide structured evidence, LangGraph coordinates synthesis and review, Langfuse exposes the run, and a human retains approval authority. The system is intentionally scoped as a dependable course demonstration while keeping a clear path to production hardening.')
    doc_heading(doc,'Appendix A: Local Run Commands',1)
    doc_para(doc,'Run these in separate terminals from the repository root. Environment secrets remain in local .env files and must not be committed.')
    for cmd in ['cd backend && source .venv/bin/activate && python -m app.mcp.server','cd backend && source .venv/bin/activate && uvicorn app.main:app --reload --port 8001','cd frontend && npm run dev']:
        p=doc.add_paragraph(); p.paragraph_format.left_indent=Inches(.2); r=p.add_run(cmd); r.font.name='Aptos Mono'; r.font.size=Pt(9); r.font.color.rgb=doc_rgb(TEAL)
    # Footer
    for section in doc.sections:
        footer=section.footer.paragraphs[0]; footer.alignment=WD_ALIGN_PARAGRAPH.CENTER; r=footer.add_run('EventPilot | Autonomous Event Planning Team | Reviewer Report'); r.font.size=Pt(8); r.font.color.rgb=doc_rgb(MUTED)
    doc.save(DOC_OUT)

if __name__ == '__main__':
    build_presentation(); build_document()
    print(PPT_OUT)
    print(DOC_OUT)
