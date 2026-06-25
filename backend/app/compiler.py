"""
DIM Wishlist 컴파일러 엔진 (프로젝트의 핵심).

DIM 의 실제 파서(`src/app/wishlists/wishlist-file.ts`)와 정확히 호환되는 텍스트를
생성한다. 컴파일 규칙은 README 와 계획서를 참조.

핵심 불변식:
  * 한 줄 내 쉼표(`perks=A,B`)는 AND. 같은 열의 "A 또는 B" 는 줄을 여러 개로 전개한다.
  * 퍽 해시는 Inventory Item 플러그 해시. 강화(Enhanced) 퍽은 emit 하지 않고
    기본(base) 해시만 출력한다(DIM 이 강화판을 자동 매칭).
  * 트래시 롤 = 아이템 해시 음수화. 와일드카드 = item=-69420 (desirable 전용).
  * 노트에 파이프(`|`) 금지 — 파서가 그 뒤를 잘라낸다.
  * 출력은 LF(`\n`) 개행, BOM 없음.
"""
from __future__ import annotations

import itertools
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional, Sequence

# DIM types.ts: WildcardItemId = -69420 (모든 아이템 매칭, desirable 전용)
WILDCARD_ITEM_ID = -69420

# DoS 방지: 한 롤이 카르테시안 전개로 만들 수 있는 최대 줄 수.
MAX_ROLL_COMBOS = 2000

# DIM wishlist-file.ts 의 줄 파싱 정규식을 그대로 옮긴 것 (라운드트립 검증용).
#   ^dimwishlist:item=(?<itemHash>-?\d+)(?:&perks=)?(?<itemPerks>[\d|,]*)(?:#notes:)?(?<wishListNotes>[^|]*)
DIM_LINE_RE = re.compile(
    r"^dimwishlist:item=(?P<itemHash>-?\d+)"
    r"(?:&perks=)?(?P<itemPerks>[\d|,]*)"
    r"(?:#notes:)?(?P<wishListNotes>[^|]*)"
)

TITLE_RE = re.compile(r"^@?title:(.+)$")
DESCRIPTION_RE = re.compile(r"^@?description:(.+)$")
BLOCK_NOTES_PREFIX = "//notes:"


class CompileError(ValueError):
    """위시리스트 컴파일 입력이 유효하지 않을 때."""


@dataclass
class RollRequest:
    """단일 롤(무기 1종에 대한 원하는/원치 않는 퍽 조합) 요청.

    columns: {열 인덱스(int): [선택된 plug_hash, ...]} — 유저가 *제약한* 열만 포함.
             한 열에 여러 해시를 넣으면 "이 중 아무거나(OR)" 의미이며, 컴파일러가
             열 간 카르테시안 곱으로 여러 줄을 만든다.
    """

    weapon_hash: int
    columns: Dict[int, List[int]] = field(default_factory=dict)
    wildcard: bool = False
    trash: bool = False
    notes: str = ""
    tags: List[str] = field(default_factory=list)
    comment: str = ""  # 파일에 `// comment` 주석으로 표기(보통 무기 이름)
    # 변형(복각/홀로포일/에이뎁트) 무기 해시들 — 같은 롤을 이 해시들에도 emit.
    # DIM 은 item hash 로 매칭하므로, 외형만 다른 홀로포일·시즌별 복각까지 한 번에 커버한다.
    variant_hashes: List[int] = field(default_factory=list)
    # {variant_hash: 그 변형이 굴릴 수 있는 plug_hash 집합} — 주어지면 그 변형이
    # 굴릴 수 없는 퍽 조합 줄은 생략(죽은 줄 방지). 비우면 필터 없이 그대로 emit.
    variant_pools: Dict[int, set] = field(default_factory=dict)


def sanitize_notes(text: str) -> str:
    """노트 문자열을 DIM 한 줄 포맷에 안전하게 정규화한다.

    - 파이프(`|`) 제거(파서가 그 뒤를 잘라냄).
    - 실제 개행/탭/제어문자는 리터럴 `\\n`(역슬래시+n)으로 변환 — DIM 이 이를 줄바꿈으로 렌더.
    - 한국어 등 비ASCII 는 유지(노트는 UTF-8 허용). 다만 NFC 정규화.
    - 앞뒤 공백 trim.
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text)
    text = text.replace("|", " ")
    # CRLF/CR/LF/탭 -> 리터럴 \n (한 물리적 줄 유지)
    text = re.sub(r"\r\n|\r|\n|\t", r"\\n", text)
    # 그 외 제어문자 제거
    text = "".join(ch for ch in text if ch == "\\" or unicodedata.category(ch)[0] != "C")
    return text.strip()


def _format_tags(tags: Sequence[str]) -> str:
    """태그를 `[PvP] [GM]` 형태로. wishlistnotes: 검색이 부분일치하므로 토큰만 남기면 됨."""
    clean = []
    seen = set()
    for t in tags:
        t = (t or "").strip().replace("|", "").replace("[", "").replace("]", "")
        if t and t.lower() not in seen:
            seen.add(t.lower())
            clean.append(t)
    return " ".join(f"[{t}]" for t in clean)


def build_note_text(notes: str, tags: Sequence[str]) -> str:
    """태그 + 노트를 합쳐 최종 `#notes:` 본문을 만든다(비면 빈 문자열)."""
    tag_str = _format_tags(tags or [])
    note_str = sanitize_notes(notes or "")
    combined = (tag_str + (" " + note_str if note_str else "")).strip()
    return combined


def sanitize_header(text: str) -> str:
    """title:/description: 헤더용 — 한 줄, 파이프 없음, 개행 제거."""
    text = unicodedata.normalize("NFC", text or "")
    text = re.sub(r"[\r\n\t]+", " ", text).replace("|", " ")
    text = "".join(ch for ch in text if unicodedata.category(ch)[0] != "C")
    return text.strip()


def _base_hash(plug_hash: int, base_map: Optional[Mapping[int, int]]) -> int:
    """강화 퍽 해시를 기본 해시로 매핑(없으면 그대로)."""
    if base_map:
        return base_map.get(plug_hash, plug_hash)
    return plug_hash


def compile_roll(
    roll: RollRequest,
    base_map: Optional[Mapping[int, int]] = None,
) -> List[str]:
    """RollRequest 한 건을 DIM `dimwishlist:` 줄 리스트로 컴파일한다(다중 줄 전개 포함)."""
    if roll.wildcard and roll.trash:
        # types.ts 가드: 음수 와일드카드는 그냥 와일드카드가 되어버려 트래시 의미가 사라진다.
        raise CompileError("와일드카드와 트래시 롤은 동시에 사용할 수 없습니다.")

    if not isinstance(roll.weapon_hash, int) or roll.weapon_hash <= 0:
        if not roll.wildcard:
            raise CompileError(f"유효하지 않은 weapon_hash: {roll.weapon_hash!r}")

    if roll.wildcard:
        item_id = WILDCARD_ITEM_ID
    elif roll.trash:
        item_id = -abs(roll.weapon_hash)
    else:
        item_id = abs(roll.weapon_hash)

    note_body = build_note_text(roll.notes, roll.tags)
    note_suffix = f"#notes:{note_body}" if note_body else ""

    # 제약된 열만, 열 인덱스 오름차순으로 안정 정렬. 각 열은 중복 제거하되 순서 유지.
    ordered_cols = []
    for col_idx in sorted(roll.columns.keys()):
        hashes = roll.columns[col_idx]
        seen = set()
        deduped = []
        for h in hashes:
            bh = _base_hash(int(h), base_map)
            if bh not in seen:
                seen.add(bh)
                deduped.append(bh)
        if deduped:
            ordered_cols.append(deduped)

    # DoS 방지: 열 간 카르테시안 곱이 폭발하지 않도록 한 롤의 조합 수를 제한.
    n_combos = 1
    for col in ordered_cols:
        n_combos *= len(col)
    if n_combos > MAX_ROLL_COMBOS:
        raise CompileError(
            f"한 롤의 퍽 조합이 너무 많습니다({n_combos}). 열당 선택 수를 줄이세요(최대 {MAX_ROLL_COMBOS} 조합)."
        )

    # emit 대상 item_id 목록: 주 무기 + 변형(복각/홀로포일). 와일드카드는 이미 전체 매칭이라 제외.
    targets: List[tuple] = [(item_id, ordered_cols)]
    if not roll.wildcard:
        for vh in roll.variant_hashes:
            vh = int(vh)
            if vh <= 0 or vh == abs(roll.weapon_hash):
                continue
            vcols = _filter_columns_for_variant(ordered_cols, roll.variant_pools.get(vh))
            if vcols is None:
                continue  # 이 변형은 원하는 제약을 하나도 못 굴림 → 스킵
            vid = -abs(vh) if roll.trash else abs(vh)
            targets.append((vid, vcols))

    lines: List[str] = []
    seen_lines = set()
    for tid, cols in targets:
        if not cols:
            ln = f"dimwishlist:item={tid}{note_suffix}"
            if ln not in seen_lines:
                seen_lines.add(ln); lines.append(ln)
            continue
        # 열 간 카르테시안 곱 = 줄별 1조합. 줄 내부는 AND.
        for combo in itertools.product(*cols):
            perks = ",".join(str(h) for h in combo)
            ln = f"dimwishlist:item={tid}&perks={perks}{note_suffix}"
            if ln not in seen_lines:
                seen_lines.add(ln); lines.append(ln)
    return lines


def _filter_columns_for_variant(ordered_cols, pool):
    """변형 무기 풀(pool)에 맞춰 각 열의 퍽을 거른다.

    - pool 이 None 이면 필터 없이 그대로(원본 반환).
    - 제약된 열 중 하나라도 변형이 굴릴 수 있는 퍽이 0개면 None(이 변형은 스킵).
    - base_map 은 호출부에서 이미 적용됨(ordered_cols 는 base 해시).
    """
    if pool is None:
        return ordered_cols
    out = []
    for col in ordered_cols:
        kept = [h for h in col if h in pool]
        if not kept:
            return None
        out.append(kept)
    return out


def compile_wishlist(
    rolls: Sequence[RollRequest],
    title: Optional[str] = None,
    description: Optional[str] = None,
    base_map: Optional[Mapping[int, int]] = None,
) -> str:
    """여러 롤을 모아 완성된 위시리스트 파일 본문(텍스트)을 만든다.

    출력은 LF 개행, BOM 없음, 마지막 줄 개행 포함.
    """
    out: List[str] = []
    if title:
        out.append(f"title:{sanitize_header(title)}")
    if description:
        out.append(f"description:{sanitize_header(description)}")
    if out:
        out.append("")  # 헤더와 본문 사이 빈 줄

    for roll in rolls:
        if roll.comment:
            out.append(f"// {sanitize_header(roll.comment)}")
        out.extend(compile_roll(roll, base_map=base_map))
        out.append("")  # 롤 그룹 사이 빈 줄 (블록 노트 bleed 방지에도 도움)

    # 마지막 잉여 빈 줄 정리 후 종결 개행 1개
    text = "\n".join(out).rstrip("\n")
    return text + "\n" if text else ""


# ---------------------------------------------------------------------------
# 검증/파싱 (단위 테스트 및 라운드트립용)
# ---------------------------------------------------------------------------

def is_valid_line(line: str) -> bool:
    """한 줄이 DIM 파서 정규식에 부합하는지."""
    return bool(DIM_LINE_RE.match(line))


def parse_line(line: str) -> Optional[dict]:
    """DIM 파서와 동일하게 한 줄을 파싱한다(라운드트립 검증용).

    반환: {item_hash:int, perks:set[int], is_undesirable:bool, is_wildcard:bool, notes:str}
    또는 매칭 실패 시 None.
    """
    m = DIM_LINE_RE.match(line)
    if not m:
        return None
    raw_hash = int(m.group("itemHash"))
    is_wildcard = raw_hash == WILDCARD_ITEM_ID
    is_undesirable = raw_hash < 0 and not is_wildcard
    perks_str = m.group("itemPerks") or ""
    perks = {int(p) for p in re.split(r"[,|]", perks_str) if p}
    return {
        "item_hash": abs(raw_hash) if not is_wildcard else raw_hash,
        "perks": perks,
        "is_undesirable": is_undesirable,
        "is_wildcard": is_wildcard,
        "notes": m.group("wishListNotes") or "",
    }


def parse_wishlist(text: str) -> dict:
    """DIM 위시리스트 **파일 전체**를 파싱(가져오기용).

    - `title:`/`description:` 헤더 추출.
    - `// 무기이름` 주석과 `//notes:` 블록 노트를 추적해 각 롤에 부여.
    - 같은 블록(연속된 같은 주석 하 같은 item_hash·트래시/와일드카드)의 여러 줄은 **하나의 롤로
      합친다**(퍽 합집합) — DIM 의 카르테시안 전개를 역으로 묶어 멀티선택 롤로 복원.
    - 빈 줄은 블록 노트 종료.

    반환: {title, description, rolls:[{item_hash, perks:set[int], trash, wildcard, notes, comment}], skipped}
    """
    title = None
    description = None
    comment = ""        # 현재 // 주석(보통 무기 이름)
    block_notes = ""    # 현재 //notes: 블록 노트
    groups: dict = {}
    order: list = []
    skipped = 0

    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            block_notes = ""
            continue
        mt = TITLE_RE.match(line)
        if mt:
            title = mt.group(1).strip(); continue
        md = DESCRIPTION_RE.match(line)
        if md:
            description = md.group(1).strip(); continue
        if line.startswith(BLOCK_NOTES_PREFIX):      # //notes: (//주석보다 먼저 검사)
            block_notes = line[len(BLOCK_NOTES_PREFIX):].strip(); continue
        if line.startswith("//"):                     # 일반 주석 = 무기 이름 라벨
            comment = line[2:].strip(); block_notes = ""; continue
        if line.startswith("dimwishlist:"):
            p = parse_line(line)
            if not p:
                skipped += 1; continue
            key = (comment, p["item_hash"], p["is_undesirable"], p["is_wildcard"])
            if key not in groups:
                groups[key] = {"perks": set(), "notes": (p["notes"] or block_notes or "").strip()}
                order.append(key)
            groups[key]["perks"].update(p["perks"])
            continue
        # 그 외 줄은 무시

    rolls = []
    for key in order:
        cm, ih, trash, wild = key
        g = groups[key]
        rolls.append({
            "item_hash": ih, "perks": g["perks"], "trash": trash,
            "wildcard": wild, "notes": g["notes"], "comment": cm,
        })
    return {"title": title, "description": description, "rolls": rolls, "skipped": skipped}
