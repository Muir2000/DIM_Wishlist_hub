"""Pydantic 입출력 스키마."""
from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class PerkOut(BaseModel):
    plug_hash: int
    name: str                      # 한국어 우선
    name_en: Optional[str] = None
    description: Optional[str] = None   # 한국어 퍽 설명 (툴팁용)
    description_en: Optional[str] = None
    icon: Optional[str] = None     # 절대 URL (bungie.net 접두 완료)
    plug_category: Optional[str] = None
    currently_can_roll: bool = True
    is_curated: bool = False
    is_enhanced: bool = False
    popularity: int = 0            # 인기도 막대용 (열 내 상대값은 프론트에서 계산)
    stats: Optional[Dict[str, float]] = None  # 스탯 델타 {stat_key: value} (배럴/탄창)
    weight: Optional[float] = None            # 활성 점수 프로필의 이 퍽 가중치 (Phase 2)


class ColumnOut(BaseModel):
    index: int
    kind: str                      # barrel|magazine|trait|origin|intrinsic
    label: str                     # 한국어 라벨
    perks: List[PerkOut]


class WeaponSummary(BaseModel):
    item_hash: int
    name: str
    name_en: Optional[str] = None
    icon: Optional[str] = None
    watermark: Optional[str] = None
    tier: Optional[int] = None
    tier_label: Optional[str] = None
    weapon_subtype: Optional[int] = None
    type_label: Optional[str] = None
    slot: Optional[str] = None
    default_damage_type: Optional[str] = None
    damage_label: Optional[str] = None
    stats: Optional[Dict[str, float]] = None       # {stat_key: 표시값}
    score: Optional[float] = None                  # 활성 프로필 종합 점수 (Phase 2)
    classification: Optional[str] = None           # god|viable|trash (Phase 2)
    # 변형(복각/홀로포일/에이뎁트) 그룹 정보
    variant_count: int = 1                         # 이 시즌의 무기 수(일반+홀로포일)
    has_holofoil: bool = False                     # 이 시즌에 홀로포일(외형만 다른 변형) 존재
    has_adept: bool = False                        # 이 시즌에 에이뎁트 변형 존재
    is_holofoil: bool = False                      # 이 무기 자체가 홀로포일인지
    season_count: int = 1                          # 이 무기의 총 시즌(복각) 수
    season_number: Optional[int] = None            # 이 무기가 출시된 시즌 번호 (예: 5)
    season_name: Optional[str] = None              # 시즌명 (ko, 예: 대장간 시즌)
    season_name_en: Optional[str] = None           # 시즌명 (en) — 영어 모드 표시용


class WeaponDetail(WeaponSummary):
    columns: List[ColumnOut] = []


class CompileRollIn(BaseModel):
    weapon_hash: int
    # JSON 키는 문자열 -> 라우터에서 int 로 변환. 한 열에 여러 해시 = OR(여러 줄로 전개).
    columns: Dict[str, List[int]] = Field(default_factory=dict)
    wildcard: bool = False
    trash: bool = False
    notes: str = ""
    tags: List[str] = Field(default_factory=list)
    comment: str = ""


class CompileOut(BaseModel):
    lines: List[str]
    line_count: int


class ExportIn(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    rolls: List[CompileRollIn]


class ExportOut(BaseModel):
    filename: str
    content: str
    line_count: int
    roll_count: int
    data_source: str               # "manifest" | "seed"
    warning: Optional[str] = None


class ImportIn(BaseModel):
    # 외부 DIM 위시리스트 .txt 본문. DoS 방지로 크기 제한(약 8MB — 대형 위시리스트도 수용).
    text: str = Field(max_length=8_000_000)


class ImportedRoll(BaseModel):
    """가져온 롤 — 프론트 store.addRoll 과 동일 형태(빌더 리스트에 바로 추가)."""
    input: CompileRollIn
    weapon_name: str
    weapon_name_en: Optional[str] = None
    perk_labels: List[str] = Field(default_factory=list)
    perk_labels_en: List[str] = Field(default_factory=list)
    lines: List[str] = Field(default_factory=list)
    type_label: Optional[str] = None
    damage_type: Optional[str] = None
    tier: Optional[int] = None


class ImportOut(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    rolls: List[ImportedRoll] = Field(default_factory=list)
    imported: int = 0              # 리스트에 추가된 롤 수
    unknown_weapons: int = 0       # DB 에 없는 무기(매니페스트 미적재/구버전) → 건너뜀
    skipped_lines: int = 0         # 파싱 실패 줄
    wildcard: int = 0              # 와일드카드(무기 무관) 롤 — 건너뜀


class StatusOut(BaseModel):
    data_source: str
    manifest_version: str
    weapons: int
    bungie_key_configured: bool
    note: Optional[str] = None


# ---------- v2: 점수화 프로필 / 점수 ----------
class SynergyBonus(BaseModel):
    perks: List[int]
    bonus: float = 0.0
    note: str = ""


class ScoringProfile(BaseModel):
    """프로필 = 공유 단위(JSON). id 없으면 생성 시 서버가 부여."""
    id: Optional[str] = None
    name: str = "내 점수 기준"
    description: str = ""
    tags: List[str] = Field(default_factory=list)
    stat_weights: Dict[str, float] = Field(default_factory=dict)
    perk_weights: Dict[str, float] = Field(default_factory=dict)  # 전역 퍽 가중치(JSON 키는 문자열)
    # 컨텍스트별 퍽 가중치: { "type:9": {plug_str: w}, "frame:H": {...}, "weapon:H": {...} }
    context_weights: Dict[str, Dict[str, float]] = Field(default_factory=dict)
    synergy_bonuses: List[SynergyBonus] = Field(default_factory=list)
    # 컨텍스트별 조합 가점: { "type:24": [{perks:[a,b], bonus}], ... }
    context_synergies: Dict[str, List[SynergyBonus]] = Field(default_factory=dict)
    use_wishlist_weights: bool = True
    blend: Dict[str, float] = Field(default_factory=lambda: {"stat": 1.0, "perk": 1.0, "synergy": 1.0})
    # v4: 스코프 블렌드(무기/프레임/종류 비중) + 열 비중(총열/탄창/특성/기원). 기본값은 scoring 상수.
    scope_blend: Dict[str, float] = Field(
        default_factory=lambda: {"weapon": 0.60, "frame": 0.25, "type": 0.15})
    column_weights: Dict[str, float] = Field(
        default_factory=lambda: {"trait": 1.0, "barrel": 0.35, "magazine": 0.35, "origin": 0.2, "intrinsic": 0.0})
    thresholds: Dict[str, float] = Field(default_factory=lambda: {"god": 75.0, "viable": 40.0})
    updated_at: Optional[str] = None


class ScoreRequest(BaseModel):
    weapon_hash: int
    perks: List[int] = Field(default_factory=list)
    profile: Optional[ScoringProfile] = None       # 인라인 프로필
    profile_id: Optional[str] = None               # 또는 저장된 프로필 id
    wishlist_rolls: List[CompileRollIn] = Field(default_factory=list)  # 위시리스트 자동 가중치용


class ScoreResult(BaseModel):
    score: Optional[float] = None                  # None = 점수 기준 없음(위시리스트/프로필 가중치 미존재)
    classification: Optional[str] = None           # god|viable|trash | None
    breakdown: Dict[str, Optional[float]]
    stats: Dict[str, float]
    coverage: Optional[float] = None               # 점수 신뢰도(기여 스코프 비중 합). 미등록 무기<1.0
    max_possible: Optional[float] = None           # 동적 만점(무기 채점가능 열 비중 합)


class DeriveWeightsRequest(BaseModel):
    """위시리스트로부터 퍽 가중치 도출 — 구조화 롤(rolls) 또는 DIM 텍스트(text)."""
    rolls: List[CompileRollIn] = Field(default_factory=list)
    text: Optional[str] = None


class DerivedWeight(BaseModel):
    plug_hash: int
    weight: float
    name: Optional[str] = None


class DeriveWeightsResult(BaseModel):
    weights: List[DerivedWeight]
    rolls_parsed: int


# ---------- v2 Phase 3: 인벤토리 / 정리 ----------
class InventoryPerk(BaseModel):
    plug_hash: int
    name: Optional[str] = None
    name_en: Optional[str] = None
    icon: Optional[str] = None
    column_kind: Optional[str] = None   # barrel|magazine|trait|origin|intrinsic (아이콘 모양용)
    column_index: Optional[int] = None  # 열 위치(총열0/탄창1/특성1 2/특성2 3/기원…) — 컬럼 정렬용


class CleanupItem(BaseModel):
    item_instance_id: str
    item_hash: int
    name: str
    name_en: Optional[str] = None
    icon: Optional[str] = None
    weapon_subtype: Optional[int] = None
    type_label: Optional[str] = None
    default_damage_type: Optional[str] = None
    damage_label: Optional[str] = None
    tier: Optional[int] = None
    power: Optional[int] = None
    perks: List[InventoryPerk] = Field(default_factory=list)
    stats: Dict[str, float] = Field(default_factory=dict)
    score: Optional[float] = None
    classification: Optional[str] = None


class InventoryStatus(BaseModel):
    connected: bool
    membership_id: Optional[str] = None
    item_count: int = 0
    synced_at: Optional[str] = None
    oauth_configured: bool = False
    login_url: Optional[str] = None
