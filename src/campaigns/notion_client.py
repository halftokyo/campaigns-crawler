from __future__ import annotations

import os
from datetime import datetime
from typing import Iterable, List

try:
    from notion_client import Client
except Exception:  # pragma: no cover - optional dependency at runtime
    Client = None  # type: ignore


def _client() -> Client | None:  # type: ignore
    token = os.getenv("NOTION_TOKEN")
    if not token or Client is None:
        return None
    return Client(auth=token)


def upsert_to_notion(items: Iterable[dict]) -> None:
    db_id = os.getenv("NOTION_DATABASE_ID")
    cli = _client()
    if not cli or not db_id:
        print("[info] Notion not configured. Skip upsert.")
        return

    now_iso = datetime.utcnow().isoformat()

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
            "Name": {"title": [{"text": {"content": it.get("name", "")}}]},
            "Provider": {"rich_text": [{"text": {"content": it.get("provider", "")}}]},
            "Category": {"rich_text": [{"text": {"content": it.get("category", "")}}]},
            "Reward Type": {"select": {"name": it.get("reward_type") or ""}},
            "Reward Value": {"rich_text": [{"text": {"content": it.get("reward_value") or ""}}]},
            "Deadline": {"date": {"start": it.get("deadline")}} if it.get("deadline") else {"date": None},
            "Source URL": {"url": it.get("source_url")},
            "External ID": {"rich_text": [{"text": {"content": eid}}]},
            "LastChecked": {"date": {"start": now_iso}},
            "Status": {"select": {"name": _status_from_deadline(it.get("deadline"))}},
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
    db_id = os.getenv("NOTION_DATABASE_ID")
    cli = _client()
    if not cli or not db_id:
        print("[info] Notion not configured. Skip archive.")
        return

    for eid in external_ids:
        res = cli.databases.query(  # type: ignore
            **{
                "database_id": db_id,
                "filter": {"property": "External ID", "rich_text": {"equals": eid}},
                "page_size": 1,
            }
        )
        if not res.get("results"):
            continue
        page_id = res["results"][0]["id"]
        payload = {}
        if set_status:
            payload.setdefault("properties", {})
            payload["properties"]["Status"] = {"select": {"name": "失效"}}
        if archive_page:
            payload["archived"] = True
        if payload:
            cli.pages.update(page_id=page_id, **payload)  # type: ignore


def _status_from_deadline(deadline: str | None) -> str:
    if not deadline:
        return "需人工确认"
    try:
        d = datetime.fromisoformat(deadline).date()
        return "有效" if d >= datetime.utcnow().date() else "需人工确认"
    except Exception:
        return "需人工确认"
