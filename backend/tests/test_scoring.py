"""점수화 엔진 단위 테스트 (v4: 스코프 블렌드 · 열 비중 · 동적 만점 · coverage 캡).

실행 (backend/ 에서): python -m unittest discover -s tests -t .
인메모리 SQLite 에 4열(총열/탄창/특성/특성) 무기 + 동일 종류/프레임·타 종류 무기를 넣고 검증.
"""
import unittest

from app import db, scoring

# 무기들 (퍽 해시는 무기 간 공유 — 실게임처럼 같은 퍽=같은 plug_hash)
WEAPON = 111      # 등록(위시리스트 있음), 종류 9 / 프레임 500
SAME = 222        # 동일 종류/프레임, 미등록 → 종류·프레임 전이 평가(캡 0.40)
OTHER = 333       # 다른 종류(24)/프레임(600) → 신호 없음
TYPEONLY = 444    # 동일 종류(9) / 다른 프레임(999) → 종류 비중(0.15)만
TYPE_A, FRAME_A = 9, 500
TYPE_B, FRAME_B = 24, 600

# 퍽 (열, 슬롯) — best=*1
P_B1, P_B2 = 10, 11   # barrel
P_M1, P_M2 = 20, 21   # magazine
P_T1, P_T2 = 30, 31   # trait (열 2)
P_U1, P_U2 = 40, 41   # trait (열 3)
COLS = [(0, "barrel", [P_B1, P_B2]), (1, "magazine", [P_M1, P_M2]),
        (2, "trait", [P_T1, P_T2]), (3, "trait", [P_U1, P_U2])]

# 동적 만점 = 0.35 + 0.35 + 1.0 + 1.0
MAXP = 2.7


def make_conn():
    conn = db.connect(":memory:")
    db.apply_schema(conn)
    cur = conn.cursor()
    for wh, ty, fr in [(WEAPON, TYPE_A, FRAME_A), (SAME, TYPE_A, FRAME_A),
                       (OTHER, TYPE_B, FRAME_B), (TYPEONLY, TYPE_A, 999)]:
        cur.execute("INSERT INTO weapons (item_hash,name_ko,weapon_subtype,frame_hash,redacted) VALUES (?,?,?,?,0)",
                    (wh, f"w{wh}", ty, fr))
        for ci, kind, plugs in COLS:
            for ph in plugs:
                cur.execute("INSERT OR IGNORE INTO perks (plug_hash,name_ko) VALUES (?,?)", (ph, f"p{ph}"))
                cur.execute("INSERT INTO weapon_perks (weapon_hash,column_index,column_kind,plug_hash) VALUES (?,?,?,?)",
                            (wh, ci, kind, ph))
    for k, v in {"handling": 40, "range": 80, "stability": 50}.items():
        cur.execute("INSERT INTO weapon_stats (weapon_hash,stat_key,value) VALUES (?,?,?)", (WEAPON, k, v))
    cur.execute("INSERT INTO perk_stats (plug_hash,stat_key,value) VALUES (?,?,?)", (P_T1, "handling", 20))
    conn.commit()
    return conn


def full_roll(wh, trash=False):
    return {"weapon_hash": wh, "columns": {"0": [P_B1], "1": [P_M1], "2": [P_T1], "3": [P_U1]}, "trash": trash}


def ctx_full(conn, n=1):
    """WEAPON 풀롤 n회 학습한 컨텍스트. n=1 이면 조합(쌍 count<2) 미생성."""
    return scoring.derive_context(conn, [full_roll(WEAPON) for _ in range(n)])


WL = {"use_wishlist_weights": True}


class TestRollStats(unittest.TestCase):
    def test_perk_delta_applied(self):
        conn = make_conn()
        s = scoring.roll_stats(conn, WEAPON, [P_T1])
        self.assertEqual(s["handling"], 60)   # 40 + 20
        self.assertEqual(s["range"], 80)


class TestNoSignal(unittest.TestCase):
    def test_none_when_no_signal(self):
        conn = make_conn()
        self.assertIsNone(scoring.score_roll(conn, WEAPON, [P_T1], {})["score"])

    def test_stats_still_computed(self):
        conn = make_conn()
        self.assertEqual(scoring.score_roll(conn, WEAPON, [P_T1], {})["stats"]["handling"], 60)

    def test_stats_not_in_score(self):
        conn = make_conn()
        prof = {"stat_weights": {"handling": 1.0}, "use_wishlist_weights": False}
        self.assertIsNone(scoring.score_roll(conn, WEAPON, [P_T1], prof)["score"])


class TestDeriveWeights(unittest.TestCase):
    def test_derive_global(self):
        w = scoring.derive_wishlist_weights([
            {"columns": {"2": [P_T1]}, "trash": False},
            {"columns": {"2": [P_T2]}, "trash": True},
        ])
        self.assertEqual(w[P_T1], 1.0)
        self.assertEqual(w[P_T2], -1.0)


class TestDynamicMax(unittest.TestCase):
    def test_full_roll_is_100(self):
        conn = make_conn()
        r = scoring.score_roll(conn, WEAPON, [P_B1, P_M1, P_T1, P_U1], WL, context=ctx_full(conn))
        self.assertEqual(r["score"], 100.0)
        self.assertEqual(r["classification"], "god")
        self.assertEqual(r["max_possible"], MAXP)
        self.assertEqual(r["coverage"], 1.0)

    def test_two_traits_below_full(self):
        conn = make_conn()
        s = scoring.score_roll(conn, WEAPON, [P_T1, P_U1], WL, context=ctx_full(conn))["score"]
        self.assertAlmostEqual(s, 74.1, delta=0.2)   # 2.0/2.7, 단일 등록이라 조합 없음
        self.assertLess(s, 100.0)

    def test_trait_beats_barrel(self):
        conn = make_conn()
        ctx = ctx_full(conn)
        t = scoring.score_roll(conn, WEAPON, [P_T1], WL, context=ctx)["score"]
        b = scoring.score_roll(conn, WEAPON, [P_B1], WL, context=ctx)["score"]
        self.assertGreater(t, b)                      # 특성(1.0) > 총열(0.35)
        self.assertAlmostEqual(t, 37.0, delta=0.2)    # 1.0/2.7
        self.assertAlmostEqual(b, 13.0, delta=0.2)    # 0.35/2.7


class TestCoverageCap(unittest.TestCase):
    def test_unregistered_capped_at_40(self):
        conn = make_conn()
        r = scoring.score_roll(conn, SAME, [P_B1, P_M1, P_T1, P_U1], WL, context=ctx_full(conn))
        self.assertAlmostEqual(r["coverage"], 0.4, delta=0.001)
        self.assertLessEqual(r["score"], 40.0)
        self.assertAlmostEqual(r["score"], 40.0, delta=0.1)   # 풀롤이면 정확히 캡에 닿음

    def test_other_type_no_signal(self):
        conn = make_conn()
        self.assertIsNone(scoring.score_roll(conn, OTHER, [P_T1], WL, context=ctx_full(conn))["score"])


class TestScopeBlend(unittest.TestCase):
    def test_registered_weight_is_1(self):
        conn = make_conn()
        wmap, has = scoring.perk_weight_map(conn, WEAPON, [P_T1], WL, context=ctx_full(conn))
        self.assertTrue(has)
        self.assertAlmostEqual(wmap[P_T1], 1.0, delta=0.001)   # 0.6+0.25+0.15

    def test_unregistered_weight_is_040(self):
        conn = make_conn()
        wmap, has = scoring.perk_weight_map(conn, SAME, [P_T1], WL, context=ctx_full(conn))
        self.assertTrue(has)
        self.assertAlmostEqual(wmap[P_T1], 0.40, delta=0.001)  # 프레임0.25 + 종류0.15

    def test_type_only_weight_is_015(self):
        conn = make_conn()
        wmap, _ = scoring.perk_weight_map(conn, TYPEONLY, [P_T1], WL, context=ctx_full(conn))
        self.assertAlmostEqual(wmap[P_T1], 0.15, delta=0.001)  # 종류만

    def test_coverage_helper(self):
        conn = make_conn()
        ctx = ctx_full(conn)
        self.assertAlmostEqual(scoring.coverage(conn, WEAPON, WL, context=ctx)[0], 1.0, delta=0.001)
        self.assertAlmostEqual(scoring.coverage(conn, SAME, WL, context=ctx)[0], 0.40, delta=0.001)
        self.assertAlmostEqual(scoring.coverage(conn, TYPEONLY, WL, context=ctx)[0], 0.15, delta=0.001)


class TestSynergyAndClassify(unittest.TestCase):
    def test_synergy_bonus(self):
        conn = make_conn()
        prof = {"perk_weights": {str(P_T1): 1.0},
                "synergy_bonuses": [{"perks": [P_T1, P_U1], "bonus": 5}],
                "use_wishlist_weights": False}
        with_pair = scoring.score_roll(conn, WEAPON, [P_T1, P_U1], prof)["score"]
        without = scoring.score_roll(conn, WEAPON, [P_T1], prof)["score"]
        self.assertGreater(with_pair, without)       # 조합 매칭 시 가점

    def test_combo_capped(self):
        # 거대한 bonus 라도 COMBO_CONTRIB_CAP(0.5) 로 제한
        conn = make_conn()
        prof = {"perk_weights": {str(P_T1): 1.0},
                "synergy_bonuses": [{"perks": [P_T1, P_U1], "bonus": 999}],
                "use_wishlist_weights": False}
        r = scoring.score_roll(conn, WEAPON, [P_T1, P_U1], prof)
        self.assertAlmostEqual(r["breakdown"]["synergy"], 100.0 * 0.5 / MAXP, delta=0.2)

    def test_classify_thresholds(self):
        self.assertEqual(scoring.classify(80, {"god": 75, "viable": 40}), "god")
        self.assertEqual(scoring.classify(50, {"god": 75, "viable": 40}), "viable")
        self.assertEqual(scoring.classify(10, {"god": 75, "viable": 40}), "trash")


class TestProfileNormalize(unittest.TestCase):
    def test_defaults(self):
        p = scoring.normalize_profile(None)
        self.assertEqual(p["thresholds"]["god"], 75.0)
        self.assertEqual(p["thresholds"]["viable"], 40.0)
        self.assertEqual(p["scope_blend"]["weapon"], 0.6)
        self.assertEqual(p["column_weights"]["trait"], 1.0)
        self.assertTrue(p["use_wishlist_weights"])

    def test_perk_weights_keys_coerced_to_int(self):
        p = scoring.normalize_profile({"perk_weights": {"30": 3.0}})
        self.assertEqual(p["perk_weights"][30], 3.0)

    def test_custom_scope_blend_merges_defaults(self):
        p = scoring.normalize_profile({"scope_blend": {"weapon": 0.8}})
        self.assertEqual(p["scope_blend"]["weapon"], 0.8)
        self.assertEqual(p["scope_blend"]["frame"], 0.25)   # 미지정은 기본 유지


class TestContextAware(unittest.TestCase):
    def test_same_perk_differs_by_type(self):
        conn = make_conn()
        rolls = [{"weapon_hash": WEAPON, "columns": {"2": [P_T1]}, "trash": False} for _ in range(3)]
        ctx = scoring.derive_context(conn, rolls)
        reg = scoring.score_roll(conn, WEAPON, [P_T1], WL, context=ctx)["score"]
        other = scoring.score_roll(conn, OTHER, [P_T1], WL, context=ctx)["score"]
        self.assertIsNotNone(reg)
        self.assertIsNone(other)

    def test_derive_context_scopes(self):
        conn = make_conn()
        ctx = scoring.derive_context(conn, [{"weapon_hash": WEAPON, "columns": {"2": [P_T1]}, "trash": False}])
        self.assertIn("type:9", ctx["weights"])
        self.assertIn("frame:500", ctx["weights"])
        self.assertIn("weapon:111", ctx["weights"])
        self.assertNotIn("type:24", ctx["weights"])

    def test_context_combo_bonus(self):
        conn = make_conn()
        ctx = ctx_full(conn, n=3)               # 풀롤 3회 → 쌍 count≥2 → 조합 학습
        both = scoring.score_roll(conn, WEAPON, [P_T1, P_U1], WL, context=ctx)["score"]
        one = scoring.score_roll(conn, WEAPON, [P_T1], WL, context=ctx)["score"]
        self.assertGreater(both, one)


if __name__ == "__main__":
    unittest.main(verbosity=2)
