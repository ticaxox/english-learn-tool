#!/usr/bin/env python3
"""Minimal T-BE-011 P1 regression smoke on the real Phase B stack."""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

import asyncpg

import phase_b_api as h


async def main() -> int:
    client = h.Client()
    pg: asyncpg.Connection | None = None
    primary: dict | None = None
    small: dict | None = None
    admin_token: str | None = None
    try:
        pg = await asyncpg.connect(h.PG_DSN)
        admin = h.ensure_password_rotated(client, h.ADMIN_USERNAME, h.ADMIN_PASSWORD, label_prefix="p1-admin")
        admin_token = admin["session"]["access_token"]
        stamp = datetime.now(UTC).strftime("%H%M%S")
        username = f"qa_m2b_p1_{stamp}"
        password = "Aa1!" + secrets.token_urlsafe(18)
        h.create_member(client, admin_token, username=username, display_name="M2 P1 Smoke", password=password)
        member = h.ensure_password_rotated(client, username, password, label_prefix=username)
        member_token = member["session"]["access_token"]
        member_id = member["session"]["user"]["id"]

        primary = h.import_book(
            client,
            admin_token,
            name=f"M2 P1 Primary {stamp}",
            entries=[
                ("alpha", "/ˈælfə/", "n.", "阿尔法", "first", "Alpha is first."),
                ("bravo", "/ˈbrɑːvəʊ/", "n.", "布拉沃", "second", "Bravo is second."),
                ("charlie", "/ˈtʃɑːli/", "n.", "查理", "third", "Charlie is third."),
                ("delta", "/ˈdeltə/", "n.", "德尔塔", "fourth", "Delta is fourth."),
            ],
        )
        small = h.import_book(
            client,
            admin_token,
            name=f"M2 P1 Small {stamp}",
            entries=[
                ("echo", "/ˈekəʊ/", "n.", "回声", "fifth", "Echo is fifth."),
                ("foxtrot", "/ˈfɒkstrɒt/", "n.", "狐步", "sixth", "Foxtrot is sixth."),
            ],
        )
        h.activate(client, member_token, primary["id"], label="p1-activate-primary")
        h.patch_profile(client, member_token, {"daily_new_words": 5, "daily_study_minutes": 15}, label="p1-profile")
        plan = h.ensure_today(client, member_token, label="p1-plan")
        h.activate(client, member_token, small["id"], label="p1-activate-small")
        session = h.create_session(client, member_token, "choice", label="p1-new-session-after-switch")
        mismatch = client.request(
            "POST",
            "/memory/sessions",
            label="p1-explicit-mismatch",
            token=member_token,
            json={"module": "choice", "wordbook_id": small["id"]},
        )
        session_mismatches = await h.count(
            pg,
            """
            SELECT count(*) FROM memory_session_items msi
            JOIN memory_sessions ms ON ms.id = msi.session_id
            JOIN wordbook_entries we ON we.id = msi.entry_id
            WHERE ms.id = $1 AND we.wordbook_id <> ms.wordbook_id
            """,
            session["session_id"],
        )
        state_mismatches = await h.count(
            pg,
            """
            SELECT count(*) FROM user_word_states uws
            JOIN wordbook_entries we ON we.id = uws.entry_id
            WHERE uws.user_id = $1 AND uws.wordbook_id <> we.wordbook_id
            """,
            member_id,
        )
        h.EVIDENCE.check("p1.plan-wordbook-is-session-wordbook", session["wordbook_id"] == plan["wordbook_id"], plan=str(plan["wordbook_id"]), session=str(session["wordbook_id"]))
        h.EVIDENCE.check("p1.session-items-match-session-book", session_mismatches == 0, mismatches=session_mismatches)
        h.EVIDENCE.check("p1.user-states-match-entry-book", state_mismatches == 0, mismatches=state_mismatches)
        h.EVIDENCE.check("p1.explicit-mismatch-409", mismatch.status_code == 409 and mismatch.json().get("code") == "MEMORY_WORDBOOK_PLAN_MISMATCH", status=mismatch.status_code, code=mismatch.json().get("code"))
        result = h.EVIDENCE.finish()
        status = 0
    except Exception as exc:
        import traceback
        traceback.print_exc()
        result = h.EVIDENCE.finish(error=f"{type(exc).__name__}: {exc}")
        status = 1
    finally:
        if pg is not None:
            await pg.close()
        client.close()
        if primary and small and admin_token:
            cleanup = h.Client()
            try:
                for book in (primary, small):
                    deleted = cleanup.request("DELETE", f"/wordbooks/{book['id']}", label=f"p1-cleanup-{book['name']}", token=admin_token, idempotency_key=h.new_key("cleanup"), json={"confirm_name": book["name"]}, expect=202).json()
                    h.poll_job(cleanup, admin_token, deleted["job_id"], label=f"p1-cleanup-{book['name']}")
            finally:
                cleanup.close()
    path = h.RUN_DIR / "p1-smoke.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"\nRESULT={result['status']} evidence={path}")
    return status


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
