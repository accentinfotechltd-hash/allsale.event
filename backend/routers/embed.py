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
"""
from __future__ import annotations

import os
from typing import Optional
from datetime import timedelta

from fastapi import APIRouter
from fastapi.responses import Response

from core import db, utc_now, event_to_public

router = APIRouter(tags=["embed"])

PUBLIC_ORIGIN = os.environ.get("PUBLIC_ORIGIN") or "https://www.allsale.events"


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
  function render(container, data, theme){
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
      });
    }
    container.appendChild(grid);
    container.appendChild(el("div", { style: { textAlign:"right", marginTop:"10px", fontSize:"11px", color: dim } }, [
      el("a", { href: API_BASE, target:"_blank", rel:"noopener", text:"Powered by Allsale Events", style: { color: dim, textDecoration:"none" } })
    ]));
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
    fetch(url).then(function(r){ return r.json(); }).then(function(d){ render(node, d, theme); }).catch(function(){ node.innerHTML = '<div style="color:#c62828;font:13px ui-sans-serif;padding:12px;text-align:center">Couldn\u2019t load events.</div>'; });
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
