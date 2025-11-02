from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Optional

from dateutil import parser as dateparser


_WS_RE = re.compile(r"\s+")


def normalize_text(s: str) -> str:
    return _WS_RE.sub(" ", (s or "").strip())


def slugify(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def make_external_id(provider: str, name: str, source_url: str, reward_value: Optional[str] = None) -> str:
    base = f"{provider}|{name}|{source_url}|{reward_value or ''}"
    h = hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]
    return f"{slugify(provider)}:{h}"


_JP_DATE_RE = re.compile(
    r"(?P<y>20\d{2})[年\-/](?P<m>\d{1,2})[月\-/](?P<d>\d{1,2})日?"
)


def parse_date_jp(s: str) -> Optional[str]:
    if not s:
        return None
    s = normalize_text(s)
    m = _JP_DATE_RE.search(s)
    if m:
        y, mth, d = int(m.group("y")), int(m.group("m")), int(m.group("d"))
        try:
            return datetime(y, mth, d).date().isoformat()
        except ValueError:
            pass
    # fallback: try generic parser
    try:
        dt = dateparser.parse(s, dayfirst=False, yearfirst=True)
        if dt:
            return dt.date().isoformat()
    except Exception:
        return None
    return None


_REWARD_RE = re.compile(r"(最大)?\s*([0-9]{1,3}(?:,[0-9]{3})*|[0-9]+)\s*(P|ポイント|円)")


def extract_reward_value(s: str) -> Optional[tuple[str, str]]:
    if not s:
        return None
    m = _REWARD_RE.search(s)
    if not m:
        return None
    value = (m.group(1) or "") + (m.group(2) or "") + (m.group(3) or "")
    unit = m.group(3)
    reward_type = "积分" if unit in ("P", "ポイント") else "现金"
    return normalize_text(value), reward_type


def status_from_deadline(deadline_iso: Optional[str]) -> str:
    if not deadline_iso:
        return "需人工确认"
    try:
        d = datetime.fromisoformat(deadline_iso).date()
        return "有效" if d >= datetime.utcnow().date() else "需人工确认"
    except Exception:
        return "需人工确认"

