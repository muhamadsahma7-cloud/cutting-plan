"""Supabase integration — reuses the same project's auth + tables as web/script.js.

Tables (already exist in the Supabase project used by the Netlify app):
  profiles(user_id, email, created_at)
  user_plans(user_id, plan, end_date)
  projects(id, user_id, name, data jsonb, updated_at)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import streamlit as st
from supabase import Client, create_client

TRIAL_DAYS = 7
ADMIN_EMAIL = "muhamadsahma@gmail.com"

# Same public project URL/anon key already embedded in web/script.js.
# An anon key is meant to be public — real access control lives in Supabase RLS.
_DEFAULT_URL = "https://qaiwtwyvnrquwsatnffv.supabase.co"
_DEFAULT_ANON_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InFhaXd0d3l2bnJxdXdzYXRuZmZ2Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzIyODU4NTMsImV4cCI6MjA4Nzg2MTg1M30.3V3gYy-6IAC0x7yL8h0K8ECUNkdzkpWhE_U2A4TtVq0"
)


def _secret(key: str, default: str) -> str:
    # st.secrets.get() raises StreamlitSecretNotFoundError (not caught by
    # Mapping.get's KeyError handling) when no secrets.toml exists at all,
    # so fall back to the default explicitly instead of relying on .get().
    try:
        return st.secrets[key]
    except Exception:
        return default


def get_client() -> Client:
    if "sb_client" not in st.session_state:
        url = _secret("SUPABASE_URL", _DEFAULT_URL)
        key = _secret("SUPABASE_ANON_KEY", _DEFAULT_ANON_KEY)
        st.session_state.sb_client = create_client(url, key)
    return st.session_state.sb_client


def sign_in(email: str, password: str) -> tuple[bool, str]:
    sb = get_client()
    try:
        res = sb.auth.sign_in_with_password({"email": email, "password": password})
        if res.user is None:
            return False, "Invalid email or password."
        st.session_state.sb_user = res.user
        st.session_state.sb_session = res.session
        upsert_profile(res.user.id, res.user.email)
        return True, ""
    except Exception as exc:  # noqa: BLE001 - surface auth errors to the UI
        return False, str(exc)


def sign_up(email: str, password: str) -> tuple[bool, str]:
    sb = get_client()
    try:
        res = sb.auth.sign_up({"email": email, "password": password})
        if res.user is None:
            return False, "Sign up failed."
        return True, "Account created. Check your email to confirm, then sign in."
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def sign_out() -> None:
    sb = get_client()
    try:
        sb.auth.sign_out()
    except Exception:  # noqa: BLE001 - best effort
        pass
    for key in ("sb_user", "sb_session", "materials", "current_project_id", "selected_material_id"):
        st.session_state.pop(key, None)


def upsert_profile(user_id: str, email: str) -> None:
    sb = get_client()
    try:
        sb.table("profiles").upsert({"user_id": user_id, "email": email}, on_conflict="user_id").execute()
    except Exception:  # noqa: BLE001 - profile bookkeeping is non-critical
        pass


def get_access_status(user_id: str, created_at: str) -> dict[str, Any]:
    """Mirrors the trial/plan logic in web/script.js's admin panel."""
    sb = get_client()
    now = datetime.now(timezone.utc)
    try:
        res = sb.table("user_plans").select("plan, end_date").eq("user_id", user_id).limit(1).execute()
        plan_row = res.data[0] if res.data else None
    except Exception:  # noqa: BLE001
        plan_row = None

    if plan_row:
        end = datetime.fromisoformat(plan_row["end_date"].replace("Z", "+00:00"))
        days_left = (end - now).days
        return {"plan": plan_row["plan"], "daysLeft": days_left, "active": days_left > 0, "isTrial": False}

    created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    trial_end = created.fromtimestamp(created.timestamp() + TRIAL_DAYS * 86400, tz=timezone.utc)
    days_left = (trial_end - now).days
    return {"plan": "trial", "daysLeft": days_left, "active": days_left > 0, "isTrial": True}


def list_projects() -> list[dict]:
    sb = get_client()
    res = sb.table("projects").select("id, name, updated_at").order("updated_at", desc=True).execute()
    return res.data or []


def load_project(project_id: str) -> dict | None:
    sb = get_client()
    res = sb.table("projects").select("id, name, data").eq("id", project_id).single().execute()
    return res.data


def create_project(user_id: str, name: str, data: dict) -> str:
    sb = get_client()
    res = sb.table("projects").insert({"user_id": user_id, "name": name, "data": data}).select("id").execute()
    return res.data[0]["id"]


def save_project(project_id: str, name: str, data: dict) -> None:
    sb = get_client()
    sb.table("projects").update({"name": name, "data": data}).eq("id", project_id).execute()


def rename_project(project_id: str, name: str) -> None:
    sb = get_client()
    sb.table("projects").update({"name": name}).eq("id", project_id).execute()


def delete_project(project_id: str) -> None:
    sb = get_client()
    sb.table("projects").delete().eq("id", project_id).execute()


# ── Admin panel (mirrors web/script.js's ADMIN_EMAIL-gated admin tab) ───────

def list_all_profiles() -> list[dict]:
    sb = get_client()
    res = sb.table("profiles").select("user_id, email, created_at").order("created_at", desc=True).execute()
    return res.data or []


def list_all_user_plans() -> list[dict]:
    sb = get_client()
    res = sb.table("user_plans").select("user_id, plan, end_date").execute()
    return res.data or []


def admin_set_plan(user_id: str, plan: str, end_date_iso: str) -> None:
    sb = get_client()
    sb.table("user_plans").upsert(
        {"user_id": user_id, "plan": plan, "end_date": end_date_iso}, on_conflict="user_id"
    ).execute()
