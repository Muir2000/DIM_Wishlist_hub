"""점수화 엔진 (v2). 컨텍스트 인식 — 같은 퍽도 무기 종류/프레임/개별 무기에 따라 점수가 달라진다.

점수 입력(프로필):
  * stat_weights        : 스탯별 가중치(조작성 등)
  * perk_weights        : 전역 수동 퍽 가중치
  * context_weights     : 컨텍스트별 퍽 가중치 — { "type:9": {plug: w}, "frame:H": {...}, "weapon:H": {...} }
  * synergy_bonuses     : 전역 수동 조합 가점
  * context_synergies   : 컨텍스트별 조합 가점 — { "type:24": [{perks:[a,b], bonus}], ... }
  * use_wishlist_weights: 활성 위시리스트로부터 컨텍스트 가중치/조합을 실시간 도출해 합산

(무기 무관) 전역 + (무기의) type/frame/weapon 스코프 가중치를 합산해 퍽 점수를 낸다.
컨텍스트 가중치/조합은 **위시리스트에서 학습**(derive_context)한다.
"""
from __future__ import annotations

import sqlite3
from collections import Counter, defaultdict
from typing import Dict, Iterable, List, Mapping, Optional

PERK_SPAN = 50.0       # perk sub-점수 진폭(중립 50 기준 ±)
EXPECTED_PERKS = 2.5   # "갓롤"로 보는 기대 선호 퍽 수 — 1개로 만점이 되지 않게 정규화
COMBO_K = 2.0          # 매칭 조합 bonus 1점당 가산점
COMBO_CAP = 15.0       # 조합 가산점 상한
COMBO_SCALE = 5.0      # 도출 조합 bonus 정규화 스케일(수동 bonus 와 비교 가능하게)


# --- v4: 스코프 블렌드 · 열 비중 · 조합 캡 (기본값) ---
# 동일 무기/종류/프레임 위시리스트를 각각 계산해 절대 가중합(없는 스코프=0). 합 1.0.
SCOPE_BLEND = {"weapon": 0.60, "frame": 0.25, "type": 0.15}
# 열(총열/탄창/특성/기원/intrinsic)별 점수 기여 비중. 특성 중심, intrinsic(고정 프레임)은 채점 제외.
COLUMN_WEIGHT = {"trait": 1.0, "barrel": 0.35, "magazine": 0.35, "origin": 0.2, "intrinsic": 0.0}
COMBO_CONTRIB_CAP = 0.5  # 조합 가점 상한(열 비중 단위; 조합만으로 과도한 점수 방지)


def default_profile() -> dict:
    return {
        "stat_weights": {},
        "perk_weights": {},
        "context_weights": {},
        "synergy_bonuses": [],
        "context_synergies": {},
        "use_wishlist_weights": True,
        "blend": {"stat": 1.0, "perk": 1.0, "synergy": 1.0},
        "scope_blend": dict(SCOPE_BLEND),
        "column_weights": dict(COLUMN_WEIGHT),
        # v4 재보정: 동적 만점(풀롤=100)으로 천장이 올라가 분포가 내려가므로 하향.
        # god≥75(거의 풀롤), viable≥40(미등록 무기 종류/프레임 풀매칭 캡과 정합).
        "thresholds": {"god": 75.0, "viable": 40.0},
    }


def normalize_profile(p: Optional[dict]) -> dict:
    p = p or {}
    d = default_profile()
    cw = {}
    for scope, perks in (p.get("context_weights") or {}).items():
        cw[scope] = {int(k): float(v) for k, v in (perks or {}).items()}
    return {
        "stat_weights": {str(k): float(v) for k, v in (p.get("stat_weights") or {}).items()},
        "perk_weights": {int(k): float(v) for k, v in (p.get("perk_weights") or {}).items()},
        "context_weights": cw,
        "synergy_bonuses": list(p.get("synergy_bonuses") or []),
        "context_synergies": {s: list(v or []) for s, v in (p.get("context_synergies") or {}).items()},
        "use_wishlist_weights": bool(p.get("use_wishlist_weights", d["use_wishlist_weights"])),
        "blend": {**d["blend"], **(p.get("blend") or {})},
        "scope_blend": {**d["scope_blend"], **{k: float(v) for k, v in (p.get("scope_blend") or {}).items()}},
        "column_weights": {**d["column_weights"], **{k: float(v) for k, v in (p.get("column_weights") or {}).items()}},
        "thresholds": {**d["thresholds"], **(p.get("thresholds") or {})},
    }


def weapon_scopes(conn: sqlite3.Connection, weapon_hash: int) -> List[str]:
    """무기 → 적용 가능한 스코프 키 목록 (개별 무기 / 종류 / 프레임)."""
    row = conn.execute(
        "SELECT weapon_subtype, frame_hash FROM weapons WHERE item_hash = ?", (weapon_hash,)
    ).fetchone()
    scopes = [f"weapon:{weapon_hash}"]
    if row:
        if row["weapon_subtype"] is not None:
            scopes.append(f"type:{row['weapon_subtype']}")
        if row["frame_hash"] is not None:
            scopes.append(f"frame:{row['frame_hash']}")
    return scopes


def _roll_perks(roll: dict) -> List[int]:
    out = []
    for hashes in (roll.get("columns") or {}).values():
        for h in hashes or []:
            out.append(int(h))
    return out


def derive_context(conn: sqlite3.Connection, rolls: Iterable[dict]) -> dict:
    """위시리스트 롤 → 컨텍스트별 퍽 가중치 + 조합. 무기의 종류/프레임/개별 단위로 집계·정규화.

    반환: {"weights": {scope: {plug:int -> w}}, "combos": {scope: [{perks:[a,b], bonus}]}}
    """
    wts: Dict[str, Dict[int, float]] = defaultdict(lambda: defaultdict(float))
    pairs: Dict[str, Counter] = defaultdict(Counter)

    for r in rolls or []:
        wh = r.get("weapon_hash")
        if not wh:
            continue  # 와일드카드(무기 무관)는 컨텍스트 학습에서 제외
        wh = int(wh)
        perks = _roll_perks(r)
        if not perks:
            continue
        trash = bool(r.get("trash"))
        sign = -1.0 if trash else 1.0
        scopes = weapon_scopes(conn, wh)
        for sc in scopes:
            for p in perks:
                wts[sc][p] += sign
        # 조합(콤보): desirable 만, type/frame 스코프, 퍽 쌍 co-occurrence
        if not trash and len(perks) >= 2:
            uniq = sorted(set(perks))
            combo_scopes = [s for s in scopes if s.startswith(("type:", "frame:"))]
            for i in range(len(uniq)):
                for j in range(i + 1, len(uniq)):
                    for sc in combo_scopes:
                        pairs[sc][(uniq[i], uniq[j])] += 1

    out_w: Dict[str, Dict[int, float]] = {}
    for sc, pm in wts.items():
        mx = max((abs(v) for v in pm.values()), default=1.0) or 1.0
        out_w[sc] = {p: round(v / mx, 3) for p, v in pm.items()}

    out_c: Dict[str, list] = {}
    for sc, cnt in pairs.items():
        kept = [(pr, c) for pr, c in cnt.items() if c >= 2]
        if not kept:
            continue
        mx = max(c for _, c in kept)
        out_c[sc] = [
            {"perks": [a, b], "bonus": round(COMBO_SCALE * c / mx, 2)}
            for (a, b), c in sorted(kept, key=lambda x: -x[1])[:8]
        ]
    return {"weights": out_w, "combos": out_c}


# 하위호환: 전역(무기 무관) 가중치 도출
def derive_wishlist_weights(rolls: Iterable[dict]) -> Dict[int, float]:
    w: Dict[int, float] = {}
    for r in rolls or []:
        sign = -1.0 if r.get("trash") else 1.0
        for p in _roll_perks(r):
            w[p] = w.get(p, 0.0) + sign
    return w


def roll_stats(conn: sqlite3.Connection, weapon_hash: int, perk_hashes: Iterable[int]) -> Dict[str, float]:
    from . import repo
    stats = dict(repo.weapon_stats(conn, weapon_hash))
    for ph in perk_hashes:
        for k, v in repo.perk_stats(conn, ph).items():
            stats[k] = stats.get(k, 0.0) + v
    return stats


def classify(score: float, thresholds: Mapping[str, float]) -> str:
    if score >= thresholds.get("god", 75):
        return "god"
    if score >= thresholds.get("viable", 45):
        return "viable"
    return "trash"


GOD_TARGET = 2.0       # 퍽 배지 표시용 척도 기준(핵심 퍽 가중치 1.0 → +50점)
PERK_POINT_SCALE = 100.0 / GOD_TARGET  # 퍽 배지: weight 1.0 ≈ +50점(desirability 표시)


def _scope_kind(scope: str) -> str:
    """'weapon:123' → 'weapon', 'type:9' → 'type', 'frame:9002' → 'frame'."""
    return scope.split(":", 1)[0]


def _scope_value(p: int, scope: str, prof, ctx_w, use_wl):
    """스코프별 1개 값(수동 context_weights 우선, 없으면 도출 ctx_w). 없으면 None."""
    manual = prof["context_weights"].get(scope, {}).get(p)
    if manual is not None:
        return manual
    if use_wl:
        lv = ctx_w.get(scope, {}).get(p)
        if lv is not None:
            return lv
    return None


def _perk_weight(p: int, scopes, prof, wl, ctx_w, use_wl) -> float:
    """퍽 가중치(부호 포함, 대략 [-1,1]): **절대 스코프 블렌드**(무기/프레임/종류 가중합, 없는 스코프=0)
    + 전역 수동/위시. 미등록 무기는 weapon 항이 0 → w ≤ (프레임+종류 비중)≈0.40 으로 낮은 신뢰 자동 반영."""
    blend = prof["scope_blend"]
    ctx_val = 0.0
    for sc in scopes:
        v = _scope_value(p, sc, prof, ctx_w, use_wl)
        if v is not None:
            ctx_val += blend.get(_scope_kind(sc), 0.0) * v
    extra = prof["perk_weights"].get(p, 0.0) + (wl.get(p, 0.0) if use_wl else 0.0)
    return ctx_val + extra


def _has_signal(scopes, prof, wl, ctx_w, use_wl) -> bool:
    """점수 기준(신호) 존재 여부 — 위시리스트/프로필에 이 무기 관련 가중치가 하나라도 있나?"""
    return (
        bool(prof["perk_weights"])
        or any(prof["context_weights"].get(sc) for sc in scopes)
        or (use_wl and (bool(wl) or any(ctx_w.get(sc) for sc in scopes)))
    )


def _coverage(scopes, prof, wl, ctx_w, use_wl):
    """이 무기에 신호가 있는 스코프들의 비중 합(점수 캡). 전역(무기 무관) 신호가 있으면 캡 없음(1.0).

    반환: (coverage ∈ (0,1], present_scopes). 등록 무기=1.0, 미등록(종류+프레임만)≈0.40.
    """
    blend = prof["scope_blend"]
    present = [sc for sc in scopes
               if prof["context_weights"].get(sc) or (use_wl and ctx_w.get(sc))]
    cov = sum(blend.get(_scope_kind(sc), 0.0) for sc in present)
    if prof["perk_weights"] or (use_wl and wl):
        cov = 1.0  # 무기 무관 전역 가중치는 스코프 제약이 없음
    return min(cov, 1.0), present


def coverage(conn: sqlite3.Connection, weapon_hash: int, profile: Optional[dict] = None,
             wl_weights: Optional[Mapping[int, float]] = None, context: Optional[dict] = None):
    """공개 래퍼 — 무기의 점수 신뢰도(coverage)와 기여 스코프."""
    prof = normalize_profile(profile)
    use_wl = prof["use_wishlist_weights"]
    wl = wl_weights or {}
    ctx_w = (context or {}).get("weights", {}) if context else {}
    return _coverage(weapon_scopes(conn, weapon_hash), prof, wl, ctx_w, use_wl)


def weapon_columns(conn: sqlite3.Connection, weapon_hash: int):
    """({plug_hash: (column_index, kind)}, {column_index: kind}) — 열 비중 채점용."""
    rows = conn.execute(
        "SELECT plug_hash, column_index, column_kind FROM weapon_perks WHERE weapon_hash = ?",
        (weapon_hash,),
    ).fetchall()
    plug: Dict[int, tuple] = {}
    cols: Dict[int, str] = {}
    for r in rows:
        kind = r["column_kind"] or "trait"
        plug[r["plug_hash"]] = (r["column_index"], kind)
        cols[r["column_index"]] = kind
    return plug, cols


def perk_weight_map(
    conn: sqlite3.Connection,
    weapon_hash: int,
    plug_hashes: Iterable[int],
    profile: Optional[dict] = None,
    wl_weights: Optional[Mapping[int, float]] = None,
    context: Optional[dict] = None,
):
    """무기의 각 퍽에 대한 (컨텍스트 인지) 가중치 맵.

    반환: ({plug_hash:int -> weight:float}, has_signal:bool).
    weight 는 score_roll 과 동일 척도(대략 [-1,1]; 1 ≈ 핵심 퍽). 표시 점수는
    프론트에서 weight * PERK_POINT_SCALE(=50) 로 환산해 롤 점수와 정합시킨다.
    """
    prof = normalize_profile(profile)
    use_wl = prof["use_wishlist_weights"]
    wl = wl_weights or {}
    ctx_w = (context or {}).get("weights", {}) if context else {}
    scopes = weapon_scopes(conn, weapon_hash)
    has = _has_signal(scopes, prof, wl, ctx_w, use_wl)
    out = {int(p): round(_perk_weight(int(p), scopes, prof, wl, ctx_w, use_wl), 3)
           for p in plug_hashes}
    return out, has


def score_roll(
    conn: sqlite3.Connection,
    weapon_hash: int,
    perk_hashes: List[int],
    profile: Optional[dict] = None,
    wl_weights: Optional[Mapping[int, float]] = None,
    stats: Optional[Dict[str, float]] = None,
    context: Optional[dict] = None,
) -> dict:
    """**위시리스트 기반·퍽롤 중심** 점수 (v4: 스코프 블렌드 + 열 비중 + 동적 만점).

    퍽 가중치 = 동일 무기(0.60)·프레임(0.25)·종류(0.15) 위시리스트를 각각 계산한 **절대 가중합**
    (`_perk_weight`). 점수 = 열별 최선 퍽 × 열 비중(특성 1.0/총열·탄창 0.35/기원 0.2)의 합 + 조합 가점을,
    **무기별 동적 만점**(채점가능 열 비중 합, 풀롤=100)으로 정규화한 0~100.

    미등록 무기(무기별 위시리스트 없음)는 무기 비중(0.60)이 비어 **coverage(종류+프레임=0.40)** 로
    점수가 캡된다 → 새 무기 판단 시 종류/프레임 기준 부분 점수를 얻되 낮은 신뢰가 점수에 반영.
    스탯 가중치는 점수에 쓰지 않는다(표시용 stats 만 계산). 신호가 전혀 없으면 score=None.
    """
    prof = normalize_profile(profile)
    use_wl = prof["use_wishlist_weights"]
    wl = wl_weights or {}
    ctx_w = (context or {}).get("weights", {}) if context else {}
    ctx_c = (context or {}).get("combos", {}) if context else {}
    perks = [int(p) for p in perk_hashes]
    scopes = weapon_scopes(conn, weapon_hash)
    if stats is None:
        stats = roll_stats(conn, weapon_hash, perks)

    has_signal = _has_signal(scopes, prof, wl, ctx_w, use_wl)
    if not has_signal:
        return {
            "score": None, "classification": None,
            "breakdown": {"stat": None, "perk": None, "synergy": None},
            "stats": stats, "coverage": None, "max_possible": None,
        }

    col_w = prof["column_weights"]
    plug_cols, weapon_cols = weapon_columns(conn, weapon_hash)
    cov, _present = _coverage(scopes, prof, wl, ctx_w, use_wl)

    # 열별 **최선** 퍽만 채택(실제 롤=열당 1개; 빌더 다중선택="이 중 아무거나"→최선값).
    best_by_col: Dict[object, tuple] = {}   # col_key -> (signed_weight, kind)
    for p in perks:
        w = _perk_weight(p, scopes, prof, wl, ctx_w, use_wl)
        if p in plug_cols:
            ckey, kind = plug_cols[p]
        else:
            ckey, kind = (f"x{p}", "trait")  # 무기 밖 퍽(이론상): 고유 열·특성 취급
        cur = best_by_col.get(ckey)
        if cur is None or w > cur[0]:
            best_by_col[ckey] = (w, kind)

    # 열 비중 적용 기여 합(부호) + 동적 만점(무기의 채점가능 열 비중 합).
    contrib = sum(col_w.get(kind, 0.0) * w for (w, kind) in best_by_col.values())
    max_possible = sum(col_w.get(k, 0.0) for k in weapon_cols.values()) or 1.0

    # 조합 가점: 위시리스트 학습 + 수동. 매칭 시 퍽 단위(bonus/COMBO_SCALE ≈ 0~1)로 가산, 소폭 캡.
    combos = list(prof["synergy_bonuses"])
    for sc in scopes:
        combos += prof["context_synergies"].get(sc, [])
    if use_wl:
        for sc in scopes:
            combos += ctx_c.get(sc, [])
    pset = set(perks)
    combo_unit = 0.0
    for c in combos:
        pr = [int(x) for x in (c.get("perks") or [])]
        if pr and all(x in pset for x in pr):
            combo_unit += float(c.get("bonus", 0)) / COMBO_SCALE
    combo_unit = min(combo_unit, COMBO_CONTRIB_CAP)

    # 100 * (열가중 기여 + 조합) / 동적 만점, 단 coverage 로 캡(미등록 무기는 종류/프레임 비중까지만).
    composite = round(min(100.0 * cov, max(0.0, 100.0 * (contrib + combo_unit) / max_possible)), 1)

    return {
        "score": composite,
        "classification": classify(composite, prof["thresholds"]),
        "breakdown": {
            "stat": None,  # 스탯은 점수에 미반영(요구사항)
            "perk": round(max(0.0, 100.0 * contrib / max_possible), 1),
            "synergy": round(100.0 * combo_unit / max_possible, 1) if combo_unit else None,
        },
        "stats": stats,
        "coverage": round(cov, 3),
        "max_possible": round(max_possible, 3),
    }
