from pathlib import Path
import sys
from typing import Callable, Awaitable

# Vercel executes from project root. Add backend to import path.
BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app import app as fastapi_app  # noqa: E402


async def app(scope, receive, send):
    """
    Vercel may forward paths with or without '/api' prefix.
    Normalize path so backend routes '/api/*' always match.
    """
    if scope.get("type") == "http":
        path = scope.get("path", "")
        # Rewrite /api/index.py/<path> -> /api/<path>
        if path.startswith("/api/index.py/"):
            path = "/api/" + path[len("/api/index.py/") :]
        elif path == "/api/index.py":
            path = "/api/health"
        if not path.startswith("/api"):
            path = f"/api{path}"
        scope = {**scope, "path": path}
    await fastapi_app(scope, receive, send)

