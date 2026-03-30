"""Convenience entry for `uvicorn main:app --app-dir src`."""

from app.http.bootstrap import app

__all__ = ["app"]
