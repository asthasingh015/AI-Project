"""Cortex AI - Autonomous AI Technology Persona.

Entry point for the backend. Run with ``uvicorn main:app``. The FastAPI
application itself lives in ``publisher.main``.
"""

from publisher.main import app  # noqa: F401
