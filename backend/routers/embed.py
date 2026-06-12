"""Embeddable widget — public, no-auth endpoints.

Lets organizers (or anyone) drop a 2-line `<script>` snippet onto an external
marketing site to render their upcoming events. The widget renders entirely
in vanilla JS with inline styles so it has zero dependencies on the host
site's CSS framework.

Endpoints:
  GET /api/embed/events.json
       Public JSON feed of upcoming events. Filters: `organizer_id` (only
       that organizer's events), `event_id` (single event), `limit`,
       `category`.
  GET /api/embed/events.js
       The vanilla-JS loader. Embedders include it like:
         <div data-allsale-events data-organizer-id="user_xxx" data-theme="light"></div>
         <script src="https://www.allsale.events/api/embed/events.js" async></script>
  GET /api/embed/track
       1x1 GIF tracking pixel. Counts widget impressions / clicks by
       (organizer_id, event_id, host). Stored in `embed_events` so
       organizers see which external sites drive their traffic.
  GET /api/organizer/embed/analytics
       Organizer-facing rollup: impressions + click-throughs by source host
       over the last 30 days.
"""
from __future__ import annotations

import os
from typing import Optional
from datetime import timedelta, datetime
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from core import db, utc_now, event_to_public, get_current_user, require_role

router = APIRouter(tags=["embed"])

PUBLIC_ORIGIN = os.environ.get("PUBLIC_ORIGIN") or "https://www.allsale.events"

# A 1x1 transparent GIF (43 bytes). Hard-coded so we don't need any image
# library at request time.
_PIXEL_GIF = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01"
    b"\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)


def _host_from_url(referer: Optional[str]) -> Optional[str]:
    if not referer:
        return None
    try:
        host = urlparse(referer).hostname
        return (host or "").lower() or None
    except Exception:  # noqa: BLE001
        return None


@router.get("/embed/events.json")
async def embed_events_feed(
    organizer_id: Optional[str] = None,
    event_id: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 6,
):
    """Public JSON feed for the widget. Only upcoming approved events.

    Open CORS — the widget runs on third-party marketing sites with arbitrary
    origins, so we set `Access-Control-Allow-Origin: *`. The endpoint exposes
    only public event data already shown on `/events`, so widening CORS adds
    no leakage risk.
    """
    limit = max(1, min(20, int(limit or 6)))
    cutoff = (utc_now() - timedelta(hours=24)).isoformat()
    q: dict = {
        "status": {"$in": ["approved", "published"]},
        "date": {"$gte": cutoff},
    }
    if organizer_id:
        q["organizer_id"] = organizer_id
    if event_id:
        q["event_id"] = event_id
    if category:
        q["category"] = category
    items = []
    async for e in db.events.find(q, {"_id": 0}).sort("date", 1).limit(limit):
        p = event_to_public(e)
        items.append({
            "event_id": p.get("event_id"),
            "title": p.get("title"),
            "date": p.get("date"),
            "venue": p.get("venue"),
            "city": p.get("city"),
            "image_url": p.get("image_url"),
            "currency": p.get("currency", "NZD"),
            "min_price": min(
                (float(t.get("price") or 0) for t in (p.get("tiers") or []) if (t.get("price") is not None)),
                default=None,
            ),
            "url": f"{PUBLIC_ORIGIN}/events/{p.get('event_id')}",
        })
    import json as _json
    return Response(
        content=_json.dumps({"items": items, "site": PUBLIC_ORIGIN}),
        media_type="application/json",
        headers={
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "public, max-age=300",  # 5-min cache for embedders
        },
    )


# Vanilla JS loader. Inline strings (no template engine) so we never leak
# server-side variables to embedders. f-string only used for PUBLIC_ORIGIN
# substitution at boot.
def _build_loader_js() -> str:
    api_base = PUBLIC_ORIGIN
    return r"""
(function(){
  var API_BASE = "__API_BASE__";
  function fmtMoney(n, cur){ try { return new Intl.NumberFormat(undefined,{style:"currency",currency:cur||"NZD"}).format(n); } catch(e){ return (cur||"NZD")+" "+(n||0); } }
  function fmtDate(iso){ try { var d=new Date(iso); return d.toLocaleDateString(undefined,{month:"short",day:"numeric",year:"numeric"}); } catch(e){ return iso || ""; } }
  function el(tag, attrs, kids){ var n=document.createElement(tag); for(var k in attrs||{}){ if(k==="style"){ for(var s in attrs[k]) n.style[s]=attrs[k][s]; } else if(k==="text"){ n.textContent=attrs[k]; } else { n.setAttribute(k, attrs[k]); } } (kids||[]).forEach(function(c){ if(c) n.appendChild(c); }); return n; }
  function render(container, data, theme, organizerHint){
    var dark = theme === "dark";
    var bg = dark ? "#0e0e10" : "#fff";
    var card = dark ? "#161618" : "#fafaf8";
    var border = dark ? "#26262a" : "#e8e6dc";
    var text = dark ? "#f5f4ef" : "#1a1a1a";
    var dim = dark ? "#9a988f" : "#666";
    var accent = "#f08a2a";
    container.innerHTML = "";
    container.style.fontFamily = "ui-sans-serif,system-ui,-apple-system,sans-serif";
    container.style.background = bg;
    container.style.color = text;
    var grid = el("div", { style: { display:"grid", gridTemplateColumns:"repeat(auto-fill,minmax(220px,1fr))", gap:"16px" } });
    if(!data.items || !data.items.length){
      grid.appendChild(el("div", { text: "No upcoming events.", style:{ color: dim, padding:"24px", textAlign:"center" } }));
    } else {
      data.items.forEach(function(ev){
        var a = el("a", { href: ev.url, target:"_blank", rel:"noopener", style: { display:"block", textDecoration:"none", color:text, background:card, border:"1px solid "+border, borderRadius:"12px", overflow:"hidden", transition:"transform .2s,box-shadow .2s" } });
        a.onmouseover = function(){ a.style.transform="translateY(-2px)"; a.style.boxShadow="0 8px 24px rgba(0,0,0,.08)"; };
        a.onmouseout = function(){ a.style.transform=""; a.style.boxShadow=""; };
        a.onclick = function(){ track("click", organizerHint, ev.event_id); };
        a.appendChild(el("img", { src: ev.image_url, alt: ev.title, style: { width:"100%", aspectRatio:"4/3", objectFit:"cover", display:"block" } }));
        var body = el("div", { style: { padding:"12px 14px 14px" } });
        body.appendChild(el("div", { text: fmtDate(ev.date), style:{ color: accent, fontSize:"11px", fontWeight:"600", letterSpacing:"0.08em", textTransform:"uppercase", marginBottom:"6px" } }));
        body.appendChild(el("div", { text: ev.title, style:{ fontSize:"15px", fontWeight:"600", lineHeight:"1.3", marginBottom:"4px" } }));
        body.appendChild(el("div", { text: (ev.venue||"") + (ev.city ? ", "+ev.city : ""), style:{ color: dim, fontSize:"12px", marginBottom:"8px" } }));
        if(ev.min_price != null){
          body.appendChild(el("div", { text: "From " + fmtMoney(ev.min_price, ev.currency), style:{ color: accent, fontSize:"13px", fontWeight:"600" } }));
        }
        a.appendChild(body);
        grid.appendChild(a);
        // Per-event impression beacon. Lazy, fire-and-forget.
        track("impression", organizerHint, ev.event_id);
      });
    }
    container.appendChild(grid);
    container.appendChild(el("div", { style: { textAlign:"right", marginTop:"10px", fontSize:"11px", color: dim } }, [
      el("a", { href: API_BASE, target:"_blank", rel:"noopener", text:"Powered by Allsale Events", style: { color: dim, textDecoration:"none" } })
    ]));
  }
  function track(kind, organizerId, eventId){
    try {
      var img = new Image(1, 1);
      var qs = "?kind=" + encodeURIComponent(kind);
      if (organizerId) qs += "&organizer_id=" + encodeURIComponent(organizerId);
      if (eventId) qs += "&event_id=" + encodeURIComponent(eventId);
      img.src = API_BASE + "/api/embed/track" + qs + "&_=" + Date.now();
    } catch(e) { /* ignore */ }
  }
  function init(node){
    var organizer = node.getAttribute("data-organizer-id");
    var eventId   = node.getAttribute("data-event-id");
    var category  = node.getAttribute("data-category");
    var limit     = node.getAttribute("data-limit") || 6;
    var theme     = node.getAttribute("data-theme") || "light";
    var url = API_BASE + "/api/embed/events.json?limit=" + encodeURIComponent(limit);
    if(organizer) url += "&organizer_id=" + encodeURIComponent(organizer);
    if(eventId)   url += "&event_id="    + encodeURIComponent(eventId);
    if(category)  url += "&category="    + encodeURIComponent(category);
    node.innerHTML = '<div style="color:#999;font:13px ui-sans-serif;padding:12px;text-align:center">Loading events…</div>';
    fetch(url).then(function(r){ return r.json(); }).then(function(d){ render(node, d, theme, organizer); }).catch(function(){ node.innerHTML = '<div style="color:#c62828;font:13px ui-sans-serif;padding:12px;text-align:center">Couldn\u2019t load events.</div>'; });
  }
  function boot(){
    var nodes = document.querySelectorAll("[data-allsale-events]");
    Array.prototype.forEach.call(nodes, init);
  }
  if (document.readyState === "loading") { document.addEventListener("DOMContentLoaded", boot); } else { boot(); }
})();
""".replace("__API_BASE__", api_base)


@router.get("/embed/events.js")
async def embed_events_loader():
    """Vanilla-JS widget loader."""
    js = _build_loader_js()
    return Response(
        content=js,
        media_type="application/javascript; charset=utf-8",
        headers={
            "Cache-Control": "public, max-age=600",  # 10-min CDN cache
            "Access-Control-Allow-Origin": "*",
        },
    )


@router.get("/embed/track")
async def embed_track(
    request: Request,
    organizer_id: Optional[str] = None,
    event_id: Optional[str] = None,
    kind: str = "impression",  # impression | click
):
    """1x1 GIF tracking pixel. Counts widget impressions/clicks by source
    host so organizers see which external sites drive their traffic.

    Loaded from `<img>` tags injected by the widget at render time
    (impression) and from `click` handlers on each event card (click).

    Best-effort logging — never errors back to the embedder.
    """
    try:
        host = _host_from_url(request.headers.get("referer"))
        ua = (request.headers.get("user-agent") or "")[:200]
        ip = request.client.host if request.client else None
        # Cap kind to known values to avoid log spam.
        kind_norm = "click" if kind == "click" else "impression"
        await db.embed_events.insert_one({
            "organizer_id": organizer_id,
            "event_id": event_id,
            "host": host,
            "kind": kind_norm,
            "user_agent": ua,
            "ip": ip,
            "at": utc_now().isoformat(),
        })
    except Exception:  # noqa: BLE001 — never break the pixel
        pass
    return Response(
        content=_PIXEL_GIF,
        media_type="image/gif",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Access-Control-Allow-Origin": "*",
        },
    )


@router.get("/organizer/embed/analytics")
async def organizer_embed_analytics(
    days: int = 30,
    user: dict = Depends(get_current_user),
):
    """Rollup of widget impressions + clicks for the calling organizer's
    events over the last `days` days. Returns:
      - totals (impressions, clicks, ctr_pct)
      - by_host (top 10 referring hosts)
      - by_event (top 10 events by impressions)
      - daily (per-day series, oldest → newest)
    """
    await require_role(user, "organizer", "admin")
    days = max(1, min(180, int(days or 30)))
    since = (utc_now() - timedelta(days=days)).isoformat()

    pipeline = [
        {"$match": {"organizer_id": user["user_id"], "at": {"$gte": since}}},
        {"$facet": {
            "totals": [
                {"$group": {"_id": "$kind", "n": {"$sum": 1}}},
            ],
            "by_host": [
                {"$match": {"host": {"$ne": None}}},
                {"$group": {
                    "_id": "$host",
                    "impressions": {"$sum": {"$cond": [{"$eq": ["$kind", "impression"]}, 1, 0]}},
                    "clicks": {"$sum": {"$cond": [{"$eq": ["$kind", "click"]}, 1, 0]}},
                }},
                {"$sort": {"impressions": -1}},
                {"$limit": 10},
            ],
            "by_event": [
                {"$match": {"event_id": {"$ne": None}}},
                {"$group": {
                    "_id": "$event_id",
                    "impressions": {"$sum": {"$cond": [{"$eq": ["$kind", "impression"]}, 1, 0]}},
                    "clicks": {"$sum": {"$cond": [{"$eq": ["$kind", "click"]}, 1, 0]}},
                }},
                {"$sort": {"impressions": -1}},
                {"$limit": 10},
            ],
            "daily": [
                {"$group": {
                    "_id": {"$substr": ["$at", 0, 10]},
                    "impressions": {"$sum": {"$cond": [{"$eq": ["$kind", "impression"]}, 1, 0]}},
                    "clicks": {"$sum": {"$cond": [{"$eq": ["$kind", "click"]}, 1, 0]}},
                }},
                {"$sort": {"_id": 1}},
            ],
        }},
    ]
    agg = [doc async for doc in db.embed_events.aggregate(pipeline)]
    facet = agg[0] if agg else {"totals": [], "by_host": [], "by_event": [], "daily": []}

    totals = {t["_id"]: t["n"] for t in (facet.get("totals") or [])}
    impressions = int(totals.get("impression", 0))
    clicks = int(totals.get("click", 0))
    ctr_pct = round((clicks * 100 / impressions), 2) if impressions else 0.0

    # Hydrate event titles for the by_event rollup.
    event_titles: dict = {}
    event_ids = [b["_id"] for b in (facet.get("by_event") or []) if b.get("_id")]
    if event_ids:
        async for e in db.events.find({"event_id": {"$in": event_ids}}, {"_id": 0, "event_id": 1, "title": 1}):
            event_titles[e["event_id"]] = e.get("title")

    return {
        "days": days,
        "totals": {
            "impressions": impressions,
            "clicks": clicks,
            "ctr_pct": ctr_pct,
        },
        "by_host": [
            {"host": b["_id"], "impressions": b["impressions"], "clicks": b["clicks"]}
            for b in (facet.get("by_host") or [])
        ],
        "by_event": [
            {
                "event_id": b["_id"],
                "title": event_titles.get(b["_id"], "—"),
                "impressions": b["impressions"],
                "clicks": b["clicks"],
            }
            for b in (facet.get("by_event") or [])
        ],
        "daily": [
            {"date": b["_id"], "impressions": b["impressions"], "clicks": b["clicks"]}
            for b in (facet.get("daily") or [])
        ],
    }
