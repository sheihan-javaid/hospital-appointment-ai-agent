# ![GitHub license](https://img.shields.io/github/license/sheihan-javaid/hospital-appointment-ai-agent) ![GitHub repo stars](https://img.shields.io/github/stars/sheihan-javaid/hospital-appointment-ai-agent?style=social) ![GitHub forks](https://img.shields.io/github/forks/sheihan-javaid/hospital-appointment-ai-agent?style=social) ![Python](https://img.shields.io/badge/python-3.11%2B-blue?logo=python) ![FastAPI](https://img.shields.io/badge/FastAPI-✨-informational?logo=fastapi)

# 🏥 Hospital Appointment AI Agent

An end-to-end **Voice AI-powered hospital appointment booking system** that lets users book, reschedule, and cancel appointments through natural conversation.

This project combines **conversational AI, FastAPI backend engineering, and intelligent scheduling logic** to simulate a real-world healthcare assistant.

---

## 🚀 Overview

The Hospital Appointment AI Agent enables users to interact with a hospital system using natural language or voice. It extracts intent, understands context, and performs actions like booking, rescheduling, and cancelling appointments through a structured backend system.

The goal is to build a **real-world deployable AI system**, not just a demo.

---

## 🧠 Key Features

- 🎙️ Voice/Text conversational interface
- 📅 Smart date & time understanding (e.g., “tomorrow morning”, “next Monday”)
- 🔁 Full appointment lifecycle (book, reschedule, cancel)
- 🏥 Doctor & specialty-based booking
- ⚙️ FastAPI backend for scheduling and logic handling (vapi HTTP service)
- 🔗 End-to-end AI + backend integration

---

## 🏗️ System Architecture

User (Voice/Text)
	↓
Conversational AI Agent
	↓
Intent & Entity Extraction
	↓
FastAPI Backend (vapi)
	↓
Scheduling Logic / Database
	↓
Response to User

---

## 🛠️ Tech Stack

- Python
- FastAPI (vapi HTTP service)
- LLM-based conversational layer (local or remote)
- REST APIs
- SQLite / PostgreSQL (optional)

---

## 📂 Project Structure

hospital-ai-agent/
│── main.py
│── app.py (optional)
│── vapi.py (FastAPI app)
│── database.py
│── services/
│   ├── time_parser.py
│   ├── specialty_normalizer.py
│   └── scheduling.py
│── models/
│── routes/
│── utils/
│── requirements.txt
│── README.md

---

## ⚡ Getting Started

1. Clone the repository

```bash
git clone https://github.com/sheihan-javaid/hospital-appointment-ai-agent
cd hospital-appointment-ai-agent
```

2. Create and activate a Python virtual environment

```bash
python -m venv .venv
source .venv/bin/activate
```

3. Install dependencies

```bash
pip install -r requirements.txt
```

4. Start the FastAPI (vapi) service

If the FastAPI app is exported as `main:app`:

```bash
uvicorn main:app --reload --port 8000
```

Or, if the app object lives in `app.py`:

```bash
uvicorn app:app --reload --port 8000
```

5. Try the API (example)

```bash
curl http://localhost:8000/health

curl -s -X POST http://localhost:8000/extract \
  -H "Content-Type: application/json" \
  -d '{"text":"Book an appointment with cardiology next Tuesday at 10am"}'
```

---

## User Scenarios (examples)

- "I need to see a cardiologist next week" → Agent asks details, suggests slots, completes booking.
- "Reschedule my ENT appointment from Monday to Thursday morning" → Agent finds appointment, proposes options, confirms.
- "Cancel my follow-up with Dr. Smith" → Agent cancels and confirms.

---

## Privacy & Safety

- This project is intended to run locally. Avoid sending PHI to third-party services unless explicitly authorized.
- Use appropriate access controls and audit logging before integrating with real patient data.

---

## Want help?

- I can wire up example calls, add a simple web UI, or extract exact API routes from `main.py`/`vapi.py` and add precise curl examples — tell me which you prefer.

Thank you for exploring the Hospital Appointment AI Agent.