"""File upload + public serve via Emergent object storage."""
import os
import uuid
import hashlib

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Request
from fastapi.responses import Response

from core import (
    db, get_current_user, require_role, utc_now,
    ALLOWED_IMAGE_EXTS, MAX_UPLOAD_BYTES, MIME_TYPES, logger,
)
from storage import put_object, get_object, APP_NAME as STORAGE_APP_NAME

router = APIRouter(tags=["uploads"])


@router.post("/uploads")
async def upload_image(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    """Upload an image to persistent object storage. Returns public URL."""
    await require_role(user, "organizer", "admin")
    ext = (os.path.splitext(file.filename or "")[1] or "").lower()
    if ext not in ALLOWED_IMAGE_EXTS:
        raise HTTPException(status_code=400, detail="Only jpg, png, webp allowed")
    contents = await file.read()
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 5MB)")

    storage_path = f"{STORAGE_APP_NAME}/uploads/{user['user_id']}/{uuid.uuid4().hex}{ext}"
    ctype = MIME_TYPES.get(ext, file.content_type or "application/octet-stream")
    try:
        result = put_object(storage_path, contents, ctype)
    except Exception as e:
        logger.error(f"Storage put failed: {e}")
        raise HTTPException(status_code=502, detail="Upload failed (storage error)")

    etag = hashlib.md5(contents).hexdigest()
    await db.uploaded_files.insert_one({
        "file_id": uuid.uuid4().hex,
        "storage_path": result["path"],
        "original_filename": file.filename,
        "content_type": ctype,
        "size": result.get("size", len(contents)),
        "etag": etag,
        "user_id": user["user_id"],
        "created_at": utc_now().isoformat(),
    })
    return {"url": f"/api/files/{result['path']}", "path": result["path"]}


@router.get("/files/{path:path}")
async def get_file(path: str, request: Request):
    """Public read endpoint with ETag support for conditional GET (304 Not Modified).
    Event covers and venue floor plans are public assets, so no auth required."""
    record = await db.uploaded_files.find_one({"storage_path": path}, {"_id": 0})
    if not record:
        raise HTTPException(status_code=404, detail="File not found")

    # ETag-based conditional GET: even when the edge proxy strips Cache-Control,
    # browsers can revalidate and skip body transfer if ETag matches.
    etag = record.get("etag")
    if etag:
        inm = request.headers.get("if-none-match")
        if inm and inm.strip('"') == etag:
            return Response(status_code=304, headers={"ETag": f'"{etag}"'})

    try:
        data, ctype = get_object(path)
    except Exception as e:
        logger.error(f"Storage get failed for {path}: {e}")
        raise HTTPException(status_code=404, detail="File not found")
    if not etag:
        etag = hashlib.md5(data).hexdigest()
        # Backfill the etag so future requests can short-circuit at the 304 check
        await db.uploaded_files.update_one(
            {"storage_path": path}, {"$set": {"etag": etag}}
        )
    headers = {
        "Cache-Control": "public, max-age=86400, stale-while-revalidate=604800",
        "ETag": f'"{etag}"',
    }
    return Response(content=data, media_type=record.get("content_type", ctype), headers=headers)
