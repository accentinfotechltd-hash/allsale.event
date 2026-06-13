"""Pydantic request/response models."""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, EmailStr, ConfigDict


class RegisterIn(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: str = "attendee"  # attendee | organizer


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
    date: str
    image_url: str
    banner_url: Optional[str] = None
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


class HoldIn(BaseModel):
    event_id: str
    tier_name: Optional[str] = None
    quantity: int = 1
    seats: Optional[List[str]] = None
    code: Optional[str] = Field(default=None, max_length=24)  # optional discount code


class CheckoutIn(BaseModel):
    booking_id: str
    origin_url: str


class GoogleSessionIn(BaseModel):
    session_id: str
