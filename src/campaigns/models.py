from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class Campaign:
    name: str
    provider: str
    category: str
    reward_type: Optional[str]
    reward_value: Optional[str]
    deadline: Optional[str]
    source_url: str
    external_id: str

    def to_dict(self) -> dict:
        return asdict(self)

