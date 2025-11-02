from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime, date
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


ISO_FMT = "%Y-%m-%dT%H:%M:%SZ"


@dataclass
class StateItem:
    external_id: str
    name: str
    provider: str
    deadline: str | None
    source_url: str
    first_seen: str
    last_seen: str
    archived: bool = False


def _now_iso() -> str:
    return datetime.utcnow().strftime(ISO_FMT)


def load_state(path: str | Path) -> Dict[str, StateItem]:
    p = Path(path)
    if not p.exists():
        return {}
    with open(p, "r", encoding="utf-8") as f:
        raw = json.load(f)
    items = raw.get("items", raw)  # tolerate older schema
    out: Dict[str, StateItem] = {}
    for eid, v in items.items():
        out[eid] = StateItem(
            external_id=eid,
            name=v.get("name", ""),
            provider=v.get("provider", ""),
            deadline=v.get("deadline"),
            source_url=v.get("source_url", ""),
            first_seen=v.get("first_seen", _now_iso()),
            last_seen=v.get("last_seen", _now_iso()),
            archived=v.get("archived", False),
        )
    return out


def save_state(state: Dict[str, StateItem], path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "updated_at": _now_iso(),
        "items": {k: asdict(v) for k, v in state.items()},
    }
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def compute_weekly_changes(
    state: Dict[str, StateItem],
    current_items: Iterable[dict],
    *,
    window_days: int = 7,
) -> Tuple[List[dict], List[str], Dict[str, StateItem]]:
    """
    Returns (new_items_within_window, expired_ids, updated_state)
    - new: not in state before; only those first_seen within window
    - expired: items in state whose deadline < today and not yet archived
    - state is updated with last_seen for current items and newly added items
    """
    today = date.today()
    now = _now_iso()

    # Index current
    current_map: Dict[str, dict] = {it["external_id"]: it for it in current_items}

    # Update existing and detect expired
    expired_ids: List[str] = []
    for eid, si in list(state.items()):
        # update last_seen if still present
        if eid in current_map:
            si.last_seen = now
            # update deadline/name/provider/url in case of changes
            it = current_map[eid]
            si.deadline = it.get("deadline")
            si.name = it.get("name", si.name)
            si.provider = it.get("provider", si.provider)
            si.source_url = it.get("source_url", si.source_url)
        # expiration check
        if not si.archived and si.deadline:
            try:
                d = datetime.fromisoformat(si.deadline).date()
                if d < today:
                    expired_ids.append(eid)
            except Exception:
                pass

    # Add new
    new_items: List[dict] = []
    window_start = today.toordinal() - window_days
    for eid, it in current_map.items():
        if eid in state:
            continue
        first_seen = now
        state[eid] = StateItem(
            external_id=eid,
            name=it.get("name", ""),
            provider=it.get("provider", ""),
            deadline=it.get("deadline"),
            source_url=it.get("source_url", ""),
            first_seen=first_seen,
            last_seen=first_seen,
        )
        # include only if first_seen within window
        dt = datetime.strptime(first_seen, ISO_FMT).date()
        if dt.toordinal() >= window_start:
            new_items.append(it)

    return new_items, expired_ids, state

