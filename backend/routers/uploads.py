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

# iPhone-friendly HEIC/HEIF support — registers extra Pillow openers so
# `Image.open(...)` can decode .heic photos transparently. We then transcode
# them to JPEG before storing, since browsers can't render HEIC directly.
try:
    from pillow_heif import register_heif_opener  # type: ignore
    register_heif_opener()
    _HAS_HEIF = True
except Exception:
    _HAS_HEIF = False


def _sniff_image_type(blob: bytes) -> str:
    """Best-effort magic-byte detection. Returns 'jpg' / 'png' / 'webp' /
    'heic' / 'heif' / '' (unknown). Used when the upload arrives with a
    missing or generic extension (common from mobile share sheets)."""
    if len(blob) < 12:
        return ""
    if blob[:3] == b"\xff\xd8\xff":
        return "jpg"
    if blob[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if blob[:4] == b"RIFF" and blob[8:12] == b"WEBP":
        return "webp"
    # ISO Base Media File Format — covers heic/heif/avif/mp4
    if blob[4:8] == b"ftyp":
        brand = blob[8:12]
        if brand in (b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis"):
            return "heic"
        if brand in (b"mif1", b"msf1", b"heif"):
            return "heif"
    return ""


def _maybe_downscale(contents: bytes, ctype: str) -> tuple[bytes, str]:
    """Returns (contents, content_type) — may transcode HEIC→JPEG and/or
    downscale large images. content_type may change if a transcode happened."""
    if not _HAS_PIL or not ctype.startswith("image/"):
        return contents, ctype
    try:
        img = Image.open(BytesIO(contents))
        # If HEIC/HEIF, force a JPEG output so browsers can render it.
        is_heif = ctype in ("image/heic", "image/heif") or (img.format or "").upper() in ("HEIF", "HEIC")
        max_w = 1600
        needs_resize = img.width > max_w
        if not is_heif and not needs_resize:
            return contents, ctype
        if needs_resize:
            ratio = max_w / float(img.width)
            new_size = (max_w, int(img.height * ratio))
            img = img.resize(new_size, Image.LANCZOS)
        buf = BytesIO()
        if is_heif:
            fmt, out_ctype = "JPEG", "image/jpeg"
        elif ctype in ("image/jpeg", "image/jpg"):
            fmt, out_ctype = "JPEG", "image/jpeg"
        elif ctype == "image/png":
            fmt, out_ctype = "PNG", "image/png"
        else:
            fmt, out_ctype = "WEBP", "image/webp"
        save_kwargs = {"optimize": True}
        if fmt == "JPEG":
            save_kwargs["quality"] = 85
            if img.mode != "RGB":
                img = img.convert("RGB")
        img.save(buf, format=fmt, **save_kwargs)
        return buf.getvalue(), out_ctype
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Downscale/transcode skipped: {exc}")
        return contents, ctype


@router.post("/uploads")
async def upload_image(request: Request, file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    """Upload an image. Returns a public URL the frontend can embed directly.

    Any signed-in user may upload (profile pictures), but file size and type
    are strictly capped. The returned `url` is absolute so it renders on the
    live Vercel site, where the frontend domain differs from the API.

    Mobile share-sheets sometimes drop the file extension or hand us a HEIC
    photo straight from the iOS Photo library. We sniff the magic bytes and
    transcode HEIC → JPEG so the upload works regardless of source.
    """
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="The file is empty — please choose another image.")
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large — please pick an image under 5 MB.")

    ext = (os.path.splitext(file.filename or "")[1] or "").lower()
    sniffed = _sniff_image_type(contents)
    # If the extension is missing, normalise from the sniffed magic bytes.
    if ext not in ALLOWED_IMAGE_EXTS and ext not in (".heic", ".heif"):
        if sniffed in {"jpg", "png", "webp"}:
            ext = f".{sniffed}" if sniffed != "jpg" else ".jpg"
        elif sniffed in {"heic", "heif"}:
            ext = f".{sniffed}"
        else:
            raise HTTPException(
                status_code=400,
                detail="Unsupported image format. Please upload a JPG, PNG, WEBP or HEIC file.",
            )

    # HEIC/HEIF — accept but only if Pillow can transcode it.
    if ext in (".heic", ".heif"):
        if not _HAS_HEIF:
            raise HTTPException(
                status_code=400,
                detail="HEIC images aren't supported on this server. Please pick a JPG or PNG.",
            )
        ctype = "image/heic" if ext == ".heic" else "image/heif"
    else:
        ctype = MIME_TYPES.get(ext, file.content_type or "application/octet-stream")

    contents, ctype = _maybe_downscale(contents, ctype)
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

    # Build an absolute URL — Railway/Vercel proxies set X-Forwarded-Host
    # and X-Forwarded-Proto, but uvicorn doesn't trust them by default.
    # Read them manually so the URL is always the public-facing host.
    rel = f"/api/files/{file_id}"
    env_base = (os.environ.get("APP_PUBLIC_URL") or "").rstrip("/")
    if env_base:
        absolute = f"{env_base}{rel}"
    else:
        proto = (request.headers.get("x-forwarded-proto") or request.url.scheme or "https").split(",")[0].strip()
        host = (request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc).split(",")[0].strip()
        absolute = f"{proto}://{host}{rel}" if host else rel
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
