import os
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request
from starlette.responses import Response

app = FastAPI(title="Physics Study API")

origins_raw = os.getenv("FRONTEND_ORIGINS", "*")
if origins_raw.strip() == "*":
    allow_origins = ["*"]
else:
    allow_origins = [o.strip() for o in origins_raw.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True if allow_origins != ["*"] else False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def lab_remote_proxy_middleware(request: Request, call_next):
    """Forward /api/lab/* requests to a remote sandbox (e.g. Docker Sandboxes cloud) when LAB_REMOTE_URL is set."""
    raw_remote = os.getenv("LAB_REMOTE_URL", "")
    remote = raw_remote.strip().strip("\"'").strip().rstrip("/")
    if remote and request.url.path.startswith("/api/lab"):
        if not remote.startswith(("http://", "https://")):
            remote = f"https://{remote}"
        target_url = f"{remote}{request.url.path}"
        if request.url.query:
            target_url = f"{target_url}?{request.url.query}"

        hop_by_hop = {
            "host",
            "content-length",
            "connection",
            "keep-alive",
            "proxy-authenticate",
            "proxy-authorization",
            "te",
            "trailers",
            "transfer-encoding",
            "upgrade",
        }
        headers = {k: v for k, v in request.headers.items() if k.lower() not in hop_by_hop}

        try:
            body = await request.body()
            content_payload = body if request.method not in ("GET", "HEAD") and body else None
            async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
                remote_resp = await client.request(
                    method=request.method,
                    url=target_url,
                    headers=headers,
                    content=content_payload,
                )

            excluded_headers = {
                "content-encoding",
                "content-length",
                "transfer-encoding",
                "connection",
            }
            resp_headers = {
                k: v
                for k, v in remote_resp.headers.items()
                if k.lower() not in excluded_headers
            }

            return Response(
                content=remote_resp.content,
                status_code=remote_resp.status_code,
                headers=resp_headers,
            )
        except Exception as exc:
            import traceback
            tb = traceback.format_exc()
            return Response(
                content=f"Remote lab sandbox unreachable at {remote}: {type(exc).__name__}: {exc}\n{tb}",
                status_code=502,
                media_type="text/plain",
            )

    return await call_next(request)


@app.get("/health")
def health() -> dict[str, str]:
    """Used by Render health checks and the CD smoke test."""
    return {"status": "ok"}


# Routers from app/api/ get registered here.
from app.api.lab import router as lab_router  # noqa: E402
from app.api.live import router as live_router  # noqa: E402

app.include_router(lab_router)
app.include_router(live_router)

# Serve the website from the same address, so a live demo needs one URL and no CORS setup
# (http://localhost:8000/). Mounted last: /health and /api/* above take precedence.
SITE = Path(__file__).resolve().parents[2] / "frontend"
if (SITE / "index.html").is_file():
    app.mount("/", StaticFiles(directory=SITE, html=True), name="site")
