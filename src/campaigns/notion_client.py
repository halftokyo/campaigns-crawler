from __future__ import annotations

import os
from datetime import datetime
from typing import Iterable, List, Dict
import re
import json

try:
    from notion_client import Client
except Exception:  # pragma: no cover - optional dependency at runtime
    Client = None  # type: ignore


def _client() -> Client | None:  # type: ignore
    token = os.getenv("NOTION_TOKEN")
    if not token or Client is None:
        return None
    return Client(auth=token)

_HEX32_RE = re.compile(r"([0-9a-f]{32})", re.I)


def _hyphenate_notion_id(raw: str) -> str:
    s = raw.replace("-", "").lower()
    if len(s) != 32:
        return raw
    return f"{s[0:8]}-{s[8:12]}-{s[12:16]}-{s[16:20]}-{s[20:32]}"


def _database_id_from_env() -> str | None:
    db_id = os.getenv("NOTION_DATABASE_ID")
    if db_id:
        return _hyphenate_notion_id(db_id)
    url = os.getenv("NOTION_DATABASE_URL")
    if not url:
        return None
    m = _HEX32_RE.search(url)
    if not m:
        return None
    return _hyphenate_notion_id(m.group(1))


def _prop_map_from_env() -> Dict[str, str]:
    # logical keys -> notion property names
    defaults = {
        "name": "Name",
        "provider": "Provider",
        "category": "Category",
        "reward_type": "Reward Type",
        "reward_value": "Reward Value",
        "deadline": "Deadline",
        "source_url": "Source URL",
        "external_id": "External ID",
        "last_checked": "LastChecked",
        "status": "Status",
    }
    raw = os.getenv("NOTION_PROP_MAP")
    if raw:
        try:
            overrides = json.loads(raw)
            if isinstance(overrides, dict):
                defaults.update({k: str(v) for k, v in overrides.items()})
        except Exception:
            pass
    # individual overrides
    for k in list(defaults.keys()):
        env_key = f"NOTION_PROP_{k.upper()}"
        if os.getenv(env_key):
            defaults[k] = os.getenv(env_key) or defaults[k]
    return defaults


def upsert_to_notion(items: Iterable[dict]) -> None:
    db_id = _database_id_from_env()
    cli = _client()
    if not cli or not db_id:
        print("[info] Notion not configured. Skip upsert.")
        return

    now_iso = datetime.utcnow().isoformat()
    pm = _prop_map_from_env()

    for it in items:
        eid = it.get("external_id")
        if not eid:
            continue
        # query existing by External ID rich text
        res = cli.databases.query(
            **{
                "database_id": db_id,
                "filter": {
                    "property": "External ID",
                    "rich_text": {"equals": eid},
                },
                "page_size": 1,
            }
        )
        props = {
            pm["name"]: {"title": [{"text": {"content": it.get("name", "")}}]},
            pm["provider"]: {"rich_text": [{"text": {"content": it.get("provider", "")}}]},
            pm["category"]: {"rich_text": [{"text": {"content": it.get("category", "")}}]},
            pm["reward_type"]: {"select": {"name": it.get("reward_type") or ""}},
            pm["reward_value"]: {"rich_text": [{"text": {"content": it.get("reward_value") or ""}}]},
            pm["deadline"]: {"date": {"start": it.get("deadline")}} if it.get("deadline") else {"date": None},
            pm["source_url"]: {"url": it.get("source_url")},
            pm["external_id"]: {"rich_text": [{"text": {"content": eid}}]},
            pm["last_checked"]: {"date": {"start": now_iso}},
            pm["status"]: {"select": {"name": _status_from_deadline(it.get("deadline"))}},
        }

        if res.get("results"):
            page_id = res["results"][0]["id"]
            cli.pages.update(page_id=page_id, properties=props)  # type: ignore
        else:
            cli.pages.create(  # type: ignore
                **{
                    "parent": {"database_id": db_id},
                    "properties": props,
                }
            )


def archive_by_external_ids(external_ids: Iterable[str], *, archive_page: bool = False, set_status: bool = True) -> None:
    db_id = _database_id_from_env()
    cli = _client()
    if not cli or not db_id:
        print("[info] Notion not configured. Skip archive.")
        return

    for eid in external_ids:
        res = cli.databases.query(  # type: ignore
            **{
                "database_id": db_id,
                "filter": {"property": _prop_map_from_env()["external_id"], "rich_text": {"equals": eid}},
                "page_size": 1,
            }
        )
        if not res.get("results"):
            continue
        page_id = res["results"][0]["id"]
        payload = {}
        if set_status:
            payload.setdefault("properties", {})
            payload["properties"][ _prop_map_from_env()["status"] ] = {"select": {"name": "失效"}}
        if archive_page:
            payload["archived"] = True
        if payload:
            cli.pages.update(page_id=page_id, **payload)  # type: ignore


def _status_from_deadline(deadline: str | None) -> str:
    if not deadline:
        return "需人工确认"


def ensure_database_schema() -> None:
    cli = _client()
    db_id = _database_id_from_env()
    if not cli or not db_id:
        print("[info] Notion not configured. Skip schema ensure.")
        return

    pm = _prop_map_from_env()
    try:
        db = cli.databases.retrieve(database_id=db_id)  # type: ignore
    except Exception as e:  # pragma: no cover - network
        print(f"[warn] retrieve database failed: {e}")
        return

    existing: Dict[str, dict] = db.get("properties", {})
    to_update: Dict[str, dict] = {}

    # ensure title name matches desired
    desired_title = pm["name"]
    existing_title_name = None
    for name, spec in existing.items():
        if spec.get("type") == "title" or ("title" in spec):
            existing_title_name = name
            break
    if existing_title_name and existing_title_name != desired_title:
        to_update[existing_title_name] = {"name": desired_title}

    # helper to add property if missing
    def add_missing(prop_name: str, spec: dict) -> None:
        if prop_name not in existing and prop_name not in to_update:
            to_update[prop_name] = spec

    # desired properties
    add_missing(pm["provider"], {"rich_text": {}})
    add_missing(pm["category"], {"rich_text": {}})
    add_missing(pm["reward_type"], {"select": {"options": [{"name": "积分"}, {"name": "现金"}]}})
    add_missing(pm["reward_value"], {"rich_text": {}})
    add_missing(pm["deadline"], {"date": {}})
    add_missing(pm["source_url"], {"url": {}})
    add_missing(pm["external_id"], {"rich_text": {}})
    add_missing(pm["last_checked"], {"date": {}})
    add_missing(pm["status"], {
        "select": {
            "options": [
                {"name": "有效", "color": "green"},
                {"name": "需人工确认", "color": "yellow"},
                {"name": "失效", "color": "red"},
            ]
        }
    })

    if to_update:
        try:
            cli.databases.update(database_id=db_id, properties=to_update)  # type: ignore
            print("[ok] ensured Notion database properties.")
        except Exception as e:  # pragma: no cover - network
            print(f"[warn] update database schema failed: {e}")
    try:
        d = datetime.fromisoformat(deadline).date()
        return "有效" if d >= datetime.utcnow().date() else "需人工确认"
    except Exception:
        return "需人工确认"
