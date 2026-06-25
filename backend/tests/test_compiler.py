"""컴파일러 엔진 단위 테스트.

stdlib unittest 만 사용하므로 `python -m unittest` 로 바로 실행 가능
(pytest 도 동일 테스트를 디스커버한다).

실행 (backend/ 디렉터리에서):
    python -m unittest discover -s tests -v
"""
import unittest

from app.compiler import (
    WILDCARD_ITEM_ID,
    CompileError,
    RollRequest,
    build_note_text,
    compile_roll,
    compile_wishlist,
    is_valid_line,
    parse_line,
    sanitize_notes,
)

# 조사에서 확인된 실제 해시 (Fractethyst, 프랙테시스트)
FRACTETHYST = 3184681056
PERK_A = 1047830412
PERK_B = 3142289711
PERK_C = 706527188
PERK_D = 47981717


class TestSingleLine(unittest.TestCase):
    def test_basic_roll(self):
        lines = compile_roll(RollRequest(FRACTETHYST, {3: [PERK_A], 4: [PERK_B]}))
        self.assertEqual(lines, [f"dimwishlist:item={FRACTETHYST}&perks={PERK_A},{PERK_B}"])

    def test_perks_sorted_by_column(self):
        # 열 인덱스 순서가 보장되어야 함 (4를 먼저 넣어도 3,4 순)
        lines = compile_roll(RollRequest(FRACTETHYST, {4: [PERK_B], 3: [PERK_A]}))
        self.assertEqual(lines, [f"dimwishlist:item={FRACTETHYST}&perks={PERK_A},{PERK_B}"])

    def test_no_perks_emits_item_only(self):
        lines = compile_roll(RollRequest(FRACTETHYST, {}))
        self.assertEqual(lines, [f"dimwishlist:item={FRACTETHYST}"])


class TestMultiPerkExpansion(unittest.TestCase):
    """가장 중요한 규칙: 같은 열 다중 선택 -> 줄 여러 개(카르테시안 곱)."""

    def test_two_in_one_column(self):
        lines = compile_roll(RollRequest(FRACTETHYST, {3: [PERK_A, PERK_B]}))
        self.assertEqual(
            lines,
            [
                f"dimwishlist:item={FRACTETHYST}&perks={PERK_A}",
                f"dimwishlist:item={FRACTETHYST}&perks={PERK_B}",
            ],
        )

    def test_cartesian_product_2x2(self):
        lines = compile_roll(RollRequest(FRACTETHYST, {3: [PERK_A, PERK_B], 4: [PERK_C, PERK_D]}))
        # 2 x 2 = 4 줄, 줄 내부는 AND(col3,col4)
        self.assertEqual(len(lines), 4)
        self.assertIn(f"dimwishlist:item={FRACTETHYST}&perks={PERK_A},{PERK_C}", lines)
        self.assertIn(f"dimwishlist:item={FRACTETHYST}&perks={PERK_A},{PERK_D}", lines)
        self.assertIn(f"dimwishlist:item={FRACTETHYST}&perks={PERK_B},{PERK_C}", lines)
        self.assertIn(f"dimwishlist:item={FRACTETHYST}&perks={PERK_B},{PERK_D}", lines)

    def test_dedupe_within_column(self):
        lines = compile_roll(RollRequest(FRACTETHYST, {3: [PERK_A, PERK_A]}))
        self.assertEqual(lines, [f"dimwishlist:item={FRACTETHYST}&perks={PERK_A}"])


class TestTrashAndWildcard(unittest.TestCase):
    def test_trash_negates_hash(self):
        lines = compile_roll(RollRequest(FRACTETHYST, {3: [PERK_A]}, trash=True))
        self.assertEqual(lines, [f"dimwishlist:item=-{FRACTETHYST}&perks={PERK_A}"])

    def test_wildcard_uses_magic_id(self):
        lines = compile_roll(RollRequest(FRACTETHYST, {3: [PERK_A, PERK_B]}, wildcard=True))
        self.assertEqual(
            lines,
            [
                f"dimwishlist:item={WILDCARD_ITEM_ID}&perks={PERK_A}",
                f"dimwishlist:item={WILDCARD_ITEM_ID}&perks={PERK_B}",
            ],
        )

    def test_wildcard_and_trash_conflict(self):
        with self.assertRaises(CompileError):
            compile_roll(RollRequest(FRACTETHYST, {3: [PERK_A]}, wildcard=True, trash=True))


class TestEnhancedMapping(unittest.TestCase):
    def test_enhanced_mapped_to_base(self):
        ENHANCED = 9999999999  # 강화 퍽 해시(가상)
        base_map = {ENHANCED: PERK_A}
        lines = compile_roll(RollRequest(FRACTETHYST, {3: [ENHANCED]}), base_map=base_map)
        self.assertEqual(lines, [f"dimwishlist:item={FRACTETHYST}&perks={PERK_A}"])

    def test_enhanced_dedupes_with_base(self):
        ENHANCED = 9999999999
        base_map = {ENHANCED: PERK_A}
        # 기본 + 강화가 같은 열에 있으면 base 로 통일되어 1줄
        lines = compile_roll(RollRequest(FRACTETHYST, {3: [PERK_A, ENHANCED]}), base_map=base_map)
        self.assertEqual(lines, [f"dimwishlist:item={FRACTETHYST}&perks={PERK_A}"])


class TestNotesAndTags(unittest.TestCase):
    def test_note_appended(self):
        lines = compile_roll(RollRequest(FRACTETHYST, {3: [PERK_A]}, notes="좋은 PvP 롤"))
        self.assertEqual(lines, [f"dimwishlist:item={FRACTETHYST}&perks={PERK_A}#notes:좋은 PvP 롤"])

    def test_pipe_stripped_from_notes(self):
        out = sanitize_notes("foo|bar|baz")
        self.assertNotIn("|", out)

    def test_newline_becomes_literal_backslash_n(self):
        out = sanitize_notes("line1\nline2")
        self.assertEqual(out, "line1\\nline2")
        self.assertNotIn("\n", out)

    def test_tags_prefixed(self):
        body = build_note_text("강력함", ["PvP", "GM"])
        self.assertTrue(body.startswith("[PvP] [GM]"))
        self.assertIn("강력함", body)

    def test_tags_make_wishlistnotes_searchable(self):
        # wishlistnotes:pvp 는 소문자 부분일치 -> "[PvP]" 안에 "pvp" 포함
        body = build_note_text("", ["PvP"])
        self.assertIn("pvp", body.lower())

    def test_empty_note_no_suffix(self):
        lines = compile_roll(RollRequest(FRACTETHYST, {3: [PERK_A]}, notes="", tags=[]))
        self.assertEqual(lines, [f"dimwishlist:item={FRACTETHYST}&perks={PERK_A}"])


class TestFileAssembly(unittest.TestCase):
    def test_headers_and_structure(self):
        text = compile_wishlist(
            [
                RollRequest(FRACTETHYST, {3: [PERK_A], 4: [PERK_B]}, comment="프랙테시스트", tags=["PvP"]),
            ],
            title="내 크루시블 갓롤",
            description="현 시즌 PvP 종결 롤",
        )
        self.assertTrue(text.startswith("title:내 크루시블 갓롤\n"))
        self.assertIn("description:현 시즌 PvP 종결 롤", text)
        self.assertIn("// 프랙테시스트", text)
        self.assertIn(f"dimwishlist:item={FRACTETHYST}&perks={PERK_A},{PERK_B}#notes:[PvP]", text)
        self.assertTrue(text.endswith("\n"))

    def test_no_bom_lf_only(self):
        text = compile_wishlist([RollRequest(FRACTETHYST, {3: [PERK_A]})])
        self.assertFalse(text.startswith("﻿"))
        self.assertNotIn("\r", text)


class TestRoundTrip(unittest.TestCase):
    """emit 한 모든 줄이 DIM 파서 정규식에 부합하고, 의미가 보존되는지."""

    def test_all_emitted_lines_valid(self):
        text = compile_wishlist(
            [
                RollRequest(FRACTETHYST, {3: [PERK_A, PERK_B], 4: [PERK_C]}, notes="좋음", tags=["PvE"]),
                RollRequest(FRACTETHYST, {2: [PERK_D]}, trash=True, notes="별로"),
                RollRequest(FRACTETHYST, {3: [PERK_A]}, wildcard=True),
            ],
            title="테스트",
        )
        for line in text.splitlines():
            if line.startswith("dimwishlist:"):
                self.assertTrue(is_valid_line(line), f"파서 정규식 불일치: {line}")

    def test_roundtrip_semantics(self):
        line = compile_roll(RollRequest(FRACTETHYST, {3: [PERK_A], 4: [PERK_B]}, notes="hi"))[0]
        parsed = parse_line(line)
        self.assertEqual(parsed["item_hash"], FRACTETHYST)
        self.assertEqual(parsed["perks"], {PERK_A, PERK_B})
        self.assertFalse(parsed["is_undesirable"])
        self.assertFalse(parsed["is_wildcard"])
        self.assertEqual(parsed["notes"], "hi")

    def test_roundtrip_trash(self):
        line = compile_roll(RollRequest(FRACTETHYST, {3: [PERK_A]}, trash=True))[0]
        parsed = parse_line(line)
        self.assertTrue(parsed["is_undesirable"])
        self.assertEqual(parsed["item_hash"], FRACTETHYST)

    def test_roundtrip_wildcard(self):
        line = compile_roll(RollRequest(FRACTETHYST, {3: [PERK_A]}, wildcard=True))[0]
        parsed = parse_line(line)
        self.assertTrue(parsed["is_wildcard"])
        self.assertFalse(parsed["is_undesirable"])

    def test_note_with_pipe_does_not_truncate_perks(self):
        # 노트에 파이프를 넣어도 sanitize 로 제거되어 파싱이 깨지지 않아야 함
        line = compile_roll(RollRequest(FRACTETHYST, {3: [PERK_A]}, notes="a|b"))[0]
        self.assertTrue(is_valid_line(line))
        parsed = parse_line(line)
        self.assertEqual(parsed["perks"], {PERK_A})


class TestVariantExpansion(unittest.TestCase):
    """복각/홀로포일 변형 확장 — 같은 롤이 변형 hash 들에도 emit 되어야 함."""

    SIBLING_HOLO = 9991111   # 홀로포일(동일 퍽 풀)
    SIBLING_OLD = 9992222    # 구버전 복각(PERK_B 못 굴림)

    def test_holofoil_gets_same_roll(self):
        roll = RollRequest(
            FRACTETHYST, {3: [PERK_A], 4: [PERK_B]},
            variant_hashes=[self.SIBLING_HOLO],
            variant_pools={self.SIBLING_HOLO: {PERK_A, PERK_B}},
        )
        lines = compile_roll(roll)
        self.assertIn(f"dimwishlist:item={FRACTETHYST}&perks={PERK_A},{PERK_B}", lines)
        self.assertIn(f"dimwishlist:item={self.SIBLING_HOLO}&perks={PERK_A},{PERK_B}", lines)

    def test_variant_missing_perk_is_skipped(self):
        # 구버전이 PERK_B 를 못 굴리면(제약 열이 비면) 그 변형 줄은 생략
        roll = RollRequest(
            FRACTETHYST, {3: [PERK_A], 4: [PERK_B]},
            variant_hashes=[self.SIBLING_OLD],
            variant_pools={self.SIBLING_OLD: {PERK_A}},  # PERK_B 없음
        )
        lines = compile_roll(roll)
        self.assertIn(f"dimwishlist:item={FRACTETHYST}&perks={PERK_A},{PERK_B}", lines)
        self.assertFalse(any(str(self.SIBLING_OLD) in ln for ln in lines))

    def test_variant_partial_or_column_filters_to_available(self):
        # OR 열 [A,B] 중 변형이 A 만 굴리면 그 변형 줄은 A 만
        roll = RollRequest(
            FRACTETHYST, {3: [PERK_A, PERK_B]},
            variant_hashes=[self.SIBLING_OLD],
            variant_pools={self.SIBLING_OLD: {PERK_A}},
        )
        lines = compile_roll(roll)
        self.assertIn(f"dimwishlist:item={self.SIBLING_OLD}&perks={PERK_A}", lines)
        self.assertNotIn(f"dimwishlist:item={self.SIBLING_OLD}&perks={PERK_B}", lines)

    def test_trash_negates_all_variant_hashes(self):
        roll = RollRequest(
            FRACTETHYST, {3: [PERK_A]}, trash=True,
            variant_hashes=[self.SIBLING_HOLO],
            variant_pools={self.SIBLING_HOLO: {PERK_A}},
        )
        lines = compile_roll(roll)
        self.assertIn(f"dimwishlist:item=-{FRACTETHYST}&perks={PERK_A}", lines)
        self.assertIn(f"dimwishlist:item=-{self.SIBLING_HOLO}&perks={PERK_A}", lines)

    def test_wildcard_ignores_variants(self):
        # 와일드카드는 이미 전체 매칭이라 변형 확장 안 함
        roll = RollRequest(
            FRACTETHYST, {3: [PERK_A]}, wildcard=True,
            variant_hashes=[self.SIBLING_HOLO],
            variant_pools={self.SIBLING_HOLO: {PERK_A}},
        )
        lines = compile_roll(roll)
        self.assertEqual(len(lines), 1)
        self.assertTrue(parse_line(lines[0])["is_wildcard"])

    def test_all_emitted_lines_valid(self):
        roll = RollRequest(
            FRACTETHYST, {3: [PERK_A], 4: [PERK_B]},
            variant_hashes=[self.SIBLING_HOLO, self.SIBLING_OLD],
            variant_pools={self.SIBLING_HOLO: {PERK_A, PERK_B}, self.SIBLING_OLD: {PERK_A, PERK_B}},
        )
        lines = compile_roll(roll)
        for ln in lines:
            self.assertTrue(is_valid_line(ln), ln)
        # 주 + 2개 변형 = 3줄, 모두 고유
        self.assertEqual(len(lines), 3)
        self.assertEqual(len(set(lines)), 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
