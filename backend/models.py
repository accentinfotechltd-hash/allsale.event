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
    tiers: List[Dict[str, Any]] = Field(default_factory=list)
    has_seatmap: bool = False
    seat_rows: int = 0
    seat_cols: int = 0
    seat_price: float = 0.0
    aisles: List[str] = Field(default_factory=list)
    seat_map_image_url: Optional[str] = None


class HoldIn(BaseModel):
    event_id: str
    tier_name: Optional[str] = None
    quantity: int = 1
    seats: Optional[List[str]] = None


class CheckoutIn(BaseModel):
    booking_id: str
    origin_url: str


class GoogleSessionIn(BaseModel):
    session_id: str
