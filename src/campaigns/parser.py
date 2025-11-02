from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urljoin
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup

from .utils import normalize_text, parse_date_jp, extract_reward_value


def _match_keywords(text: str, include: List[str], exclude: List[str]) -> bool:
    t = text or ""
    if include and not any(k in t for k in include):
        return False
    if exclude and any(k in t for k in exclude):
        return False
    return True


def parse_html(source: Dict[str, Any], html: str, base_url: str) -> List[Dict[str, Any]]:
    sel = source.get("selectors", {})
    include = source.get("include_keywords", []) or []
    exclude = source.get("exclude_keywords", []) or []

    soup = BeautifulSoup(html, "lxml")

    results: List[Dict[str, Any]] = []

    list_selector = sel.get("list")
    items: Iterable[Any]
    if list_selector:
        items = soup.select(list_selector)
    else:
        items = soup.find_all("a")

    for node in items:
        # Prefer within-node selectors
        title_el = node.select_one(sel.get("title")) if sel.get("title") else node
        link_el = node.select_one(sel.get("link")) if sel.get("link") else node
        date_el = node.select_one(sel.get("date")) if sel.get("date") else None
        reward_el = node.select_one(sel.get("reward")) if sel.get("reward") else None

        title = normalize_text(title_el.get_text(strip=True) if title_el else "")
        href = link_el.get("href") if link_el else None
        if not href:
            continue
        url = urljoin(base_url, href)

        if not _match_keywords(title, include, exclude):
            # try surrounding text for keywords before skipping
            near_text = normalize_text(node.get_text(" ", strip=True))
            if not _match_keywords(near_text, include, exclude):
                continue

        date_text = normalize_text(date_el.get_text(" ", strip=True)) if date_el else normalize_text(node.get_text(" ", strip=True))
        reward_text = normalize_text(reward_el.get_text(" ", strip=True)) if reward_el else title

        deadline = parse_date_jp(date_text)
        reward = extract_reward_value(reward_text)
        reward_value, reward_type = (reward[0], reward[1]) if reward else (None, None)

        results.append(
            {
                "title": title,
                "url": url,
                "deadline": deadline,
                "reward_value": reward_value,
                "reward_type": reward_type,
            }
        )

    return results


def parse_rss(source: Dict[str, Any], xml_text: str) -> List[Dict[str, Any]]:
    include = source.get("include_keywords", []) or []
    exclude = source.get("exclude_keywords", []) or []

    root = ET.fromstring(xml_text)
    results: List[Dict[str, Any]] = []
    for item in root.findall(".//item"):
        title_el = item.find("title")
        link_el = item.find("link")
        date_el = item.find("pubDate")

        title = normalize_text(title_el.text if title_el is not None else "")
        link = normalize_text(link_el.text if link_el is not None else "")
        if not link:
            continue
        if not _match_keywords(title, include, exclude):
            continue

        deadline = parse_date_jp(date_el.text if date_el is not None else "")
        reward = extract_reward_value(title)
        reward_value, reward_type = (reward[0], reward[1]) if reward else (None, None)

        results.append(
            {
                "title": title,
                "url": link,
                "deadline": deadline,
                "reward_value": reward_value,
                "reward_type": reward_type,
            }
        )
    return results


def _json_lookup_path(data: Any, path: str) -> Any:
    cur = data
    for part in (path or "").split("."):
        if not part:
            continue
        if isinstance(cur, list):
            try:
                idx = int(part)
                cur = cur[idx]
            except Exception:
                return None
        elif isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def parse_json(source: Dict[str, Any], json_text: str) -> List[Dict[str, Any]]:
    include = source.get("include_keywords", []) or []
    exclude = source.get("exclude_keywords", []) or []
    path = source.get("json_path") or "items"
    title_key = source.get("json_title_key") or "title"
    link_key = source.get("json_link_key") or "url"
    deadline_key = source.get("json_deadline_key") or "deadline"

    data = json.loads(json_text)
    arr = _json_lookup_path(data, path)
    if not isinstance(arr, list):
        return []

    results: List[Dict[str, Any]] = []
    for obj in arr:
        if not isinstance(obj, dict):
            continue
        title = normalize_text(str(obj.get(title_key, "")))
        link = str(obj.get(link_key) or "")
        if not link:
            continue
        if not _match_keywords(title, include, exclude):
            continue
        dl_raw = obj.get(deadline_key)
        deadline = parse_date_jp(str(dl_raw)) if dl_raw else None
        reward = extract_reward_value(title)
        reward_value, reward_type = (reward[0], reward[1]) if reward else (None, None)
        results.append(
            {
                "title": title,
                "url": link,
                "deadline": deadline,
                "reward_value": reward_value,
                "reward_type": reward_type,
            }
        )
    return results

