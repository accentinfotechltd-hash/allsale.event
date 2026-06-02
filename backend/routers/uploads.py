"""File upload + public serve. Stores binary files in MongoDB so the platform
works on any hosting provider (Railway, Vercel, self-hosted) without depending
on an external object store. Files <16MB fit inside a BSON document; we serve
them via /api/files/<file_id> with ETag-based conditional GET so the browser
can short-circuit repeat fetches.

NOTE: For very large catalogs, swap MongoDB to Cloudflare R2 / S3 / Cloudinary
without touching frontend code — just change `put_blob` / `get_blob` below.
"""
import hashlib
import os
import uuid
from io import BytesIO

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response

from core import (
    ALLOWED_IMAGE_EXTS,
    MAX_UPLOAD_BYTES,
    MIME_TYPES,
    db,
    get_current_user,
    logger,
    require_role,
    utc_now,
)

router = APIRouter(tags=["uploads"])

# Optional pillow-based downscale: shrinks huge phone photos to <=1600px wide,
# saving ~80% storage. Skips silently if Pillow isn't installed.
try:
    from PIL import Image  # type: ignore
    _HAS_PIL = True
except Exception:
    _HAS_PIL = False


def _maybe_downscale(contents: bytes, ctype: str) -> bytes:
    if not _HAS_PIL or not ctype.startswith("image/"):
        return contents
    try:
        img = Image.open(BytesIO(contents))
        max_w = 1600
        if img.width <= max_w:
            return contents
        ratio = max_w / float(img.width)
        new_size = (max_w, int(img.height * ratio))
        img = img.resize(new_size, Image.LANCZOS)
        buf = BytesIO()
        fmt = "JPEG" if ctype in ("image/jpeg", "image/jpg") else ("PNG" if ctype == "image/png" else "WEBP")
        save_kwargs = {"optimize": True}
        if fmt == "JPEG":
            save_kwargs["quality"] = 85
            if img.mode != "RGB":
                img = img.convert("RGB")
        img.save(buf, format=fmt, **save_kwargs)
        return buf.getvalue()
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Downscale skipped: {exc}")
        return contents


@router.post("/uploads")
async def upload_image(request: Request, file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    """Upload an image. Returns a public URL the frontend can embed directly.

    Any signed-in user may upload (profile pictures), but file size and type
    are strictly capped. The returned `url` is absolute so it renders on the
    live Vercel site, where the frontend domain differs from the API.
    """
    ext = (os.path.splitext(file.filename or "")[1] or "").lower()
    if ext not in ALLOWED_IMAGE_EXTS:
        raise HTTPException(status_code=400, detail="Only jpg, png, webp allowed")
    contents = await file.read()
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 5MB)")

    ctype = MIME_TYPES.get(ext, file.content_type or "application/octet-stream")
    contents = _maybe_downscale(contents, ctype)
    file_id = uuid.uuid4().hex
    etag = hashlib.md5(contents).hexdigest()

    await db.uploaded_files.insert_one({
        "file_id": file_id,
        "storage_path": file_id,
        "original_filename": file.filename,
        "content_type": ctype,
        "size": len(contents),
        "etag": etag,
        "data": contents,
        "user_id": user["user_id"],
        "created_at": utc_now().isoformat(),
    })

    # Build an absolute URL — prefer APP_PUBLIC_URL (set by ops); otherwise
    # fall back to the host the request came in on. This guarantees the URL
    # works on Vercel even if APP_PUBLIC_URL isn't configured in Railway.
    rel = f"/api/files/{file_id}"
    env_base = (os.environ.get("APP_PUBLIC_URL") or "").rstrip("/")
    if env_base:
        absolute = f"{env_base}{rel}"
    else:
        # request.base_url is the FastAPI host (e.g. https://api.allsale.events/).
        # Strip the trailing slash so we don't end up with `//api/files/...`.
        host = str(request.base_url).rstrip("/")
        absolute = f"{host}{rel}"
    return {"url": absolute, "path": file_id, "file_id": file_id}


@router.get("/files/{path:path}")
async def get_file(path: str, request: Request):
    """Public read endpoint with ETag-based conditional GET (304 Not Modified).
    Event covers and floor plans are public assets — no auth required."""
    # `path` may be either the new file_id or the legacy nested storage_path.
    record = await db.uploaded_files.find_one(
        {"$or": [{"file_id": path}, {"storage_path": path}]},
        {"_id": 0},
    )
    if not record:
        raise HTTPException(status_code=404, detail="File not found")

    etag = record.get("etag")
    if etag:
        inm = request.headers.get("if-none-match")
        if inm and inm.strip('"') == etag:
            return Response(status_code=304, headers={"ETag": f'"{etag}"'})

    data = record.get("data")
    ctype = record.get("content_type", "application/octet-stream")
    if not data:
        # Legacy record without inline bytes — try external storage as a fallback.
        try:
            from storage import get_object  # local import: only used for legacy rows
            data, ctype = get_object(record.get("storage_path", path))
        except Exception as exc:  # noqa: BLE001
            logger.error(f"Legacy storage fetch failed for {path}: {exc}")
            raise HTTPException(status_code=404, detail="File not found") from exc

    if not etag:
        etag = hashlib.md5(data).hexdigest()
        await db.uploaded_files.update_one(
            {"file_id": record.get("file_id", path)},
            {"$set": {"etag": etag}},
        )
    headers = {
        "Cache-Control": "public, max-age=86400, stale-while-revalidate=604800",
        "ETag": f'"{etag}"',
    }
    return Response(content=data, media_type=ctype, headers=headers)
