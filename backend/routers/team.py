"""Team management — organizers add other users as collaborators.

Three permission levels:
    co_organizer  → full rights (edit event, refunds, analytics, check-in)
    manager       → edit event + analytics + check-in (no refunds / payouts)
    door_staff    → check-in only (use shareable scanner links for non-users)

Two scopes:
    event         → access to one specific event
    organization  → access to ALL the organizer's events

A member is keyed by email. If the email is already a registered user, they
get access instantly. Otherwise an invite email is sent and the record is
stored with status="invited" and member_user_id=None — when that user later
signs up with the matching email, `attach_pending_team_invites()` runs and
upgrades the records to status="active".
"""
from __future__ import annotations

import uuid
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr

from core import db, get_current_user, require_role, utc_now
from emails import send_template_fireforget

router = APIRouter(prefix="/organizer/team", tags=["organizer-team"])

VALID_ROLES = ("co_organizer", "manager", "door_staff")
VALID_SCOPES = ("event", "organization")


# ---------------------------------------------------------------------------
# Permissions helper — re-used by other routers via direct import.
# ---------------------------------------------------------------------------
async def get_user_team_role(user_id: str, event: dict) -> Optional[str]:
    """Return the team role this user has for the event, or None.

    The role can come from a per-event grant OR an organization-wide grant by
    the event's owner. Owners and admins are not handled here — use
    `user_can_manage_event()` for the combined check.
    """
    # Per-event grant
    rec = await db.team_members.find_one(
        {
            "scope": "event",
            "event_id": event["event_id"],
            "member_user_id": user_id,
            "status": "active",
        },
        {"_id": 0, "role": 1},
    )
    if rec:
        return rec.get("role")
    # Org-wide grant for THIS event's owner
    rec = await db.team_members.find_one(
        {
            "scope": "organization",
            "owner_user_id": event["organizer_id"],
            "member_user_id": user_id,
            "status": "active",
        },
        {"_id": 0, "role": 1},
    )
    if rec:
        return rec.get("role")
    return None


async def user_can_manage_event(
    user: dict,
    event: dict,
    *,
    required: Literal["co_organizer", "manager", "door_staff"] = "manager",
) -> bool:
    """True if the user is the owner, an admin, or has at least `required` rights."""
    if user.get("role") == "admin":
        return True
    if event["organizer_id"] == user["user_id"]:
        return True
    granted = await get_user_team_role(user["user_id"], event)
    if not granted:
        return False
    # Ladder: co_organizer ≥ manager ≥ door_staff
    rank = {"door_staff": 1, "manager": 2, "co_organizer": 3}
    return rank.get(granted, 0) >= rank.get(required, 0)


async def attach_pending_team_invites(user_doc: dict) -> int:
    """Call after a user signs up — flip status invited→active on records for their email."""
    res = await db.team_members.update_many(
        {"member_email": user_doc["email"], "status": "invited"},
        {"$set": {"member_user_id": user_doc["user_id"], "status": "active",
                  "accepted_at": utc_now().isoformat()}},
    )
    return res.modified_count


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class TeamAddIn(BaseModel):
    email: EmailStr
    role: str  # co_organizer | manager | door_staff
    event_id: Optional[str] = None  # if provided → scope=event; else organization-wide


async def _assert_can_grant(user: dict, event_id: Optional[str]) -> Optional[dict]:
    """Owner of the event (or admin) can grant for that event.
    For organization-wide grants, any organizer can manage their own team."""
    await require_role(user, "organizer", "admin")
    if event_id:
        event = await db.events.find_one({"event_id": event_id}, {"_id": 0})
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")
        if event["organizer_id"] != user["user_id"] and user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Only the event owner can manage its team")
        return event
    return None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@router.get("")
async def list_my_team(user: dict = Depends(get_current_user)):
    """Every team member this organizer has added — across all scopes."""
    await require_role(user, "organizer", "admin")
    items = []
    async for r in db.team_members.find(
        {"owner_user_id": user["user_id"]}, {"_id": 0}
    ).sort("added_at", -1):
        items.append(r)
    return {"items": items, "count": len(items)}


@router.get("/event/{event_id}")
async def list_event_team(event_id: str, user: dict = Depends(get_current_user)):
    """List team members for one event (per-event grants + org-wide grants by the owner)."""
    event = await _assert_can_grant(user, event_id)
    assert event is not None
    items = []
    async for r in db.team_members.find(
        {
            "$or": [
                {"scope": "event", "event_id": event_id},
                {"scope": "organization", "owner_user_id": event["organizer_id"]},
            ]
        },
        {"_id": 0},
    ).sort("added_at", -1):
        items.append(r)
    return {"items": items, "count": len(items)}


@router.post("")
async def add_team_member(payload: TeamAddIn, user: dict = Depends(get_current_user)):
    """Add a team member by email. If the email exists, access is instant.
    Otherwise we send an invitation email and persist a pending record."""
    await require_role(user, "organizer", "admin")
    if payload.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of {VALID_ROLES}")

    event = await _assert_can_grant(user, payload.event_id)
    scope = "event" if payload.event_id else "organization"
    email = str(payload.email).lower().strip()

    if email == user["email"]:
        raise HTTPException(status_code=400, detail="You can't add yourself to your own team")

    # Look up the invited user (may not exist yet)
    invited = await db.users.find_one({"email": email}, {"_id": 0, "password_hash": 0})

    # Reject duplicate (same scope + same email + same event)
    dup_filter = {
        "owner_user_id": user["user_id"],
        "member_email": email,
        "scope": scope,
    }
    if scope == "event":
        dup_filter["event_id"] = payload.event_id
    if await db.team_members.find_one(dup_filter):
        raise HTTPException(status_code=400, detail="That user is already on this team")

    member_id = f"tm_{uuid.uuid4().hex[:12]}"
    doc = {
        "member_id": member_id,
        "owner_user_id": user["user_id"],
        "owner_name": user.get("name"),
        "member_email": email,
        "member_user_id": invited["user_id"] if invited else None,
        "member_name": invited["name"] if invited else None,
        "role": payload.role,
        "scope": scope,
        "event_id": payload.event_id,
        "event_title": event["title"] if event else None,
        "status": "active" if invited else "invited",
        "added_at": utc_now().isoformat(),
        "added_by": user["user_id"],
    }
    await db.team_members.insert_one(doc)

    # Fire-and-forget invitation email
    try:
        send_template_fireforget(
            "team_invitation",
            email,
            {
                "name": invited["name"] if invited else email.split("@")[0],
                "email": email,
                "inviter_name": user.get("name") or user.get("email"),
                "role": payload.role,
                "scope": scope,
                "event_title": event["title"] if event else None,
                "new_user": not bool(invited),
            },
            db,
        )
    except Exception:
        pass

    # Strip _id-prone keys before returning
    out = {k: v for k, v in doc.items() if k != "_id"}
    return out


@router.delete("/{member_id}")
async def remove_team_member(member_id: str, user: dict = Depends(get_current_user)):
    """Remove a team member. Only the owner or admin may revoke."""
    await require_role(user, "organizer", "admin")
    rec = await db.team_members.find_one({"member_id": member_id}, {"_id": 0})
    if not rec:
        raise HTTPException(status_code=404, detail="Team member not found")
    if rec["owner_user_id"] != user["user_id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Only the team owner can remove members")
    await db.team_members.delete_one({"member_id": member_id})
    return {"removed": member_id}
