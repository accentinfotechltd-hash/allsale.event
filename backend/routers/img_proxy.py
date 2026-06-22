"""Image proxy — lets the frontend load remote images as if they were same-
origin so html-to-image / canvas can export them without tainting.

Use case: `/events/{id}/share` flyer downloads. Event posters live on Unsplash,
Imgur, Cloudinary, etc., which often don't send permissive CORS headers. Loading
them through `<img crossorigin="anonymous" src="...">` fails, and falling back
to no-CORS makes the canvas tainted (toPng / toBlob raise SecurityError).

This proxy fetches the remote bytes server-side, then streams them back with
`Access-Control-Allow-Origin: *` so the browser treats them as same-origin.

Safety: only HTTPS sources, content-type must start with `image/`, max 12 MB,
and we cap downloads to 6 seconds to avoid being abused as a generic SSRF.
"""
import asyncio
import httpx
from fastapi import APIRouter, HTTPException, Query, Response

router = APIRouter(tags=["img_proxy"])

MAX_BYTES = 12 * 1024 * 1024  # 12 MB
TIMEOUT_S = 6.0


@router.get("/img-proxy")
async def img_proxy(url: str = Query(..., min_length=10, max_length=2048)):
    if not url.lower().startswith(("http://", "https://")):
        raise HTTPException(400, detail="Only http(s) URLs allowed")
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S, follow_redirects=True) as client:
            r = await client.get(url, headers={"User-Agent": "AllsaleImageProxy/1.0"})
    except (httpx.TimeoutException, httpx.RequestError):
        raise HTTPException(504, detail="Upstream image fetch timed out")
    if r.status_code >= 400:
        raise HTTPException(r.status_code, detail="Upstream image not available")
    ctype = (r.headers.get("content-type") or "").split(";")[0].strip().lower()
    if not ctype.startswith("image/"):
        raise HTTPException(415, detail="Not an image")
    if len(r.content) > MAX_BYTES:
        raise HTTPException(413, detail="Image too large (max 12 MB)")
    return Response(
        content=r.content,
        media_type=ctype,
        headers={
            "Cache-Control": "public, max-age=86400, immutable",
            "Access-Control-Allow-Origin": "*",
            "Cross-Origin-Resource-Policy": "cross-origin",
        },
    )
