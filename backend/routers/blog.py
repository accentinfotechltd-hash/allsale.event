"""Blog endpoints for SEO compound growth.

Public:
  - GET  /api/blog                  list published posts (paginated)
  - GET  /api/blog/{slug}           get a single published post by slug
  - GET  /api/blog/{slug}/related   3 most recent published posts (excluding self)

Admin (auth required, role=admin):
  - GET    /api/admin/blog          list ALL posts (incl. drafts)
  - POST   /api/admin/blog          create a post (draft or published)
  - PUT    /api/admin/blog/{slug}   update post content
  - DELETE /api/admin/blog/{slug}   delete a post

Posts live in MongoDB collection `blog_posts`. Slug is the unique primary key
so the public URL never breaks — title can be edited freely without changing
the link organizers/socials share.
"""
from __future__ import annotations

import re
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core import db, get_current_user, utc_now, logger

router = APIRouter(tags=["blog"])


# ---------- helpers ----------

def _slugify(s: str) -> str:
    """URL-safe slug: lowercase, dashes, no leading/trailing punctuation."""
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s[:80] or "post"


def _admin_only(user: dict):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")


def _strip_id(doc: dict) -> dict:
    """Remove internal _id field before returning to the API."""
    if not doc:
        return doc
    doc.pop("_id", None)
    return doc


# ---------- pydantic schemas ----------

class BlogPostIn(BaseModel):
    title: str = Field(..., min_length=2, max_length=200)
    slug: Optional[str] = None  # auto-generated from title if omitted
    excerpt: Optional[str] = Field(default="", max_length=400)
    cover_url: Optional[str] = ""
    body_html: str = Field(..., min_length=1)
    tags: List[str] = []
    status: str = Field(default="draft", pattern="^(draft|published)$")
    meta_title: Optional[str] = ""
    meta_description: Optional[str] = ""


class BlogPostPatch(BaseModel):
    title: Optional[str] = None
    excerpt: Optional[str] = None
    cover_url: Optional[str] = None
    body_html: Optional[str] = None
    tags: Optional[List[str]] = None
    status: Optional[str] = Field(default=None, pattern="^(draft|published)$")
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None


# ---------- public endpoints ----------

@router.get("/blog")
async def list_published(
    limit: int = Query(20, ge=1, le=50),
    skip: int = Query(0, ge=0),
    tag: Optional[str] = None,
):
    """Public blog index — only published posts, sorted newest first."""
    q: dict = {"status": "published"}
    if tag:
        q["tags"] = tag
    total = await db.blog_posts.count_documents(q)
    cur = (
        db.blog_posts.find(
            q,
            {
                "_id": 0,
                "body_html": 0,  # exclude heavy body from the list
            },
        )
        .sort("published_at", -1)
        .skip(skip)
        .limit(limit)
    )
    items = [doc async for doc in cur]
    return {"total": total, "items": items}


@router.get("/blog/{slug}")
async def get_post(slug: str):
    doc = await db.blog_posts.find_one({"slug": slug, "status": "published"})
    if not doc:
        raise HTTPException(status_code=404, detail="Post not found")
    return _strip_id(doc)


@router.get("/blog/{slug}/related")
async def related_posts(slug: str):
    cur = (
        db.blog_posts.find(
            {"status": "published", "slug": {"$ne": slug}},
            {"_id": 0, "body_html": 0},
        )
        .sort("published_at", -1)
        .limit(3)
    )
    return [doc async for doc in cur]


# ---------- admin endpoints ----------

@router.get("/admin/blog")
async def admin_list_all(user: dict = Depends(get_current_user)):
    _admin_only(user)
    cur = db.blog_posts.find({}, {"_id": 0}).sort("updated_at", -1)
    return [doc async for doc in cur]


@router.get("/admin/blog/{slug}")
async def admin_get(slug: str, user: dict = Depends(get_current_user)):
    _admin_only(user)
    doc = await db.blog_posts.find_one({"slug": slug})
    if not doc:
        raise HTTPException(status_code=404, detail="Post not found")
    return _strip_id(doc)


@router.post("/admin/blog")
async def admin_create(payload: BlogPostIn, user: dict = Depends(get_current_user)):
    _admin_only(user)
    slug = _slugify(payload.slug or payload.title)
    # If a post with this slug already exists, suffix a short counter so the
    # admin still gets a unique URL without manual intervention.
    if await db.blog_posts.find_one({"slug": slug}):
        suffix = 2
        while await db.blog_posts.find_one({"slug": f"{slug}-{suffix}"}):
            suffix += 1
        slug = f"{slug}-{suffix}"
    now = utc_now()
    doc = {
        "slug": slug,
        "title": payload.title.strip(),
        "excerpt": (payload.excerpt or "").strip(),
        "cover_url": payload.cover_url or "",
        "body_html": payload.body_html,
        "tags": [t.strip() for t in (payload.tags or []) if t.strip()],
        "status": payload.status,
        "meta_title": (payload.meta_title or payload.title).strip(),
        "meta_description": (payload.meta_description or payload.excerpt or "").strip(),
        "author_id": user.get("user_id"),
        "author_name": user.get("name") or user.get("email"),
        "created_at": now,
        "updated_at": now,
        "published_at": now if payload.status == "published" else None,
    }
    await db.blog_posts.insert_one(doc)
    return _strip_id(doc)


@router.put("/admin/blog/{slug}")
async def admin_update(
    slug: str,
    payload: BlogPostPatch,
    user: dict = Depends(get_current_user),
):
    _admin_only(user)
    existing = await db.blog_posts.find_one({"slug": slug})
    if not existing:
        raise HTTPException(status_code=404, detail="Post not found")
    updates: dict = {"updated_at": utc_now()}
    fields = payload.model_dump(exclude_unset=True)
    for k, v in fields.items():
        if v is not None:
            updates[k] = v
    # Promote to published — stamp published_at the first time it flips.
    if updates.get("status") == "published" and not existing.get("published_at"):
        updates["published_at"] = utc_now()
    await db.blog_posts.update_one({"slug": slug}, {"$set": updates})
    doc = await db.blog_posts.find_one({"slug": slug})
    return _strip_id(doc)


@router.delete("/admin/blog/{slug}")
async def admin_delete(slug: str, user: dict = Depends(get_current_user)):
    _admin_only(user)
    res = await db.blog_posts.delete_one({"slug": slug})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Post not found")
    return {"deleted": slug}


# ---------- email subscribers ----------

class SubscribeIn(BaseModel):
    email: str
    source: Optional[str] = None  # "blog_index", "blog_post:<slug>", etc.


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@router.post("/blog/subscribers")
async def subscribe(payload: SubscribeIn):
    """Public newsletter signup — idempotent.

    Repeat submissions of the same address are coalesced (we just bump the
    `last_seen_at`) so spam-clicking the button doesn't pollute the list.
    """
    email = (payload.email or "").strip().lower()
    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Please enter a valid email")
    now = utc_now()
    existing = await db.blog_subscribers.find_one({"email": email})
    if existing:
        if existing.get("status") == "unsubscribed":
            # User opted back in — flip the flag.
            await db.blog_subscribers.update_one(
                {"email": email},
                {"$set": {"status": "active", "resubscribed_at": now, "last_seen_at": now}},
            )
            return {"ok": True, "status": "resubscribed"}
        await db.blog_subscribers.update_one(
            {"email": email}, {"$set": {"last_seen_at": now}}
        )
        return {"ok": True, "status": "already_subscribed"}
    await db.blog_subscribers.insert_one(
        {
            "email": email,
            "source": payload.source or "blog",
            "status": "active",
            "created_at": now,
            "last_seen_at": now,
        }
    )
    return {"ok": True, "status": "subscribed"}


@router.post("/blog/unsubscribe")
async def unsubscribe(payload: SubscribeIn):
    """Public one-click unsubscribe (used in email footers)."""
    email = (payload.email or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Email required")
    await db.blog_subscribers.update_one(
        {"email": email},
        {"$set": {"status": "unsubscribed", "unsubscribed_at": utc_now()}},
    )
    return {"ok": True}


class UnsubscribeReasonIn(BaseModel):
    email: str
    reason: str  # one of the standard buckets below
    comment: Optional[str] = None


# Standard reason buckets — keep finite so we can chart them on the admin
# dashboard. Free-form text goes in `comment`.
_UNSUB_REASONS = {
    "too_many_emails",
    "not_relevant",
    "never_signed_up",
    "found_better",
    "other",
}


@router.post("/blog/unsubscribe/reason")
async def unsubscribe_reason(payload: UnsubscribeReasonIn):
    """Optional opt-out survey — captures why a subscriber left so we can
    improve content cadence / relevance. Always returns ok:true to avoid
    leaking which addresses are on the list.
    """
    email = (payload.email or "").strip().lower()
    if not email:
        return {"ok": True}
    reason = payload.reason if payload.reason in _UNSUB_REASONS else "other"
    comment = (payload.comment or "").strip()[:500] or None
    await db.blog_subscribers.update_one(
        {"email": email},
        {"$set": {
            "unsubscribe_reason": reason,
            "unsubscribe_comment": comment,
            "unsubscribe_feedback_at": utc_now(),
        }},
    )
    return {"ok": True}


@router.get("/admin/newsletter/subscribers")
async def admin_list_subscribers(
    user: dict = Depends(get_current_user),
    status: Optional[str] = None,
    limit: int = Query(200, ge=1, le=1000),
    skip: int = Query(0, ge=0),
):
    _admin_only(user)
    q: dict = {}
    if status:
        q["status"] = status
    total = await db.blog_subscribers.count_documents(q)
    active = await db.blog_subscribers.count_documents({"status": "active"})
    cur = db.blog_subscribers.find(q, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit)
    items = [doc async for doc in cur]
    return {"total": total, "active": active, "items": items}


@router.get("/admin/newsletter/unsubscribe-reasons")
async def admin_unsubscribe_reasons(user: dict = Depends(get_current_user)):
    """Aggregated counts of unsubscribe reasons + recent free-form comments.

    Powers a small "Why are people leaving?" widget on the admin newsletter
    tab. Returns `{counts: {reason: n}, comments: [{email, comment, at}]}`.
    """
    _admin_only(user)
    pipeline = [
        {"$match": {"status": "unsubscribed", "unsubscribe_reason": {"$exists": True}}},
        {"$group": {"_id": "$unsubscribe_reason", "count": {"$sum": 1}}},
    ]
    counts: dict = {}
    async for row in db.blog_subscribers.aggregate(pipeline):
        counts[row["_id"]] = row["count"]
    # Recent free-form comments
    cur = db.blog_subscribers.find(
        {"unsubscribe_comment": {"$nin": [None, ""]}},
        {"_id": 0, "email": 1, "unsubscribe_comment": 1, "unsubscribe_feedback_at": 1, "unsubscribe_reason": 1},
    ).sort("unsubscribe_feedback_at", -1).limit(50)
    comments = [c async for c in cur]
    return {"counts": counts, "comments": comments}


@router.delete("/admin/newsletter/subscribers/{email}")
async def admin_remove_subscriber(email: str, user: dict = Depends(get_current_user)):
    _admin_only(user)
    res = await db.blog_subscribers.delete_one({"email": email.lower()})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return {"deleted": email}


@router.post("/admin/blog/{slug}/notify-subscribers")
async def admin_notify_subscribers(slug: str, user: dict = Depends(get_current_user)):
    """Fan-out a published blog post to every active newsletter subscriber.

    Idempotent per-subscriber: each post has a `notified_subscribers` set on
    the post doc — we skip any address already in that set so re-running the
    button after adding new subscribers only emails the new ones.

    The actual send is via `send_template("blog_new_post", ...)` which uses
    Resend. We spawn it as a background task per recipient so the endpoint
    returns fast even for large lists.
    """
    _admin_only(user)
    post = await db.blog_posts.find_one({"slug": slug})
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    if post.get("status") != "published":
        raise HTTPException(status_code=400, detail="Publish the post first")

    # Lazy import so the blog router doesn't pull in the email service at
    # module import time (keeps cold-starts fast).
    from emails import send_template

    already = set(post.get("notified_subscribers") or [])
    cur = db.blog_subscribers.find(
        {"status": "active", "email": {"$nin": list(already)}},
        {"_id": 0, "email": 1},
    )
    targets = [doc["email"] async for doc in cur]

    if not targets:
        return {"sent": 0, "skipped": len(already), "total_active": len(already), "reason": "All active subscribers already notified for this post"}

    ctx_base = {
        "post_title": post.get("title") or "",
        "post_excerpt": post.get("excerpt") or "",
        "post_slug": post.get("slug") or slug,
        "cover_url": post.get("cover_url") or "",
    }

    # Bounded-concurrency fan-out: send up to 10 emails in parallel. Keeps
    # large subscriber lists from blocking the request thread sequentially
    # while still respecting Resend's rate limits.
    import asyncio as _asyncio
    sem = _asyncio.Semaphore(10)
    results = {"sent": 0, "failed": 0}

    async def _send_one(email: str) -> None:
        async with sem:
            try:
                await send_template(
                    "blog_new_post",
                    email,
                    {**ctx_base, "subscriber_email": email},
                    db=db,
                )
                results["sent"] += 1
            except Exception as exc:  # pragma: no cover
                results["failed"] += 1
                logger.warning(f"[blog-notify] {slug} → {email} failed: {exc}")

    await _asyncio.gather(*(_send_one(e) for e in targets))
    sent = results["sent"]
    failed = results["failed"]

    # Stamp the post so a re-run only hits new subscribers.
    new_notified = list(already.union(targets))
    await db.blog_posts.update_one(
        {"slug": slug},
        {
            "$set": {
                "notified_subscribers": new_notified,
                "last_notified_at": utc_now(),
            }
        },
    )

    return {
        "sent": sent,
        "failed": failed,
        "skipped": len(already),
        "total_active": len(already) + len(targets),
    }
