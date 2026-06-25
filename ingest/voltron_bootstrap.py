"""voltron.txt (커뮤니티 집계 위시리스트) -> roll_stats 부트스트랩 (Phase 5).

light.gg 식 인기도 막대와 메타 대시보드는 데이터 원본이 필요한데, 우리에겐 자체
유저 데이터가 아직 없다(콜드스타트). 그래서 GitHub 에 호스팅된 voltron.txt 를 파싱해
무기별·열별 퍽 추천 빈도를 집계, 출시 시점부터 통계를 채운다.

전제: 먼저 manifest_ingest 로 weapon_perks 가 적재되어 있어야 한다(퍽->열 매핑에 사용).
desirable 롤만 집계(트래시/와일드카드 제외).

실행 (repo 루트에서):
    python -m ingest.voltron_bootstrap
    python -m ingest.voltron_bootstrap --file path/to/voltron.txt   # 로컬 파일 사용
"""
from __future__ import annotations

import argparse
from collections import defaultdict

from . import _bootstrap_path  # noqa: F401

import httpx  # noqa: E402
from app import config, db  # noqa: E402
from app.compiler import parse_line  # noqa: E402


def _load_text(file: str = None) -> str:
    if file:
        with open(file, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    print(f"voltron 다운로드: {config.VOLTRON_URL}")
    r = httpx.get(config.VOLTRON_URL, timeout=120.0, follow_redirects=True)
    r.raise_for_status()
    return r.text


def bootstrap(file: str = None) -> None:
    conn = db.connect(config.DB_PATH)
    db.apply_schema(conn)

    # 퍽 -> 그 무기에서의 열 인덱스 매핑 (한 퍽이 여러 열에 있을 수 있어 set)
    perk_cols = defaultdict(set)
    for r in conn.execute("SELECT weapon_hash, column_index, plug_hash FROM weapon_perks"):
        perk_cols[(r["weapon_hash"], r["plug_hash"])].add(r["column_index"])

    if not perk_cols:
        print("경고: weapon_perks 가 비어 있습니다. 먼저 `python -m ingest.manifest_ingest` 를 실행하세요.")

    text = _load_text(file)
    counts = defaultdict(int)  # (weapon, col, plug) -> count
    n_lines = 0
    for line in text.splitlines():
        if not line.startswith("dimwishlist:"):
            continue
        parsed = parse_line(line)
        if not parsed or parsed["is_wildcard"] or parsed["is_undesirable"]:
            continue
        wh = parsed["item_hash"]
        for ph in parsed["perks"]:
            cols = perk_cols.get((wh, ph))
            if not cols:
                continue  # 매니페스트에 없는(구버전) 퍽은 스킵
            for col in cols:
                counts[(wh, col, ph)] += 1
        n_lines += 1

    cur = conn.cursor()
    cur.execute("DELETE FROM roll_stats WHERE source='voltron'")
    for (wh, col, ph), c in counts.items():
        cur.execute(
            """INSERT OR REPLACE INTO roll_stats
               (weapon_hash,column_index,plug_hash,count,source) VALUES (?,?,?,?, 'voltron')""",
            (wh, col, ph, c),
        )
    conn.commit()
    conn.close()
    print(f"완료: {n_lines} 롤 라인 파싱, {len(counts)} (무기,열,퍽) 통계 기록.")


def main():
    ap = argparse.ArgumentParser(description="voltron.txt -> roll_stats 부트스트랩")
    ap.add_argument("--file", default=None, help="로컬 voltron.txt 경로(미지정 시 URL 다운로드)")
    args = ap.parse_args()
    bootstrap(file=args.file)


if __name__ == "__main__":
    main()
