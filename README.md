# Hospital AI Agent

A simple, local assistant that helps interpret and extract information from clinical text (dates, specialties, times, and more) so you can get fast, useful answers without digging through notes.

Why this matters to you
- Save time: get structured answers from free-form clinical notes.
- Reduce errors: standardized outputs for scheduling and triage.
- Easy to try: runs locally with minimal setup.

Who should try this
- Clinicians who want quick extraction of dates/times and specialties from notes.
- Administrative staff who need to speed up triage and scheduling tasks.
- Anyone evaluating small, privacy-conscious NLP tools locally.

Key features (user-focused)
- Extracts and normalizes specialty names from text.
- Parses and normalizes times and dates mentioned in notes.
- Provides simple CLI-based usage for fast, local testing.

Quick start (3 minutes)
1. Install Python 3.11+ (use system Python or a virtual environment).
2. Create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Run the app (try either):

```bash
python main.py
# or
python app.py
```

If the project uses a different entrypoint, running `python main.py` is a good first attempt.

How to use (examples)
- Extract a specialty from a sentence:

```text
Input: "Patient needs referral to cardiology for chest pain"
Output: "cardiology"
```

- Parse a time/date from a note:

```text
Input: "Follow up next Tuesday at 2pm"
Output: "2026-04-28 14:00"  # example normalized datetime
```

Tips and behavior
- The tool focuses on short text snippets rather than full EMR dumps.
- Results are best-effort—always verify critical scheduling information.
- Designed to run locally to help protect patient data; avoid uploading PHI to external services unless explicitly configured.

Troubleshooting
- If you see missing packages, re-run `pip install -r requirements.txt`.
- If `python main.py` does nothing, try `python app.py` or open `main.py` to see usage instructions.

Privacy & Data
- This project is intended to run locally. Do not send protected health information (PHI) to third-party services.

Want help or want me to do more?
- I can review `main.py` next to extract exact usage instructions and sample commands.
- Open an issue or contact the maintainer with test cases you care about.

Thank you for trying the Hospital AI Agent — let me know which sample you want me to run next.