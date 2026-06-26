"""Pydantic request/response models."""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, EmailStr, ConfigDict


class RegisterIn(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: str = "attendee"  # attendee | organizer
    # Phone is required for all new accounts (operational + safety + WhatsApp).
    # Validation is intentionally lenient — international numbers, no E.164 enforcement.
    phone: str = Field(..., min_length=6, max_length=20)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    user_id: str
    email: str
    name: str
    role: str
    picture: Optional[str] = None


class EventIn(BaseModel):
    title: str
    description: str
    category: str
    venue: str
    city: str
    # ISO 3166-1 alpha-2 (e.g. "NZ", "IN", "AE"). Optional for backward compat
    # — events created before this field existed default to NZ.
    country: str = "NZ"
    # IANA tz (e.g. "Pacific/Auckland", "Asia/Kolkata"). When omitted, the
    # event's date string is treated as UTC. Powers per-visitor local-time
    # conversion on the event detail page.
    timezone: Optional[str] = None
    date: str
    # Optional explicit end timestamp (ISO 8601). Required by Google Event
    # rich-results — if omitted on the frontend, we derive `endDate` as
    # `date + 3h` for the Schema.org JSON-LD. Organisers can override here.
    end_date: Optional[str] = None
    image_url: str
    banner_url: Optional[str] = None
    # Optional promo video URL — accepts YouTube / Vimeo / Instagram / direct
    # mp4. Rendered as an embedded player below the cover banner.
    promo_video_url: Optional[str] = None
    # Optional vertical poster (9:16 ratio works best) — shown as a thumbnail
    # in the sidebar next to ticket info. Mirrors Eventfinda's layout.
    poster_url: Optional[str] = None
    currency: str = "NZD"  # ISO 4217. Drives event pricing, checkout, payouts.
    tiers: List[Dict[str, Any]] = Field(default_factory=list)
    has_seatmap: bool = False
    seat_rows: int = 0
    seat_cols: int = 0
    seat_price: float = 0.0
    aisles: List[str] = Field(default_factory=list)
    seat_map_image_url: Optional[str] = None
    # Theatre-style enhancements (all optional; existing events unaffected)
    seatmap_curved: bool = False  # render rows as curved arc
    seatmap_numbering_rtl: bool = False  # number seats right-to-left (cinemas in India/ME)
    seatmap_sections: List[Dict[str, Any]] = Field(default_factory=list)
    # List of {after_row: int (0-indexed, e.g. 4 means break after row E), label: str}
    seatmap_categories: Dict[str, List[str]] = Field(default_factory=dict)
    # Per-seat category map: {"wheelchair": ["A-1","A-2"], "house":[...], "disabled":[...], "vip":[...], "premium":[...]}
    seatmap_category_prices: Dict[str, float] = Field(default_factory=dict)
    # Per-category seat price overrides: {"vip": 80.0, "premium": 60.0, "wheelchair": 40.0, "disabled": 40.0, "house": 0.0}
    # Falls back to seat_price (event level) when a category isn't priced here.
    seatmap_row_offsets: Dict[str, int] = Field(default_factory=dict)
    # Per-row label offset: {"C": 2} means row C's seat at grid col 3 displays as label "1" (col - offset).
    # Used when a row is visually indented under a wider front row (e.g. cinemas).
    seatmap_custom_labels: Dict[str, str] = Field(default_factory=dict)
    # Per-seat custom label override: {"A-3": "AA3", "B-1": "Box-1"}. When present,
    # the frontend shows this value instead of the computed "row+col-offset" label.
    # Seat IDs (the keys) stay column-indexed — only the displayed label changes.
    seatmap_backdrop_opacity: float = 0.4  # 0.0–1.0
    seatmap_backdrop_offset_y: int = 0
    seatmap_backdrop_offset_x: int = 0
    seatmap_backdrop_scale: float = 1.0  # 0.4–2.5
    # Refund-window policy. None / disabled = organizer handles refunds
    # manually. When enabled, attendees can self-serve a refund up to
    # `hours_before_event` hours before the event start; the refund_pct is
    # the % of `face_value` returned (Stripe + platform fees are non-refundable
    # by default). Backwards compatible — unset = no self-serve refunds.
    refund_policy: Optional[Dict[str, Any]] = None  # {enabled,hours_before_event,refund_pct}
    auto_promo_disabled: bool = False  # opt out of the FIRST50 auto-promo
    # Open influencer marketplace — when True, any influencer can self-join
    # this event's affiliate program with the default commission %.
    affiliate_program_open: bool = False
    affiliate_default_commission_pct: float = 5.0
    # Group-booking auto-discount: when buyers purchase >= `min_qty` tickets in
    # one go they get `pct_off` % off automatically. Set min_qty=0 to disable.
    group_discount: Optional[Dict[str, Any]] = None  # {min_qty: int, pct_off: float}
    # Admin-only: when set, the event is attributed to this organizer instead
    # of the caller. Silently ignored when the caller isn't an admin. Enables
    # admins to set up events on behalf of an organizer who can't or won't.
    on_behalf_of_organizer_id: Optional[str] = None


class HoldIn(BaseModel):
    event_id: str
    tier_name: Optional[str] = None
    quantity: int = 1
    seats: Optional[List[str]] = None
    code: Optional[str] = Field(default=None, max_length=24)  # optional discount code
    gift_card_code: Optional[str] = Field(default=None, max_length=32)  # optional gift card
    # Ticket Protection — buyer opt-in. Adds TICKET_PROTECTION_PCT (default
    # 6.5%) on top of the buyer total. Refunds are routed through the admin
    # claim flow in /admin → Ticket Protection.
    protection_opted: bool = False


class CheckoutIn(BaseModel):
    booking_id: str
    origin_url: str


class GoogleSessionIn(BaseModel):
    session_id: str
