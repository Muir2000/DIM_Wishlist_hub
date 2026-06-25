"""DIM식 텍스트 쿼리 파서/컴파일러 단위 테스트.

순수 컴파일(토크나이즈/파싱/SQL 생성)만 검증 — DB 불필요.
실행: backend/ 에서 `python -m unittest discover -s tests`
"""
import unittest

from app.query import QueryError, compile_query, tokenize


class TestTokenize(unittest.TestCase):
    def test_basic_split(self):
        self.assertEqual(tokenize("is:arc is:handcannon"), ["is:arc", "is:handcannon"])

    def test_quoted_keeps_spaces(self):
        self.assertEqual(tokenize('perkname:"kill clip"'), ['perkname:"kill clip"'])

    def test_parens_are_tokens(self):
        self.assertEqual(tokenize("(is:arc or is:void)"),
                         ["(", "is:arc", "or", "is:void", ")"])

    def test_empty(self):
        self.assertEqual(tokenize("   "), [])


class TestCompile(unittest.TestCase):
    def test_empty_query(self):
        self.assertEqual(compile_query(""), ("", []))

    def test_is_subtype_en_and_ko(self):
        en, p1 = compile_query("is:handcannon")
        ko, p2 = compile_query("is:핸드캐논")
        self.assertIn("weapon_subtype = ?", en)
        self.assertEqual(p1, [9])
        self.assertEqual((en, p1), (ko, p2))  # EN/KO 동일 컴파일

    def test_is_element(self):
        sql, p = compile_query("is:solar")
        self.assertIn("default_damage_type = ?", sql)
        self.assertEqual(p, ["Solar"])

    def test_implicit_and(self):
        sql, p = compile_query("is:handcannon is:arc")
        self.assertIn(" AND ", sql)
        self.assertEqual(p, [9, "Arc"])

    def test_or_grouping(self):
        sql, p = compile_query("(is:arc or is:void) is:exotic")
        self.assertIn(" OR ", sql)
        self.assertIn(" AND ", sql)
        self.assertEqual(p, ["Arc", "Void", 6])

    def test_negation_dash_and_not(self):
        a = compile_query("-is:exotic")
        b = compile_query("not is:exotic")
        self.assertTrue(a[0].startswith("NOT ("))
        self.assertEqual(a, b)

    def test_stat_ops(self):
        sql, p = compile_query("stat:range:>=50")
        self.assertIn("ws.stat_key = ?", sql)
        self.assertIn("ws.value >= ?", sql)
        self.assertEqual(p, ["range", 50.0])

    def test_stat_range(self):
        sql, p = compile_query("stat:handling:40-60")
        self.assertIn("ws.value >= ? AND ws.value <= ?", sql)
        self.assertEqual(p, ["handling", 40.0, 60.0])

    def test_stat_bare_is_equality(self):
        sql, p = compile_query("stat:rpm:180")
        self.assertIn("ws.value = ?", sql)
        self.assertEqual(p, ["rpm", 180.0])

    def test_perkname_quoted(self):
        sql, p = compile_query('perkname:"kill clip"')
        self.assertIn("weapon_perks", sql)
        self.assertEqual(p, ["%kill clip%", "%kill clip%"])

    def test_params_are_bound_not_inlined(self):
        # 인젝션 방지: 값이 SQL 문자열에 인라인되지 않고 ? 로만 들어가야 함
        sql, p = compile_query('name:"x\'; DROP TABLE weapons;--"')
        self.assertNotIn("DROP TABLE", sql)
        self.assertEqual(sql.count("?"), len(p))

    def test_bare_text_is_name(self):
        sql, p = compile_query("용광로")
        self.assertIn("name_ko LIKE ?", sql)
        self.assertEqual(p, ["%용광로%", "%용광로%"])

    # --- 에러 케이스 ---
    def test_unknown_is_token(self):
        with self.assertRaises(QueryError):
            compile_query("is:없는무기")

    def test_unknown_stat_key(self):
        with self.assertRaises(QueryError):
            compile_query("stat:없는스탯:>=5")

    def test_unknown_keyword(self):
        with self.assertRaises(QueryError):
            compile_query("foo:bar")

    def test_unbalanced_paren(self):
        with self.assertRaises(QueryError):
            compile_query("( is:arc")

    def test_empty_value(self):
        with self.assertRaises(QueryError):
            compile_query("perkname:")


if __name__ == "__main__":
    unittest.main(verbosity=2)
