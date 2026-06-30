"""One-shot harvest: parse Eventfinda venue listings from the in-session
crawl outputs and dump them into recruitment_leads.

Usage:
    python harvest_eventfinda_seed.py

The crawl markdown was captured manually for this run from:
- /whatson/events/auckland
- /whatson/events/wellington-region
- /whatson/events/canterbury
"""
import asyncio
import re
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from core import db, utc_now  # noqa: E402

# Sanitized seed list extracted from the live crawl_tool output.
# Each entry: (venue_name, region/city, source_url, eventfinda_count_hint)
# Counts are approximate — derived from how many times the venue appeared
# across the 3 region pages we sampled (NOT a full Eventfinda audit).
SEED = [
    # ===== AUCKLAND =====
    ("Four Winds Theatre at Due Drop Events Centre", "Manukau City, Auckland", "https://www.eventfinda.co.nz/venue/bnz-theatre-at-due-drop-events-centre-auckland", 1),
    ("Sweet Axe Throwing Co.", "CBD, Auckland", "https://www.eventfinda.co.nz/venue/sweet-axe-throwing-co-auckland3", 1),
    ("The Kingslander", "Kingsland, Auckland", "https://www.eventfinda.co.nz/venue/auckland-the-kingslander", 1),
    ("Botany Town Centre", "Botany Downs, Auckland", "https://www.eventfinda.co.nz/venue/botany-town-centre-square-botany-downs", 1),
    ("Hawkins Theatre", "Papakura, Auckland", "https://www.eventfinda.co.nz/venue/auckland-south-hawkins-theatre", 3),
    ("New Brew Bar and Restaurant", "Albany, Auckland", "https://www.eventfinda.co.nz/venue/auckland-north-new-brew-bar-restaurant", 1),
    ("The Classic Comedy Club", "CBD, Auckland", "https://www.eventfinda.co.nz/venue/auckland-the-classic-comedy-bar", 1),
    ("Continual Store & Fever Vintage Clothing", "Ponsonby, Auckland", "https://www.eventfinda.co.nz/venue/continual-store-fever-vintage-clothing-auckland", 1),
    ("The Wintergarden, The Civic", "CBD, Auckland", "https://www.eventfinda.co.nz/venue/the-wintergarden-beneath-the-civic-theatre-auckland-central", 1),
    ("The Clare Inn", "Mt Eden, Auckland", "https://www.eventfinda.co.nz/venue/auckland-central-the-clare-inn", 1),
    ("Long Bay Surf Club", "Long Bay, Auckland", "https://www.eventfinda.co.nz/venue/long-bay-surf-club-auckland", 1),
    ("Mr Illingsworth", "Te Atatū Peninsula, Auckland", "https://www.eventfinda.co.nz/venue/mr-illingsworth-auckland", 1),
    ("Gus Fisher Gallery", "CBD, Auckland", "https://www.eventfinda.co.nz/venue/gus-fisher-gallery-auckland-central", 1),
    ("Longroom", "Ponsonby, Auckland", "https://www.eventfinda.co.nz/venue/longroom-bar-ponsonby", 1),
    ("Takapuna Beachside Cinema", "Takapuna, Auckland", "https://www.eventfinda.co.nz/venue/hoyts-cinema-auckland", 2),
    ("Capitol Cinema", "Balmoral, Auckland", "https://www.eventfinda.co.nz/venue/capitol-cinema-auckland", 2),
    ("John Barleycorns Taphouse", "Newmarket, Auckland", "https://www.eventfinda.co.nz/venue/john-barleycorns-taphouse-auckland3", 1),
    ("Phoenix Cabaret", "Newton, Auckland", "https://www.eventfinda.co.nz/venue/phoenix-cabaret-auckland", 1),
    ("Mezze Bar", "CBD, Auckland", "https://www.eventfinda.co.nz/venue/mezze-bar-auckland", 1),
    ("Milford Senior Citizens Hall", "Milford, Auckland", "https://www.eventfinda.co.nz/venue/milford-senior-citizens-hall-north-shore-milford", 1),
    ("Helensville Showgrounds", "Helensville, Auckland", "https://www.eventfinda.co.nz/venue/helensville-showgrounds-helensville", 1),
    ("Orewa Community Centre", "Orewa, Auckland", "https://www.eventfinda.co.nz/venue/orewa-community-centre-auckland-north", 1),
    ("Jubilee Building - Parnell Community Centre", "Parnell, Auckland", "https://www.eventfinda.co.nz/venue/auckland-jubilee-building", 1),
    ("Auckland Horticultural Centre", "Western Springs, Auckland", "https://www.eventfinda.co.nz/venue/auckland-horticultural-centre-auckland-central", 1),
    ("Manurewa Market", "Manurewa, Auckland", "https://www.eventfinda.co.nz/venue/manurewa-market-auckland-south-manurewa", 1),

    # ===== WELLINGTON =====
    ("Whisky & Wood", "Wellington", "https://www.eventfinda.co.nz/venue/whisky-wood", 1),
    ("Hannah Playhouse", "Wellington", "https://www.eventfinda.co.nz/venue/hannah-playhouse-wellington", 2),
    ("Two/Fiftyseven", "Wellington", "https://www.eventfinda.co.nz/venue/two-fiftyseven-wellington", 1),
    ("Sweet Axe Throwing Co.", "Wellington", "https://www.eventfinda.co.nz/venue/sweet-axe-throwing-co-wellington2", 1),
    ("Toi Aro Arts Centre", "Wellington", "https://www.eventfinda.co.nz/venue/toi-aro-gallery-wellington", 1),
    ("The Fringe Bar", "Wellington", "https://www.eventfinda.co.nz/venue/the-fringe-bar-wellington", 1),
    ("Stonehenge Aotearoa", "Carterton, Wairarapa", "https://www.eventfinda.co.nz/venue/stonehenge-aotearoa-wellington-carterton", 4),
    ("Aperitif Wine Bar", "Greytown, Wairarapa", "https://www.eventfinda.co.nz/venue/aperitif-wine-bar-greytown", 1),
    ("St Andrews on the Terrace", "Wellington", "https://www.eventfinda.co.nz/venue/st-andrews-on-the-terrace-wellington", 1),
    ("The Thistle Inn", "Wellington", "https://www.eventfinda.co.nz/venue/wellington-the-thistle-inn", 2),
    ("Valhalla", "Wellington", "https://www.eventfinda.co.nz/venue/valhalla-wellington", 1),
    ("Te Matapihi ki te Ao Nui", "Wellington", "https://www.eventfinda.co.nz/venue/te-matapihi-ki-te-ao-nui-wellington", 1),
    ("The Old Bailey", "Wellington", "https://www.eventfinda.co.nz/venue/the-old-bailey-wellington", 1),
    ("Rathkeale College Auditorium", "Masterton, Wairarapa", "https://www.eventfinda.co.nz/venue/rathkeale-college-masterton", 1),
    ("Hutt Valley High School", "Lower Hutt", "https://www.eventfinda.co.nz/venue/hutt-valley-high-school-lower-hutt", 1),
    ("Rewa Rewa Station", "Masterton, Wairarapa", "https://www.eventfinda.co.nz/venue/rewa-rewa-station-masterton", 1),
    ("Meow Nui", "Wellington", "https://www.eventfinda.co.nz/venue/meow-nui-wellington", 1),
    ("Kelburn Village Pub", "Wellington", "https://www.eventfinda.co.nz/venue/kelburn-village-pub-wellington", 1),
    ("Wharekauhau Country Estate", "Featherston, Wairarapa", "https://www.eventfinda.co.nz/venue/wharekauhau-country-estate-wairarapa", 1),
    ("Amador", "Wellington", "https://www.eventfinda.co.nz/venue/amador-wellington", 1),
    ("Dowse Square", "Lower Hutt", "https://www.eventfinda.co.nz/venue/dowse-square-lower-hutt", 1),
    ("Street Eats", "Upper Hutt", "https://www.eventfinda.co.nz/venue/street-eats-upper-hutt3", 1),

    # ===== CANTERBURY =====
    ("McCombs Performing Arts Centre", "Christchurch", "https://www.eventfinda.co.nz/venue/mccombs-performing-arts-centre-christchurch", 1),
    ("Cathedral Square", "Christchurch", "https://www.eventfinda.co.nz/venue/cathedral-square-christchurch", 1),
    ("Parakiore Recreation and Sports Centre", "Christchurch", "https://www.eventfinda.co.nz/venue/parakiore-recreation-and-sports-centre-christchurch", 1),
    ("Crazy Horse Restaurant & Bar", "Christchurch", "https://www.eventfinda.co.nz/venue/crazy-horse-restaurant-bar-christchurch", 1),
    ("The Brewers", "Christchurch", "https://www.eventfinda.co.nz/venue/the-brewers-christchurch", 1),
    ("Muy Muy", "Christchurch", "https://www.eventfinda.co.nz/venue/muy-muy-christchurch", 2),
    ("Ara Institute of Canterbury", "Timaru, South Canterbury", "https://www.eventfinda.co.nz/venue/ara-institute-of-canterbury", 1),
    ("Timaru Squash Club", "Timaru, South Canterbury", "https://www.eventfinda.co.nz/venue/timaru-squash-club", 1),
    ("Catholic Pro-Cathedral", "Christchurch", "https://www.eventfinda.co.nz/venue/catholic-pro-cathedral-christchurch", 1),
    ("The Riccs", "Christchurch", "https://www.eventfinda.co.nz/venue/the-riccs-christchurch", 1),
    ("The Rock Rolleston", "Rolleston, Selwyn", "https://www.eventfinda.co.nz/venue/the-rock-rolleston", 1),
    ("Climate Action Campus", "Christchurch", "https://www.eventfinda.co.nz/venue/climate-action-campus-christchurch", 2),
    ("Workspace Studios", "Christchurch", "https://www.eventfinda.co.nz/venue/workspace-studios-christchurch", 1),
    ("Darkroom", "Christchurch", "https://www.eventfinda.co.nz/venue/darkroom-christchurch", 2),
    ("Columbus Coffee Hornby", "Christchurch", "https://www.eventfinda.co.nz/venue/columbus-coffee-hornby-christchurch", 1),
    ("McDonald's Merivale", "Christchurch", "https://www.eventfinda.co.nz/venue/mcdonaldrs-merivale-christchurch-city", 1),
    ("Just Desserts", "Christchurch", "https://www.eventfinda.co.nz/venue/just-desserts-christchurch-city", 1),
    ("The Good Home", "Christchurch", "https://www.eventfinda.co.nz/venue/the-good-home-christchurch2", 1),
    ("Scenic Hotel Cotswold", "Christchurch", "https://www.eventfinda.co.nz/venue/scenic-hotel-cotswold-christchurch3", 1),
    ("Bridie's Bar & Bistro", "Christchurch", "https://www.eventfinda.co.nz/venue/bridies-bar-bistro-christchurch", 1),
    ("James Hay Theatre, Christchurch Town Hall", "Christchurch", "https://www.eventfinda.co.nz/venue/james-hay-theatre-christchurch", 1),
    ("The Piano", "Christchurch", "https://www.eventfinda.co.nz/venue/the-piano-christchurch", 2),
    ("Renegade Brewing Co.", "Christchurch", "https://www.eventfinda.co.nz/venue/renegade-brewing-co-christchurch", 1),
    ("Wolfbrook Arena", "Christchurch", "https://www.eventfinda.co.nz/venue/wolfbrook-arena-christchurch", 1),
]


def _slug_email(venue_name: str) -> str:
    """Generate a *placeholder* email so the lead row passes our schema
    requirements. Admin will overwrite with the real email once they
    research it. Using a structured placeholder so it's obvious it's a
    research-needed lead."""
    slug = re.sub(r"[^a-z0-9]+", "-", venue_name.lower()).strip("-")[:50]
    return f"research-needed+{slug}@allsale.events"


async def main():
    now = utc_now().isoformat()
    created = updated = skipped = 0
    for name, locality, source_url, event_count in SEED:
        if not name:
            skipped += 1
            continue
        email = _slug_email(name)
        existing = await db.recruitment_leads.find_one({"email": email})
        if existing:
            await db.recruitment_leads.update_one(
                {"email": email},
                {"$set": {
                    "name": name,
                    "source_url": source_url,
                    "event_count": event_count,
                    "notes": f"Eventfinda venue · {locality} · auto-harvested {now[:10]} · MANUAL: find owner email + replace placeholder",
                    "updated_at": now,
                }},
            )
            updated += 1
        else:
            await db.recruitment_leads.insert_one({
                "lead_id": f"lead_{uuid.uuid4().hex[:10]}",
                "name": name,
                "email": email,
                "source": "eventfinda",
                "source_url": source_url,
                "event_count": event_count,
                "notes": f"Eventfinda venue · {locality} · auto-harvested {now[:10]} · MANUAL: find owner email + replace placeholder",
                "kind": "organizer",
                "status": "new",
                "created_at": now,
                "created_by": "system_eventfinda_harvester",
            })
            created += 1
    print(f"Eventfinda harvest complete — created={created} updated={updated} skipped={skipped} total_seed={len(SEED)}")


if __name__ == "__main__":
    asyncio.run(main())
