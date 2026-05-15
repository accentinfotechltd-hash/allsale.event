"""Demo seed: admin, organizer, attendee users + 8 demo events."""
import uuid
from datetime import timedelta

from core import db, hash_password, utc_now, ADMIN_EMAIL, ADMIN_PASSWORD, logger

DEMO_EVENTS = [
    {
        "title": "Midnight Echoes — Live in Concert",
        "category": "music", "city": "Auckland", "venue": "Spark Arena",
        "description": "An immersive sonic journey under neon lights. Featuring Midnight Echoes with full band, strings, and synths. Doors at 7pm. Limited VIP front-row available.",
        "image_url": "https://images.unsplash.com/photo-1470229722913-7c0e2dbbafd3?w=1200",
        "banner_url": "https://images.unsplash.com/photo-1470229722913-7c0e2dbbafd3?w=1920",
        "tiers": [
            {"name": "Early Bird", "price": 45.0, "capacity": 100},
            {"name": "General", "price": 75.0, "capacity": 500},
            {"name": "VIP", "price": 180.0, "capacity": 50},
        ],
        "featured": True,
    },
    {
        "title": "Stand-Up Saturday: The Roast",
        "category": "comedy", "city": "Wellington", "venue": "The Opera House",
        "description": "Six of NZ's sharpest comedians take the stage for a no-holds-barred night of stand-up, improv, and live audience roasting.",
        "image_url": "https://images.unsplash.com/photo-1527224538127-2104bb71c51b?w=1200",
        "banner_url": "https://images.unsplash.com/photo-1527224538127-2104bb71c51b?w=1920",
        "has_seatmap": True, "seat_rows": 8, "seat_cols": 12, "seat_price": 55.0,
        "aisles": [f"{r}-{c}" for r in "ABCDEFGH" for c in (6, 7)],
        "tiers": [], "featured": True,
    },
    {
        "title": "AllBlacks vs Wallabies — Bledisloe Cup",
        "category": "sports", "city": "Auckland", "venue": "Eden Park",
        "description": "The biggest rivalry in rugby returns. Witness history at Eden Park as the All Blacks battle the Wallabies for the Bledisloe Cup.",
        "image_url": "https://images.unsplash.com/photo-1517649763962-0c623066013b?w=1200",
        "banner_url": "https://images.unsplash.com/photo-1517649763962-0c623066013b?w=1920",
        "tiers": [
            {"name": "General", "price": 95.0, "capacity": 2000},
            {"name": "Premium", "price": 220.0, "capacity": 400},
            {"name": "Corporate Box", "price": 650.0, "capacity": 20},
        ],
        "featured": True,
    },
    {
        "title": "Hamilton — The Musical",
        "category": "theater", "city": "Auckland", "venue": "Civic Theatre",
        "description": "The award-winning Broadway musical comes to Auckland for a limited season. A revolutionary story told through hip-hop, R&B, and pop.",
        "image_url": "https://images.unsplash.com/photo-1503095396549-807759245b35?w=1200",
        "banner_url": "https://images.unsplash.com/photo-1503095396549-807759245b35?w=1920",
        "has_seatmap": True, "seat_rows": 10, "seat_cols": 14, "seat_price": 120.0,
        "aisles": [f"{r}-{c}" for r in "ABCDEFGHIJ" for c in (5, 10)],
        "tiers": [], "featured": False,
    },
    {
        "title": "Future//Stack — Devs Conference 2026",
        "category": "tech", "city": "Wellington", "venue": "TSB Arena",
        "description": "Two days of talks, workshops, and demos from the world's leading developers. Topics: AI, edge computing, Rust, distributed systems.",
        "image_url": "https://images.unsplash.com/photo-1540575467063-178a50c2df87?w=1200",
        "banner_url": "https://images.unsplash.com/photo-1540575467063-178a50c2df87?w=1920",
        "tiers": [
            {"name": "Early Bird", "price": 199.0, "capacity": 200},
            {"name": "General", "price": 349.0, "capacity": 1000},
            {"name": "VIP Pass", "price": 899.0, "capacity": 50},
        ],
        "featured": True,
    },
    {
        "title": "Ceramics Studio Weekend",
        "category": "workshops", "city": "Christchurch", "venue": "The Clay House",
        "description": "Two days of hands-on ceramics with master potter Lena Voss. All materials included. Take home three finished pieces.",
        "image_url": "https://images.unsplash.com/photo-1565193566173-7a0ee3dbe261?w=1200",
        "banner_url": "https://images.unsplash.com/photo-1565193566173-7a0ee3dbe261?w=1920",
        "tiers": [{"name": "Workshop Pass", "price": 145.0, "capacity": 20}],
        "featured": False,
    },
    {
        "title": "Splendour Open Air Festival",
        "category": "festivals", "city": "Queenstown", "venue": "Lake Wakatipu Grounds",
        "description": "Three stages, 40+ artists, sunset over the lake. The South Island's biggest open-air music festival returns for its 8th year.",
        "image_url": "https://images.unsplash.com/photo-1459749411175-04bf5292ceea?w=1200",
        "banner_url": "https://images.unsplash.com/photo-1459749411175-04bf5292ceea?w=1920",
        "tiers": [
            {"name": "Day Pass", "price": 89.0, "capacity": 3000},
            {"name": "Weekend Pass", "price": 199.0, "capacity": 2000},
            {"name": "VIP Camping", "price": 499.0, "capacity": 100},
        ],
        "featured": True,
    },
    {
        "title": "Modernism Reframed — Art Exhibit",
        "category": "arts", "city": "Auckland", "venue": "Auckland Art Gallery",
        "description": "A curated retrospective of 20th-century modernist works. Guided tours hourly. Wine reception included.",
        "image_url": "https://images.unsplash.com/photo-1547891654-e66ed7ebb968?w=1200",
        "banner_url": "https://images.unsplash.com/photo-1547891654-e66ed7ebb968?w=1920",
        "tiers": [
            {"name": "General", "price": 28.0, "capacity": 500},
            {"name": "Member", "price": 18.0, "capacity": 200},
        ],
        "featured": False,
    },
]


async def seed_demo():
    if not await db.users.find_one({"email": ADMIN_EMAIL}):
        await db.users.insert_one({
            "user_id": f"user_{uuid.uuid4().hex[:12]}",
            "email": ADMIN_EMAIL, "name": "AURA Admin", "role": "admin",
            "password_hash": hash_password(ADMIN_PASSWORD), "picture": None,
            "created_at": utc_now().isoformat(), "auth_provider": "password",
        })
    org = await db.users.find_one({"email": "organizer@aura.events"})
    if not org:
        org_id = f"user_{uuid.uuid4().hex[:12]}"
        await db.users.insert_one({
            "user_id": org_id, "email": "organizer@aura.events",
            "name": "AURA Productions", "role": "organizer",
            "password_hash": hash_password("organizer123"), "picture": None,
            "created_at": utc_now().isoformat(), "auth_provider": "password",
        })
    else:
        org_id = org["user_id"]

    if not await db.users.find_one({"email": "attendee@aura.events"}):
        await db.users.insert_one({
            "user_id": f"user_{uuid.uuid4().hex[:12]}",
            "email": "attendee@aura.events", "name": "Demo Attendee", "role": "attendee",
            "password_hash": hash_password("attendee123"), "picture": None,
            "created_at": utc_now().isoformat(), "auth_provider": "password",
        })

    if await db.events.count_documents({}) == 0:
        for i, e in enumerate(DEMO_EVENTS):
            date = utc_now() + timedelta(days=15 + i * 7)
            await db.events.insert_one({
                "event_id": f"evt_{uuid.uuid4().hex[:12]}",
                "organizer_id": org_id, "organizer_name": "AURA Productions",
                "title": e["title"], "description": e["description"],
                "category": e["category"], "venue": e["venue"], "city": e["city"],
                "date": date.isoformat(),
                "image_url": e["image_url"], "banner_url": e["banner_url"],
                "tiers": e.get("tiers", []),
                "has_seatmap": e.get("has_seatmap", False),
                "seat_rows": e.get("seat_rows", 0),
                "seat_cols": e.get("seat_cols", 0),
                "seat_price": e.get("seat_price", 0.0),
                "aisles": e.get("aisles", []),
                "seat_map_image_url": e.get("seat_map_image_url"),
                "status": "approved", "featured": e.get("featured", False),
                "created_at": utc_now().isoformat(),
            })
        logger.info("Seeded demo events")
