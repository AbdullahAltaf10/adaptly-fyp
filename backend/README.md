# Adaptly backend foundation

This directory contains the FastAPI foundation and Module 5 assistant endpoint.
It defaults to deterministic mock mode; Gemini is opt-in through environment
variables.

Python 3.10 or later is required.

## Install

```bash
cd backend
python3 -m pip install -e ".[test]"
```

## Run

```bash
cd backend
python3 -m uvicorn app.main:app --reload
```

Open Swagger UI at `http://127.0.0.1:8000/docs`.

## Assistant modes

Mock mode is the default and requires no credentials:

```bash
export ASSISTANT_MODE=mock
```

To use Gemini, keep the API key in your shell environment and never commit it:

```bash
export ASSISTANT_MODE=gemini
export GEMINI_API_KEY="your-key"
export GEMINI_MODEL="gemini-3.6-flash"
export GEMINI_TIMEOUT_MS=60000
```

Gemini mode sends the supplied assistant question, active chunk, and prior
conversation messages to Google's Gemini service. Do not send webcam data.

## Test

```bash
cd backend
python3 -m pytest
```
