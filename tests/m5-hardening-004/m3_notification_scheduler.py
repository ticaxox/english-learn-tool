#!/usr/bin/env python3
"""Live scheduler notification check for T-QA-002."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import asyncpg

import m3_api as h


async def main() -> int:
    client = h.Client()
    pg: asyncpg.Connection | None = None
    wordbook = None
    admin_token = None
    member = None
    try:
        pg = await asyncpg.connect(h.PG_DSN)
        admin = h.rotate(client, os.environ.get("LIVE_ADMIN_USERNAME", "qa_m3_ai_admin"), os.environ["LIVE_ADMIN_PASSWORD"], prefix="scheduler-admin")
        admin_token = admin["session"]["access_token"]
        stamp = datetime.now(UTC).strftime("%H%M%S")
        username = f"qa_m3_scheduler_{stamp}"
        password = "Qa-M3-Scheduler-2026!x"
        h.create_member(client, admin_token, username=username, password=password, display="M3 Scheduler")
        member = h.rotate(client, username, password, prefix=username)
        entries = [
            ("scheduled1", "/ˈskedʒuːld/", "adj.", "预定的", "planned", "The task is scheduled."),
            ("scheduled2", "/ˈskedʒuːld/", "adj.", "已安排的", "arranged", "The meeting is arranged."),
        ]
        wordbook = h.import_book(client, admin_token, name=f"T-QA-002 Scheduler {stamp}", entries=entries)
        client.request("POST", f"/wordbooks/{wordbook['id']}/activate", label="scheduler-activate", token=member["session"]["access_token"], expect=200)
        client.request("PATCH", "/users/me/profile", label="scheduler-profile", token=member["session"]["access_token"], json={"daily_new_words": 5, "daily_study_minutes": 15}, expect=200)
        today = client.request("POST", "/learning/daily-plan/ensure", label="scheduler-plan", token=member["session"]["access_token"], expect=200).json()
        plan_id = await pg.fetchval("SELECT id FROM daily_plans WHERE user_id=$1", uuid.UUID(member["session"]["user"]["id"]))
        entry_id = uuid.UUID(today["items"][0]["entry_id"])
        state_id = uuid.uuid4()
        await pg.execute("""
            INSERT INTO user_word_states (id,user_id,wordbook_id,entry_id,status,fsrs_card,algorithm_version,due_at,review_count,lapse_count,created_at,updated_at)
            VALUES ($1,$2,$3,$4,'review','{}'::jsonb,'fsrs-6.3.2',$5,1,0,now(),now())
            """, state_id, uuid.UUID(member["session"]["user"]["id"]), uuid.UUID(wordbook["id"]), entry_id, datetime.now(UTC) - timedelta(hours=1))
        yesterday = datetime.now(ZoneInfo("Asia/Shanghai")).date() - timedelta(days=1)
        await pg.execute("INSERT INTO daily_activities (user_id,local_date,active_seconds,heartbeat_count) VALUES ($1,$2,60,2)", uuid.UUID(member["session"]["user"]["id"]), yesterday)
        client.request("PUT", "/notifications/preferences", label="scheduler-prefs", token=member["session"]["access_token"], json={"categories": {"due_review": True, "today_incomplete": True, "streak_risk": True, "ai_completed": True, "ai_failed": True, "plan_adjusted": True, "ai_action": True}, "dnd_start": "00:00", "dnd_end": "00:00", "daily_limit": 20, "timezone": "Asia/Shanghai"}, expect=200)

        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
        from app.core.config import Settings
        from app.services.notifications import enqueue_scheduled_notification_events, process_notification_outbox
        engine = create_async_engine(h.SQLALCHEMY_DSN, pool_pre_ping=True)
        factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
        now = datetime.now(ZoneInfo("Asia/Shanghai"))
        try:
            async with factory() as session:
                first = await enqueue_scheduled_notification_events(session, Settings(), now=now)
                await process_notification_outbox(session, Settings(), now=now)
                second = await enqueue_scheduled_notification_events(session, Settings(), now=now)
                await process_notification_outbox(session, Settings(), now=now)
        finally:
            await engine.dispose()
        rows = await pg.fetch("SELECT category,status FROM notifications WHERE user_id=$1 AND category = ANY($2::text[])", uuid.UUID(member["session"]["user"]["id"]), ["due_review", "today_incomplete", "streak_risk"])
        by_category = {row["category"]: row["status"] for row in rows}
        h.EVIDENCE.check("notifications.scheduler-events-live", first >= 3 and second == 0 and by_category.get("due_review") == "sent" and by_category.get("today_incomplete") == "sent" and by_category.get("streak_risk") == "sent", first_created=first, second_created=second, statuses=by_category)
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
        if admin_token and wordbook:
            cleanup = h.Client()
            try:
                deleted = cleanup.request("DELETE", f"/wordbooks/{wordbook['id']}", label="scheduler-cleanup-wordbook", token=admin_token, idempotency_key=h.new_key("cleanup"), json={"confirm_name": wordbook["name"]}, expect=202).json()
                for _ in range(120):
                    job = cleanup.request("GET", f"/wordbooks/jobs/{deleted['job_id']}", label="scheduler-cleanup-poll", token=admin_token, expect=200).json()
                    if job["status"] in {"succeeded", "failed", "cancelled"}:
                        break
                    await asyncio.sleep(0.4)
            finally:
                cleanup.close()
    path = h.RUN_DIR / "scheduler-notifications.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"\nRESULT={result['status']} evidence={path}")
    return status


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
