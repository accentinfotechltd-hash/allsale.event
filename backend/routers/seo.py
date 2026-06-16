"""SEO endpoints: dynamic sitemap.xml + robots.txt.

Generated from the live `events` collection so search engines discover
every approved event automatically. Cached implicitly by Vercel/CDN headers.
"""
from __future__ import annotations
from fastapi import APIRouter
from fastapi.responses import Response
from core import db, utc_now

router = APIRouter(tags=["seo"])

PUBLIC_ORIGIN_DEFAULT = "https://www.allsale.events"


async def _public_origin() -> str:
    cms = await db.platform_settings.find_one({"key": "cms"}, {"_id": 0}) or {}
    return (cms.get("public_origin") or PUBLIC_ORIGIN_DEFAULT).rstrip("/")


@router.get("/sitemap.xml")
async def sitemap():
    """Standard XML sitemap — Google/Bing crawl this once a day."""
    origin = await _public_origin()
    now_iso = utc_now().date().isoformat()
    static_paths = [
        ("/", "1.0", "daily"),
        ("/events", "0.9", "daily"),
        ("/events?past=1", "0.5", "weekly"),
        ("/influencers", "0.6", "weekly"),
        ("/about", "0.4", "monthly"),
        ("/contact", "0.4", "monthly"),
        ("/become-organizer", "0.7", "weekly"),
    ]
    parts = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for path, prio, freq in static_paths:
        parts.append(
            f"<url><loc>{origin}{path}</loc><lastmod>{now_iso}</lastmod>"
            f"<changefreq>{freq}</changefreq><priority>{prio}</priority></url>"
        )
    async for ev in db.events.find(
        {"status": {"$in": ["approved", "published"]}},
        {"_id": 0, "event_id": 1, "updated_at": 1, "created_at": 1},
    ).limit(5000):
        lastmod = (ev.get("updated_at") or ev.get("created_at") or now_iso)[:10]
        parts.append(
            f"<url><loc>{origin}/events/{ev['event_id']}</loc>"
            f"<lastmod>{lastmod}</lastmod><changefreq>daily</changefreq><priority>0.8</priority></url>"
        )
    parts.append("</urlset>")
    return Response(content="".join(parts), media_type="application/xml")


@router.get("/robots.txt")
async def robots():
    origin = await _public_origin()
    body = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /admin\n"
        "Disallow: /organizer\n"
        "Disallow: /api/\n"
        "Disallow: /scan\n"
        "Disallow: /feedback/\n"
        f"Sitemap: {origin}/api/sitemap.xml\n"
    )
    return Response(content=body, media_type="text/plain")
