from pathlib import Path
import sys
import json
import traceback

# Vercel executes from project root. Add backend to import path.
BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

_fastapi_app = None


async def app(scope, receive, send):
    """
    Vercel may forward paths with or without '/api' prefix.
    Normalize path so backend routes '/api/*' always match.
    """
    global _fastapi_app
    try:
        if _fastapi_app is None:
            # Lazy import to avoid crashing at module import time.
            from app import app as fastapi_app  # noqa: E402

            _fastapi_app = fastapi_app

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

        await _fastapi_app(scope, receive, send)
    except Exception as exc:
        if scope.get("type") != "http":
            raise

        payload = {
            "detail": "Function invocation failed",
            "error": repr(exc),
            "traceback": traceback.format_exc().splitlines()[-30:],
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = [(b"content-type", b"application/json; charset=utf-8")]
        await send({"type": "http.response.start", "status": 500, "headers": headers})
        await send({"type": "http.response.body", "body": body})

