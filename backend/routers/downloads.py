"""One-shot temporary download endpoint for handing the user a zip of the
codebase straight from the running container. Lives under /api/downloads/* so
it's exposed via the same Kubernetes ingress as the rest of the backend.

This is intentionally simple — only serves files that the operator dropped
into `backend/public_downloads/`. Safe because (a) the directory is not
user-writable, and (b) we resolve filenames against it via os.path.
"""
import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter(prefix="/downloads", tags=["downloads"])

DOWNLOADS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "public_downloads")


@router.get("/{filename}")
async def get_download(filename: str):
    # No traversal. Resolve and assert it stays inside DOWNLOADS_DIR.
    safe_name = os.path.basename(filename)
    full = os.path.join(DOWNLOADS_DIR, safe_name)
    if not os.path.isfile(full):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(full, media_type="application/octet-stream", filename=safe_name)
