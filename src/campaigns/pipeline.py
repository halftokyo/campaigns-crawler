from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from .fetch import get
from .models import Campaign
from .parser import parse_html, parse_rss, parse_json
from .utils import make_external_id, normalize_text


DEFAULT_INCLUDE = [
    "新規",
    "口座開設",
    "キャンペーン",
    "ポイント",
    "キャッシュバック",
    "還元",
    "入会",
    "登録",
    "特典",
    "プレゼント",
    "クーポン",
]
DEFAULT_EXCLUDE = ["終了", "終了しました", "抽選のみ"]


def _load_sources(config_path: str | Path) -> List[Dict[str, Any]]:
    with open(config_path, "r", encoding="utf-8") as f:
        arr = json.load(f)
    if not isinstance(arr, list):
        raise ValueError("sources.json must be a list")
    return arr


def _ensure_keywords(src: Dict[str, Any]) -> None:
    if not src.get("include_keywords"):
        src["include_keywords"] = DEFAULT_INCLUDE
    if not src.get("exclude_keywords"):
        src["exclude_keywords"] = DEFAULT_EXCLUDE


def run(
    config_path: str | Path,
    out_path: str | Path,
    *,
    valid_within_days: Optional[int] = None,
    require_deadline: bool = False,
) -> list[Campaign]:
    sources = _load_sources(config_path)
    campaigns: list[Campaign] = []

    for src in sources:
        if src.get("disabled"):
            continue
        _ensure_keywords(src)
        stype = (src.get("source_type") or "html").lower()
        url = src.get("url")
        if not url:
            continue

        try:
            resp = get(url)
        except Exception as e:
            print(f"[warn] fetch failed {url}: {e}")
            continue

        items: list[dict[str, Any]]
        try:
            if stype == "html":
                items = parse_html(src, resp.text, url)
            elif stype == "rss":
                items = parse_rss(src, resp.text)
            elif stype == "json":
                items = parse_json(src, resp.text)
            else:
                print(f"[warn] unknown source_type {stype} for {url}")
                continue
        except Exception as e:
            print(f"[warn] parse failed {url}: {e}")
            continue

        for it in items:
            name = normalize_text(it.get("title") or "")
            if not name:
                continue
            provider = src.get("provider") or ""
            category = src.get("category") or ""
            reward_value = it.get("reward_value")
            reward_type = it.get("reward_type")
            deadline = it.get("deadline")
            source_url = it.get("url")
            eid = make_external_id(provider, name, source_url, reward_value)

            campaigns.append(
                Campaign(
                    name=name,
                    provider=provider,
                    category=category,
                    reward_type=reward_type,
                    reward_value=reward_value,
                    deadline=deadline,
                    source_url=source_url,
                    external_id=eid,
                )
            )

    # de-duplicate by external_id (last one wins)
    uniq: dict[str, Campaign] = {}
    for c in campaigns:
        uniq[c.external_id] = c

    # optional filtering
    items = list(uniq.values())
    if require_deadline or valid_within_days is not None:
        items = _filter_by_deadline(items, valid_within_days, require_deadline)

    out = [c.to_dict() for c in items]
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"[ok] wrote {len(out)} campaigns -> {out_path}")
    return items


def _filter_by_deadline(
    items: list[Campaign], valid_within_days: Optional[int], require_deadline: bool
) -> list[Campaign]:
    today = datetime.utcnow().date()
    window_end = today + timedelta(days=valid_within_days or 0)
    filtered: list[Campaign] = []
    for c in items:
        if not c.deadline:
            if require_deadline:
                continue
            # if not required and no window provided, keep
            if valid_within_days is None:
                filtered.append(c)
            continue
        try:
            d = datetime.fromisoformat(c.deadline).date()
        except Exception:
            if require_deadline:
                continue
            if valid_within_days is None:
                filtered.append(c)
            continue

        # keep if deadline in [today, window_end] when window specified
        if valid_within_days is not None:
            if today <= d <= window_end:
                filtered.append(c)
        else:
            # otherwise keep if not expired
            if d >= today:
                filtered.append(c)
    return filtered
