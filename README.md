# EventPilot: Autonomous Event Planning Team

EventPilot is a full-stack multi-agent event-planning application. The React
frontend collects an event brief, presents an event-specific plan, manages
budget revisions and risk actions, and exports the final plan. It also offers
a conversational planner that collects and validates a complete event brief
before using the same generation workflow. The FastAPI
backend runs a LangGraph workflow with MCP-backed specialists, manager review,
one reflection retry, SQLite persistence, and Langfuse tracing.

## Project Structure

    .
    ├── frontend/             React and Vite application
    │   ├── src/components/   Dashboard UI components
    │   ├── src/data/         Frontend demo plan generator
    │   └── .openai/          Existing private Site hosting configuration
    ├── backend/
    │   ├── app/api/          FastAPI route handlers
    │   ├── app/core/         Environment configuration
    │   ├── app/graphs/       LangGraph workflow entry point
    │   ├── app/models/       Pydantic request and response models
    │   └── app/services/     Planning service
    ├── backend/.env.example  Azure OpenAI environment template
    ├── docs/ARCHITECTURE.md   Workflow diagram and design trade-offs
    └── README.md

## Run Locally

Frontend:

    cd frontend
    npm install
    npm run dev

Backend:

    cd backend
    export PATH="$HOME/.local/bin:$PATH"
    uv venv --python 3.11 .venv
    source .venv/bin/activate
    uv pip install --python .venv/bin/python -r requirements.txt
    uvicorn app.main:app --reload --port 8001

The frontend runs at http://127.0.0.1:5173 and backend API documentation is
available at http://127.0.0.1:8001/docs.
Copy backend/.env.example to backend/.env before adding Azure OpenAI
credentials. The API falls back to a deterministic planner when Azure OpenAI
is unavailable.

## Saved Event Workspace

Every saved event brief and its latest generated plan are retained in local
SQLite storage. On refresh, EventPilot loads the most recently created saved
event. Use **Your events** in the sidebar to open another saved event, then
continue editing its brief, revising its budget, previewing its blueprint, or
approving it. Risk decisions and approval status are stored per event in the
browser, so they also survive a refresh on the same browser.

## Conversational Planner

Select **Plan with AI** in the sidebar to create a new event through a guided
conversation. EventPilot asks for event type, name, date, location, attendee
count, budget, and objective. Each step offers common choices plus a custom
answer field. After reviewing the collected brief, select **Generate event
plan** to save the event and run the existing multi-agent workflow.

---

# Original Project Requirements

# Autonomous Event Planning Team: Multi-Agent Event Orchestration System

## 📌 Problem Statement

Planning events such as workshops, conferences, college fests, or meetups requires coordination across logistics, budgeting, scheduling, promotions, and risk management. Decisions made by one team often impact others, making collaboration essential.

Traditional tools assist with isolated tasks, but successful event execution depends on structured coordination between multiple roles working toward a shared objective.

------------------------------------------------------------------------

## 🌍 Context

The Autonomous Event Planning Team simulates an organizing committee where specialized AI agents collaborate under an **Event Manager (Manager Agent)** to design, refine, and finalize a complete event execution plan.

------------------------------------------------------------------------

## 🚧 Key Real-World Challenges

- Event planning involves multiple interdependent tasks.
- Budget, logistics, and promotion decisions influence each other.
- Planning requires iterative refinement and coordination.
- Miscommunication leads to scheduling conflicts or resource issues.
- Final execution demands unified decision synthesis.

------------------------------------------------------------------------

## 🎯 Project Goal

Build an **Autonomous Multi-Agent System** that:

- Breaks event planning into specialized agent roles.
- Coordinates collaboration through hierarchical delegation.
- Uses structured reasoning workflows.
- Applies reflection to refine planning decisions.
- Produces a complete event execution strategy.

------------------------------------------------------------------------

## 🧠 Problem Description

This project focuses on engineering a **Stateful Multi-Agent Event Planning System** that:

- Defines role-based planning responsibilities.
- Models workflows using state machines (LangGraph).
- Enables collaboration between planning agents.
- Applies reflection to improve plans iteratively.
- Synthesizes outputs into a unified event blueprint.
- Optimizes workflow efficiency and coordination.

Example prompts:

- *"Plan a one-day AI workshop for 200 participants."*
- *"Adjust the event plan within a reduced budget."*
- *"Review risks and improve execution readiness."*

------------------------------------------------------------------------

## ⚙️ Functional Requirements

Your system must support:

### 🧩 Role-Based Agents

- Logistics Planning Agent
- Budget & Finance Agent
- Marketing & Promotion Agent
- Schedule Coordination Agent
- Risk & Operations Agent

### 🧭 Manager-Led Delegation

- Event Manager coordinating tasks
- Structured delegation and synthesis logic

### 🔄 Iterative Reasoning

- ReAct or Plan–Act–Check loops
- Reflection and refinement cycles

### 🔗 Multi-Agent Coordination

- Collaboration across planning roles
- Conflict resolution and dependency handling

### 📊 Optimization

- Reduced redundant planning steps
- Improved workflow efficiency and clarity

------------------------------------------------------------------------

## 🧪 Technical Details

### 🧑‍💻 Programming Language

- **Python**

### 🏗️ Core Framework

- **LangGraph**

### 🧰 Libraries & Tools

| Tool / Library | Purpose |
|----------------|---------|
| langgraph | Stateful workflow orchestration |
| langchain | Agent abstractions and tools |
| openai / anthropic | LLM APIs |
| pydantic | Structured outputs |
| fastapi | Backend API (optional) |
| uvicorn | API server |
| dotenv | Environment configuration |

------------------------------------------------------------------------

## 🔐 Environment Variables

| Variable | Purpose |
|-----------|---------|
| OPENAI_API_KEY | LLM authentication |
| ANTHROPIC_API_KEY | Optional LLM provider |
| MODEL_NAME | Selected LLM |
| DEBUG_MODE | Workflow debugging flag |

------------------------------------------------------------------------

## 🏗️ Infrastructure Requirements

- Python environment
- LLM API access
- Optional backend service (FastAPI)
- Local or cloud deployment setup

------------------------------------------------------------------------

## 📚 Sample Inputs

- Event type and objective
- Expected audience size
- Budget constraints
- Venue or timeline preferences

------------------------------------------------------------------------

## 📦 Project Deliverables

### 1️⃣ Functional Multi-Agent System

- Role-based planning agents
- Manager-led coordination
- Reflection loop integration
- End-to-end event planning workflow

### 2️⃣ Architecture & Workflow Design

- State machine diagram
- Delegation logic documentation
- Planning workflow explanation

### 3️⃣ Optimization & Refactoring

- Modular code structure
- Performance improvement analysis
- Error handling strategy

### 4️⃣ Demonstration

- Event planning workflow walkthrough
- Iterative refinement example

### 5️⃣ Documentation

- Architecture diagram
- Agent role definitions
- Workflow explanation
- Design trade-offs summary

------------------------------------------------------------------------

## 🧪 Evaluation Criteria

The system will be evaluated on:

- Multi-agent coordination quality
- Delegation effectiveness
- Reflection and self-correction capability
- Workflow clarity and state modeling
- System optimization and performance
- Code quality and modularity
- Documentation clarity

------------------------------------------------------------------------

## 🚀 Getting Started

1. Define event planning roles and responsibilities
2. Design workflow using LangGraph
3. Implement base agents
4. Add manager delegation logic
5. Integrate reflection loop
6. Optimize workflow
7. Test with multiple event scenarios
8. Document architecture and reasoning flow

> **Note:** Focus on coordinated planning and decision orchestration rather than generating a static event checklist.
