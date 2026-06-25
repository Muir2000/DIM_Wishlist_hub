"""DIM식 텍스트 검색 쿼리 → SQL WHERE 식 컴파일러.

DIM Item Search 의 사고방식을 도입한 파워유저용 텍스트 쿼리. 지원 문법(서브셋):

    is:<토큰>            종류/속성/슬롯/등급/탄약/adept/holofoil/exotic/legendary/randomroll
    perkname:"이름"      그 퍽(부분일치)을 굴릴 수 있는 무기 (perk: 동의어)
    stat:<키>:<조건>     예) stat:range:>=50, stat:rpm:180, stat:handling:40-60
    season:<조건>        예) season:5, season:>=20
    frame:<텍스트>       프레임(아키타입) 이름 부분일치
    origin:<텍스트>      기원 특성 이름 부분일치
    name:<텍스트>        무기 이름 부분일치 (맨텍스트도 이름 검색)
    and / or / not / -   불리언 (인접 = 암묵 AND), 괄호 () 그룹

확장성: 새 필터 = `_REGISTRY` 에 키워드 1줄 추가. 값은 항상 파라미터 바인딩(인젝션 차단),
스탯키/연산자는 화이트리스트만 허용.
"""
from __future__ import annotations

import re
from typing import List, Tuple

from . import labels, seasons

# 컴파일 결과: (sql_fragment, params)
SQL = Tuple[str, list]

STAT_KEYS = {
    "impact", "range", "stability", "handling", "reload", "magazine", "aim_assist",
    "recoil", "zoom", "rpm", "charge_time", "draw_time", "swing_speed",
    "blast_radius", "velocity",
}
# 흔한 별칭 → 정규 키
STAT_ALIASES = {"aimassist": "aim_assist", "chargetime": "charge_time",
                "drawtime": "draw_time", "blastradius": "blast_radius",
                "swingspeed": "swing_speed", "mag": "magazine"}

_OPS = {">=", "<=", ">", "<", "="}


class QueryError(ValueError):
    """쿼리 문법/토큰 오류."""


# ---------------------------------------------------------------------------
# 토크나이저
# ---------------------------------------------------------------------------
def tokenize(s: str) -> List[str]:
    """공백으로 나누되 "..." 안의 공백은 보존, 괄호는 별도 토큰."""
    tokens: List[str] = []
    cur = ""
    in_quote = False
    for ch in s or "":
        if ch == '"':
            in_quote = not in_quote
            cur += ch
        elif ch in "()" and not in_quote:
            if cur.strip():
                tokens.append(cur.strip()); cur = ""
            tokens.append(ch)
        elif ch.isspace() and not in_quote:
            if cur.strip():
                tokens.append(cur.strip()); cur = ""
        else:
            cur += ch
    if cur.strip():
        tokens.append(cur.strip())
    return tokens


# ---------------------------------------------------------------------------
# 파서 (재귀 하강) → AST
#   AST 노드: ('and'|'or', l, r) | ('not', n) | ('leaf', sql, params)
# ---------------------------------------------------------------------------
class _Parser:
    def __init__(self, tokens: List[str]):
        self.toks = tokens
        self.i = 0

    def _peek(self):
        return self.toks[self.i] if self.i < len(self.toks) else None

    def _next(self):
        t = self.toks[self.i]; self.i += 1; return t

    def parse(self):
        if not self.toks:
            return None
        node = self._expr()
        if self.i != len(self.toks):
            raise QueryError(f"예상치 못한 토큰: {self._peek()!r}")
        return node

    def _expr(self):  # OR
        node = self._term()
        while self._peek() and self._peek().lower() == "or":
            self._next()
            node = ("or", node, self._term())
        return node

    def _term(self):  # 암묵/명시 AND
        node = self._factor()
        while True:
            t = self._peek()
            if t is None or t == ")" or t.lower() == "or":
                break
            if t.lower() == "and":
                self._next()
            node = ("and", node, self._factor())
        return node

    def _factor(self):
        t = self._peek()
        if t is None:
            raise QueryError("식이 비어 있습니다.")
        if t.lower() == "not":
            self._next()
            return ("not", self._factor())
        if t == "(":
            self._next()
            node = self._expr()
            if self._peek() != ")":
                raise QueryError("괄호가 닫히지 않았습니다.")
            self._next()
            return node
        if t == ")":
            raise QueryError("예상치 못한 ')'.")
        self._next()
        if t.startswith("-") and len(t) > 1:
            return ("not", ("leaf", *_compile_leaf(t[1:])))
        return ("leaf", *_compile_leaf(t))


# ---------------------------------------------------------------------------
# 리프 컴파일 (필터 레지스트리)
# ---------------------------------------------------------------------------
def _strip_quotes(v: str) -> str:
    return v.strip().strip('"').strip()


def _name_like(v: str) -> SQL:
    like = f"%{_strip_quotes(v)}%"
    return "(w.name_ko LIKE ? OR w.name_en LIKE ?)", [like, like]


def _is_token(v: str) -> SQL:
    t = labels._norm(v)
    if t in labels.SUBTYPE_TOKENS:
        return "w.weapon_subtype = ?", [labels.SUBTYPE_TOKENS[t]]
    if t in labels.DAMAGE_TOKENS:
        return "w.default_damage_type = ?", [labels.DAMAGE_TOKENS[t]]
    if t in labels.SLOT_TOKENS:
        return "w.slot = ?", [labels.SLOT_TOKENS[t]]
    if t in labels.TIER_TOKENS:
        return "w.tier = ?", [labels.TIER_TOKENS[t]]
    if t in labels.AMMO_TOKENS:
        return "w.ammo_type = ?", [labels.AMMO_TOKENS[t]]
    if t in ("adept", "숙련자"):
        return "COALESCE(w.is_adept,0) = 1", []
    if t in ("holofoil", "홀로포일"):
        return "COALESCE(w.is_holofoil,0) = 1", []
    if t == "randomroll":
        return "EXISTS(SELECT 1 FROM weapon_perks wp WHERE wp.weapon_hash = w.item_hash)", []
    raise QueryError(f"알 수 없는 is: 토큰 '{v}'")


def _perk_like(v: str) -> SQL:
    like = f"%{_strip_quotes(v)}%"
    return ("EXISTS(SELECT 1 FROM weapon_perks wp JOIN perks p ON p.plug_hash = wp.plug_hash "
            "WHERE wp.weapon_hash = w.item_hash AND (p.name_ko LIKE ? OR p.name_en LIKE ?))",
            [like, like])


def _origin_like(v: str) -> SQL:
    like = f"%{_strip_quotes(v)}%"
    return ("EXISTS(SELECT 1 FROM weapon_perks wp JOIN perks p ON p.plug_hash = wp.plug_hash "
            "WHERE wp.weapon_hash = w.item_hash AND wp.column_kind = 'origin' "
            "AND (p.name_ko LIKE ? OR p.name_en LIKE ?))",
            [like, like])


def _frame_like(v: str) -> SQL:
    return "w.frame LIKE ?", [f"%{_strip_quotes(v)}%"]


def _parse_cond(cond: str):
    """'>=50' / '50' / '40-60' → ('op', value) 또는 ('range', lo, hi)."""
    cond = cond.strip()
    m = re.match(r"^(\d+)\s*-\s*(\d+)$", cond)
    if m:
        return ("range", float(m.group(1)), float(m.group(2)))
    m = re.match(r"^(>=|<=|>|<|=)?\s*(-?\d+(?:\.\d+)?)$", cond)
    if not m:
        raise QueryError(f"숫자 조건 형식이 아닙니다: '{cond}'")
    op = m.group(1) or "="
    return (op, float(m.group(2)))


def _stat(v: str) -> SQL:
    # v = 'range:>=50'  (stat: 다음 전체)
    if ":" not in v:
        raise QueryError("stat 형식: stat:<키>:<조건> (예: stat:range:>=50)")
    key, cond = v.split(":", 1)
    key = labels._norm(key)
    key = STAT_ALIASES.get(key, key)
    if key not in STAT_KEYS:
        raise QueryError(f"알 수 없는 스탯 키 '{key}'")
    parsed = _parse_cond(cond)
    base = "EXISTS(SELECT 1 FROM weapon_stats ws WHERE ws.weapon_hash = w.item_hash AND ws.stat_key = ? AND "
    if parsed[0] == "range":
        return base + "ws.value >= ? AND ws.value <= ?)", [key, parsed[1], parsed[2]]
    op = "=" if parsed[0] == "=" else parsed[0]
    return base + f"ws.value {op} ?)", [key, parsed[1]]


def _season(v: str) -> SQL:
    parsed = _parse_cond(v)
    allnums = seasons.all_season_numbers()
    if parsed[0] == "range":
        lo, hi = parsed[1], parsed[2]
        nums = [n for n in allnums if lo <= n <= hi]
    else:
        op, val = parsed[0], parsed[1]
        cmp = {">=": lambda n: n >= val, "<=": lambda n: n <= val,
               ">": lambda n: n > val, "<": lambda n: n < val, "=": lambda n: n == val}[op]
        nums = [n for n in allnums if cmp(n)]
    wms: list = []
    for n in nums:
        wms += seasons.watermarks_for_season(n)
    if not wms:
        return "0", []
    return f"w.watermark IN ({','.join('?' * len(wms))})", wms


# 키워드 → 빌더(value) -> SQL.  ← 새 필터는 여기 한 줄 추가하면 됨(확장성)
_REGISTRY = {
    "is": _is_token,
    "perkname": _perk_like,
    "perk": _perk_like,
    "stat": _stat,
    "season": _season,
    "frame": _frame_like,
    "origin": _origin_like,
    "name": _name_like,
}


def _compile_leaf(token: str) -> SQL:
    if ":" in token:
        key, val = token.split(":", 1)
        builder = _REGISTRY.get(key.lower())
        if builder:
            if not val:
                raise QueryError(f"'{key}:' 뒤에 값이 필요합니다.")
            return builder(val)
        # 알 수 없는 key: 형태는 이름 검색으로 떨어뜨리지 않고 에러(오타 방지)
        raise QueryError(f"알 수 없는 검색 키워드 '{key}:'")
    return _name_like(token)


# ---------------------------------------------------------------------------
# AST → SQL
# ---------------------------------------------------------------------------
def _to_sql(node) -> SQL:
    kind = node[0]
    if kind == "leaf":
        return node[1], list(node[2])
    if kind == "not":
        s, p = _to_sql(node[1])
        return f"NOT ({s})", p
    # and / or
    ls, lp = _to_sql(node[1])
    rs, rp = _to_sql(node[2])
    return f"({ls} {kind.upper()} {rs})", lp + rp


def compile_query(text: str) -> SQL:
    """텍스트 쿼리 → (sql_where, params). 빈 쿼리는 ('', [])."""
    tokens = tokenize(text)
    if not tokens:
        return "", []
    ast = _Parser(tokens).parse()
    if ast is None:
        return "", []
    return _to_sql(ast)


# 프론트 치트시트/도움말
HELP = {
    "operators": ["and (암묵)", "or", "not / -", "( )"],
    "keywords": [
        {"token": "is:<종류/속성/슬롯/등급/탄약>", "예": "is:핸드캐논, is:solar, is:exotic, is:adept"},
        {"token": "perkname:\"이름\"", "예": 'perkname:"무법자"'},
        {"token": "stat:<키>:<조건>", "예": "stat:range:>=50, stat:rpm:180, stat:handling:40-60"},
        {"token": "season:<조건>", "예": "season:5, season:>=20"},
        {"token": "frame:<텍스트>", "예": "frame:정밀"},
        {"token": "origin:<텍스트>", "예": "origin:대장간"},
        {"token": "name:<텍스트> / 맨텍스트", "예": "name:용광로"},
    ],
    "examples": [
        'is:핸드캐논 is:solar stat:range:>=50',
        'is:파동소총 -perkname:"무법자" season:>=23',
        '(is:arc or is:void) is:exotic',
        'frame:정밀 stat:handling:>=45',
    ],
}
