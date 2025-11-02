from __future__ import annotations

import time
from typing import Optional
from urllib.parse import urlparse

import requests
from urllib import robotparser


DEFAULT_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def _robots_parser_for(url: str) -> Optional[robotparser.RobotFileParser]:
    try:
        p = urlparse(url)
        robots_url = f"{p.scheme}://{p.netloc}/robots.txt"
        rp = robotparser.RobotFileParser()
        rp.set_url(robots_url)
        rp.read()
        return rp
    except Exception:
        return None


def allowed_by_robots(url: str, user_agent: str = DEFAULT_UA) -> bool:
    rp = _robots_parser_for(url)
    if not rp:
        return True
    try:
        return rp.can_fetch(user_agent, url)
    except Exception:
        return True


def get(url: str, *, user_agent: str = DEFAULT_UA, timeout: int = 20, delay: float = 0.8) -> requests.Response:
    if not allowed_by_robots(url, user_agent):
        raise RuntimeError(f"Blocked by robots.txt: {url}")
    headers = {"User-Agent": user_agent, "Accept": "*/*"}
    resp = requests.get(url, headers=headers, timeout=timeout)
    time.sleep(delay)
    resp.raise_for_status()
    return resp

