# Adaptly backend foundation

This directory currently contains the FastAPI foundation and the Issue #17
deterministic Module 5 assistant endpoint.

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

## Test

```bash
cd backend
python3 -m pytest
```
