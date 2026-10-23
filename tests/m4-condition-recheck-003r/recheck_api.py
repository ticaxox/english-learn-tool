#!/usr/bin/env python3
"""Focused T-QA-003R API, cross-container, and browser recheck runner."""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import asyncpg
import httpx

HERE = Path(__file__).resolve().parent
REPO_ROOT = Path(os.environ.get("REPO_ROOT", HERE.parents[1])).resolve()
DEFAULT_RUNTIME_ENV = (
    r"E:\agent workspace\英语学习工具\ai-workspace\10-collaboration"
    r"\sessions\A30-TEST\temp\m4r-runtime\runtime.env"
)
RUNTIME_ENV = Path(os.environ.get("RUNTIME_ENV", DEFAULT_RUNTIME_ENV)).resolve()
os.environ["RUNTIME_ENV"] = str(RUNTIME_ENV)
os.environ.setdefault("LIVE_API_BASE_URL", "http://127.0.0.1:8096")
os.environ.setdefault("LIVE_WEB_BASE_URL", "http://127.0.0.1:8097")
os.environ.setdefault("LIVE_PROVIDER_CONTROL_URL", "http://127.0.0.1:18083")
os.environ.setdefault("LIVE_PROVIDER_BASE_URL", "http://a30-m4r-provider:18080/v1")
os.environ.setdefault(
    "EVIDENCE_DIR",
    r"E:\agent workspace\英语学习工具\ai-workspace\04-qa\evidence\T-QA-003R",
)
os.environ.setdefault("LIVE_RUN_ID", f"m4r-{datetime.now(UTC):%Y%m%d%H%M%S}")
for _line in RUNTIME_ENV.read_text(encoding="utf-8").splitlines():
    if "=" in _line:
        _name, _value = _line.split("=", 1)
        os.environ.setdefault(_name, _value)
os.environ.setdefault(
    "LIVE_PG_DSN",
    f"postgresql://english_learn:{os.environ.get('POSTGRES_PASSWORD', '')}"
    "@127.0.0.1:55448/english_learn_m4r",
)
os.environ.setdefault("LIVE_REDIS_URL", "redis://127.0.0.1:55449/0")

sys.path.insert(0, str(HERE.parent / "m4-learning-int"))
import m4_api as base  # noqa: E402

base.EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
base.RUN_DIR.mkdir(parents=True, exist_ok=True)
base.LOG_DIR.mkdir(parents=True, exist_ok=True)
(base.EVIDENCE_ROOT / "runtime").mkdir(parents=True, exist_ok=True)

SHANGHAI = ZoneInfo("Asia/Shanghai")
STARTED_AT = datetime.now(UTC).isoformat()


def check(name: str, condition: bool, **details: object) -> bool:
    return base.EVIDENCE.check(name, condition, **details)


def note(name: str, **details: object) -> None:
    base.EVIDENCE.note(name, **details)


def provider_modes(modes: dict[str, str], default: str = "ok") -> None:
    base.set_provider_modes(modes, default=default)


async def main() -> int:
    client = base.Client()
    pg: asyncpg.Connection | None = None
    try:
        pg = await asyncpg.connect(base.PG_DSN)
        ready = await asyncio.to_thread(
            httpx.get,
            f"{base.API_BASE.rsplit('/api/v1', 1)[0]}/health/ready",
            timeout=30,
        )
        ready_body = ready.json()
        check(
            "environment.real-pg16-redis7",
            ready_body.get("status") == "ready"
            and ready_body.get("components", {}).get("database", {}).get("status") == "ok"
            and ready_body.get("components", {}).get("redis", {}).get("status") == "ok",
            postgres=(await pg.fetchval("SELECT version()")).split(" on ")[0],
        )
        openapi = client.request("GET", "/openapi.json", label="openapi", expect=200).json()
        check(
            "contract.openapi.m4r",
            openapi.get("openapi") == "3.1.0"
            and len(openapi.get("paths", {})) == 84
            and len(openapi.get("components", {}).get("schemas", {})) == 153,
            paths=len(openapi.get("paths", {})),
            schemas=len(openapi.get("components", {}).get("schemas", {})),
        )

        admin = base.rotate(
            client,
            os.environ.get("LIVE_ADMIN_USERNAME", "qa_m4r_admin"),
            os.environ["LIVE_ADMIN_PASSWORD"],
            prefix="admin",
        )
        admin_token = str(admin["session"]["access_token"])
        stamp = datetime.now(UTC).strftime("%H%M%S")
        specs = {
            "api": ("Core", f"qa_m4r_api_{stamp}", "Qa-M4R-Api-2026!x"),
            "ui": ("Core", f"qa_m4r_ui_{stamp}", "Qa-M4R-Ui-2026!x"),
            "other": ("Core", f"qa_m4r_other_{stamp}", "Qa-M4R-Other-2026!x"),
            "small1": ("Small", f"qa_m4r_small1_{stamp}", "Qa-M4R-Small1-2026!x"),
            "small2": ("Small", f"qa_m4r_small2_{stamp}", "Qa-M4R-Small2-2026!x"),
            "single": ("Single", f"qa_m4r_single_{stamp}", "Qa-M4R-Single-2026!x"),
        }
        members: dict[str, dict[str, object]] = {}
        for name, (group, username, password) in specs.items():
            base.create_member(
                client,
                admin_token,
                username=username,
                password=password,
                display=f"M4R {name}",
                department="QA",
                learning_group=group,
            )
            rotated = base.rotate(client, username, password, prefix=username)
            members[name] = {
                "id": rotated["session"]["user"]["id"],
                "username": username,
                "password": rotated["password"],
                "token": rotated["session"]["access_token"],
                "group": group,
            }

        entries = [
            (
                "harbor",
                "/ˈhɑːbə/",
                "n.",
                "港口",
                "a place where ships shelter",
                "The harbor is quiet.",
            ),
            ("lantern", "/ˈlæntən/", "n.", "灯笼", "a portable light", "The lantern glows."),
            ("meadow", "/ˈmedəʊ/", "n.", "草地", "a grassy field", "The meadow is green."),
            (
                "orchard",
                "/ˈɔːtʃəd/",
                "n.",
                "果园",
                "a place with fruit trees",
                "The orchard blooms.",
            ),
            ("pebble", "/ˈpebl/", "n.", "鹅卵石", "a small stone", "A pebble rolled."),
            ("quiver", "/ˈkwɪvə/", "v.", "颤抖", "to shake slightly", "The leaves quiver."),
            ("ripple", "/ˈrɪpl/", "n.", "涟漪", "a small wave", "A ripple crossed the pond."),
            ("thrive", "/θraɪv/", "v.", "茁壮成长", "to grow well", "Plants thrive here."),
        ]
        wordbook = base.import_book(
            client, admin_token, name=f"T-QA-003R Wordbook {stamp}", entries=entries
        )
        headwords = {str(item["id"]): item["headword"] for item in wordbook["entries"]}
        check("setup.wordbook", len(headwords) == 8, entries=len(headwords))

        for name in ("api", "ui", "other", "single"):
            base.activate_and_plan(
                client,
                str(members[name]["token"]),
                wordbook_id=str(wordbook["id"]),
                daily_new_words=5,
                study_minutes=30,
            )
        check("setup.plans", True)

        primary_key = "sk-m4r-primary-" + secrets.token_urlsafe(18)
        provider_modes({primary_key: "ok"})
        provider = base.create_provider(
            client,
            admin_token,
            name=f"M4R Provider {stamp}",
            api_key=primary_key,
            model_id="fake-m4-model",
        )
        tested = client.request(
            "POST",
            f"/admin/ai/providers/{provider['id']}/test",
            label="provider-test",
            token=admin_token,
            expect=200,
        ).json()
        check("provider.ready", tested.get("success") is True, provider=provider["name"])

        created = client.request(
            "POST",
            "/coach/conversations",
            label="coach-conversation-create",
            token=str(members["api"]["token"]),
            json={"title": "COACH-TITLE-SECRET"},
            expect=201,
        ).json()
        conversation_id = created["id"]
        coach_key = base.new_key("m4r-coach")
        content = "请调整今日计划：25 个新词，45 分钟。"
        accepted = base.send_coach_message(
            client,
            str(members["api"]["token"]),
            conversation_id,
            key=coach_key,
            content=content,
            label="coach-message",
        )
        replay = base.send_coach_message(
            client,
            str(members["api"]["token"]),
            conversation_id,
            key=coach_key,
            content=content,
            label="coach-message-replay",
        )
        conflict = client.request(
            "POST",
            f"/coach/conversations/{conversation_id}/messages",
            label="coach-message-conflict",
            token=str(members["api"]["token"]),
            idempotency_key=coach_key,
            json={"content": "不同内容", "page_context": {"page_route": "/coach"}},
        )
        final = base.wait_message(
            client,
            str(members["api"]["token"]),
            accepted["message_id"],
            label="coach-message",
        )
        receipt = final["actions"][0]
        stream = client.request(
            "GET",
            f"/coach/streams/{accepted['message_id']}",
            label="coach-stream",
            token=str(members["api"]["token"]),
            expect=200,
        )
        event_types = {event.get("event") for event in base.parse_sse(stream.text)}
        undone = client.request(
            "POST",
            f"/coach/action-receipts/{receipt['id']}/undo",
            label="coach-undo",
            token=str(members["api"]["token"]),
            expect=200,
        ).json()
        check(
            "coach.regression-sse-action-undo-idempotency",
            replay["message_id"] == accepted["message_id"]
            and conflict.status_code == 409
            and final["status"] == "completed"
            and receipt["status"] == "applied"
            and undone["receipt"]["status"] == "undone"
            and {"message.delta", "action.applied", "usage", "done"}.issubset(event_types),
            events=sorted(event_types),
        )
        usage_row = await pg.fetchrow(
            "SELECT l.local_date, j.created_at, l.consumed "
            "FROM ai_usage_ledger l JOIN ai_jobs j ON j.id=l.job_id "
            "WHERE l.user_id=$1 AND l.quota_kind='coach_messages' "
            "ORDER BY j.created_at DESC LIMIT 1",
            uuid.UUID(str(members["api"]["id"])),
        )
        shanghai_today = datetime.now(SHANGHAI).date()
        usage_default = client.request(
            "GET", "/admin/ai/usage", label="ai-usage-default", token=admin_token, expect=200
        ).json()
        usage_explicit = client.request(
            "GET",
            "/admin/ai/usage",
            label="ai-usage-explicit",
            token=admin_token,
            params={"date_from": shanghai_today.isoformat(), "date_to": shanghai_today.isoformat()},
            expect=200,
        ).json()
        default_coach = next(
            item for item in usage_default["quotas"] if item["quota_kind"] == "coach_messages"
        )
        explicit_coach = next(
            item for item in usage_explicit["quotas"] if item["quota_kind"] == "coach_messages"
        )
        check(
            "usage.shanghai-default-cross-day",
            usage_row is not None
            and usage_row["local_date"] == shanghai_today
            and usage_default["date_to"] == shanghai_today.isoformat()
            and usage_explicit["date_to"] == shanghai_today.isoformat()
            and default_coach["consumed"] >= 1
            and explicit_coach["consumed"] == default_coach["consumed"],
            utc_created=(usage_row["created_at"].isoformat() if usage_row else None),
            shanghai_date=shanghai_today.isoformat(),
            default_date_to=usage_default["date_to"],
            consumed=default_coach["consumed"],
        )

        base_params = {"department": "QA"}
        zero = client.request(
            "GET",
            "/admin/dashboard",
            label="dashboard-zero",
            token=admin_token,
            params={**base_params, "learning_group": "NoMembers"},
            expect=200,
        ).json()
        one = client.request(
            "GET",
            "/admin/dashboard",
            label="dashboard-one",
            token=admin_token,
            params={**base_params, "learning_group": "Single"},
            expect=200,
        ).json()
        two = client.request(
            "GET",
            "/admin/dashboard",
            label="dashboard-two",
            token=admin_token,
            params={**base_params, "learning_group": "Small"},
            expect=200,
        ).json()
        three = client.request(
            "GET",
            "/admin/dashboard",
            label="dashboard-three",
            token=admin_token,
            params={**base_params, "learning_group": "Core"},
            expect=200,
        ).json()
        member_dashboard = client.request(
            "GET",
            "/admin/dashboard",
            label="dashboard-member",
            token=str(members["api"]["token"]),
        )
        zero_ok = (
            zero["privacy"]["suppressed"] is False
            and zero["metrics"]["total_members"] == 0
            and zero["trend"] == []
            and zero["groups"] == []
        )
        one_ok = one["privacy"]["suppressed"] is True and one["metrics"]["total_members"] == 1
        two_ok = two["privacy"]["suppressed"] is True and two["metrics"]["total_members"] == 2
        three_ok = (
            three["privacy"]["suppressed"] is False and three["metrics"]["total_members"] == 3
        )
        check(
            "dashboard.zero-one-two-three-distinction",
            zero_ok and one_ok and two_ok and three_ok and member_dashboard.status_code == 403,
            zero=(zero["privacy"], zero["metrics"]["total_members"]),
            one=(one["privacy"], one["metrics"]["total_members"]),
            two=(two["privacy"], two["metrics"]["total_members"]),
            three=(three["privacy"], three["metrics"]["total_members"]),
        )
        default_dashboard_text = json.dumps(
            client.request(
                "GET",
                "/admin/dashboard",
                label="dashboard-all",
                token=admin_token,
                expect=200,
            ).json(),
            ensure_ascii=False,
        )
        check(
            "dashboard.privacy-no-member-content",
            "COACH-TITLE-SECRET" not in default_dashboard_text
            and "COACH-CONTENT-SECRET" not in default_dashboard_text,
        )

        ui_token = str(members["ui"]["token"])
        generated = client.request(
            "POST",
            "/challenges/today/generate",
            label="challenge-generate",
            token=ui_token,
            expect=202,
        ).json()
        generated_job = base.poll_job(
            client, ui_token, generated["job_id"], label="challenge-generate"
        )
        challenge = client.request(
            "GET", "/challenges/today", label="challenge-today", token=ui_token, expect=200
        ).json()
        main_nodes = sorted(
            [item for item in challenge["nodes"] if not item.get("optional")],
            key=lambda item: item["order_index"],
        )
        check(
            "challenge.regression-map-contract",
            generated_job["status"] == "succeeded"
            and challenge["status"] == "ready"
            and 3 <= len(main_nodes) <= 6
            and main_nodes[-1]["node_type"] == "BOSS",
            nodes=len(main_nodes),
        )
        for index, node in enumerate(main_nodes[:-1], start=1):
            if node["node_type"] in {"REVIEW", "NEW_WORDS", "WORD_DRILL", "OPTIONAL_SIDE"}:
                base.complete_challenge_memory_node(
                    client,
                    ui_token,
                    challenge["id"],
                    node["id"],
                    entry_headwords=headwords,
                    label=f"challenge-node-{index}",
                )
        boss = main_nodes[-1]
        boss_started = client.request(
            "POST",
            f"/challenges/{challenge['id']}/nodes/{boss['id']}/start",
            label="boss-start",
            token=ui_token,
            expect=200,
        ).json()
        boss_session = base.poll_practice(
            client, ui_token, boss_started["resource_id"], label="boss-practice"
        )
        check(
            "challenge.boss-ready-for-browser",
            boss_started["resource_type"] == "practice"
            and boss_session["status"] == "ready"
            and len(boss_session["questions"]) in {5, 10},
            questions=len(boss_session["questions"]),
        )

        browser_state = {
            "web_base_url": base.WEB_BASE,
            "admin": {
                "username": admin["session"]["user"]["username"],
                "password": admin["password"],
            },
            "member_ui": {
                "username": members["ui"]["username"],
                "password": members["ui"]["password"],
            },
            "challenge_id": challenge["id"],
            "boss_node_id": boss["id"],
            "boss_session_id": boss_session["id"],
            "run_id": base.RUN_ID,
        }
        state_path = base.RUNTIME_ENV.parent / "m4r_browser_state.json"
        state_path.write_text(
            json.dumps(browser_state, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        browser_script = HERE / "recheck_browser.mjs"
        browser_env = os.environ.copy()
        browser_env.update(
            {
                "RECHECK_STATE": str(state_path),
                "EVIDENCE_DIR": str(base.EVIDENCE_ROOT),
                "LIVE_RUN_ID": base.RUN_ID,
                "LIVE_WEB_BASE_URL": base.WEB_BASE,
            }
        )
        browser_log = base.LOG_DIR / f"{base.RUN_ID}-browser.log"
        completed = await asyncio.to_thread(
            subprocess.run,
            [os.environ.get("NODE_EXE", "node"), str(browser_script)],
            cwd=str(REPO_ROOT),
            env=browser_env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=420,
            check=False,
        )
        browser_log.write_text(
            (completed.stdout or "") + ("\n" + completed.stderr if completed.stderr else ""),
            encoding="utf-8",
        )
        browser_path = base.RUN_DIR / "browser-acceptance.json"
        browser_result = (
            json.loads(browser_path.read_text(encoding="utf-8"))
            if browser_path.exists()
            else {"status": "FAIL", "checks": []}
        )
        base.EVIDENCE.artifacts["browser"] = {
            "status": browser_result.get("status"),
            "exit_code": completed.returncode,
            "checks": len(browser_result.get("checks", [])),
            "log": str(browser_log.relative_to(base.EVIDENCE_ROOT)),
        }
        check(
            "browser.condition-closure",
            browser_result.get("status") == "PASS"
            and completed.returncode == 0
            and all(item.get("status") == "PASS" for item in browser_result.get("checks", [])),
            status=browser_result.get("status"),
            exit_code=completed.returncode,
            checks=len(browser_result.get("checks", [])),
            gaps=len(browser_result.get("gaps", [])),
        )

        final_challenge = client.request(
            "GET",
            f"/challenges/{challenge['id']}",
            label="challenge-final",
            token=ui_token,
            expect=200,
        ).json()
        final_result = client.request(
            "GET",
            f"/practice/sessions/{boss_session['id']}/result",
            label="boss-result",
            token=ui_token,
            expect=200,
        ).json()
        check(
            "challenge.boss-persisted-completion",
            final_challenge["status"] == "completed"
            and final_challenge["main_completed"] == final_challenge["main_total"]
            and final_result["status"] == "completed",
            main=(final_challenge["main_completed"], final_challenge["main_total"]),
            result_status=final_result["status"],
        )
        check(
            "all.tqa003r-conditions-closed",
            all(item["status"] == "PASS" for item in base.EVIDENCE.checks),
            checks=len(base.EVIDENCE.checks),
            requests=len(base.EVIDENCE.network),
        )
        result = base.EVIDENCE.finish()
        result["task"] = "T-QA-003R"
        result["phase"] = "M4R"
        result["started_at"] = STARTED_AT
        status = 0
    except Exception as exc:
        import traceback

        traceback.print_exc()
        result = base.EVIDENCE.finish(error=f"{type(exc).__name__}: {exc}")
        result["task"] = "T-QA-003R"
        result["phase"] = "M4R"
        status = 1
    finally:
        if pg is not None:
            await pg.close()
        client.close()

    result_path = base.RUN_DIR / "api-acceptance.json"
    result_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8"
    )
    print(f"\nRESULT={result['status']} evidence={result_path}")
    return status


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
