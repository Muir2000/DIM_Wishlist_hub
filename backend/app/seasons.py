"""워터마크 → 시즌(번호 + 이름) 매핑.

무기 정의에는 seasonHash 가 비어 있어, 어느 시즌(복각) 무기인지 알 수 없다.
대신 Bungie 가 시즌마다 바꾸는 iconWatermark 로 구분한다. watermark→시즌번호 매핑은
DIM 커뮤니티(d2-additional-info)의 watermark-to-season.json 을, 시즌명은 매니페스트
DestinySeasonDefinition 을 사용한다(둘 다 backend/app/refdata 에 동봉). 런타임 1회 로드.

재적재가 필요 없다 — 무기의 watermark 만 있으면 매 요청 시 매핑한다.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Tuple

_DIR = Path(__file__).parent / "refdata"
_wm_to_season: dict = {}
_season_names: dict = {}


def _load() -> None:
    global _wm_to_season, _season_names
    try:
        with open(_DIR / "watermark-to-season.json", encoding="utf-8-sig") as f:
            _wm_to_season = json.load(f)
    except (OSError, ValueError):
        _wm_to_season = {}
    try:
        with open(_DIR / "season-names.json", encoding="utf-8-sig") as f:
            _season_names = json.load(f)
    except (OSError, ValueError):
        _season_names = {}


_load()


def _path_only(watermark: str) -> str:
    """절대 URL(https://www.bungie.net/common/...)이 와도 /common/... 경로만 추출."""
    if watermark.startswith("http"):
        i = watermark.find("/common/")
        if i >= 0:
            return watermark[i:]
    return watermark


def season_number(watermark: Optional[str]) -> Optional[int]:
    if not watermark:
        return None
    return _wm_to_season.get(_path_only(watermark))


def season_name(num: Optional[int]) -> Optional[str]:
    if num is None:
        return None
    info = _season_names.get(str(num)) or {}
    return info.get("ko") or info.get("en")


def season_for_watermark(watermark: Optional[str]) -> Tuple[Optional[int], Optional[str]]:
    """watermark → (시즌번호, 시즌명). 매핑 없으면 (None, None)."""
    num = season_number(watermark)
    return num, season_name(num)


def watermarks_for_season(num: int) -> list:
    """시즌 번호 → 그 시즌에 해당하는 watermark 경로들(역매핑). 시즌 필터용."""
    return [wm for wm, n in _wm_to_season.items() if n == num]


def all_season_numbers() -> list:
    """매핑에 존재하는 시즌 번호 목록(오름차순). 시즌 패싯 후보."""
    return sorted({int(n) for n in _wm_to_season.values()})
