"""샘플(seed) 데이터 생성기.

Bungie API 키 없이도 앱이 즉시 구동되도록, 인지 가능한 무기/퍼크로 구성된
seed_data.json 을 결정적으로 생성한다. 실제 매니페스트 적재 시 이 데이터는 대체된다.

실행:  python build_seed.py   (backend/seed/ 에서)
주의:  seed 의 퍼크 해시는 합성값이므로, seed 모드에서 내보낸 .txt 는 DIM 에서
       실제 매칭되지 않는다(데모용). 실사용은 매니페스트 적재 후.
"""
import json
import os

# --- 공유 퍼크 카탈로그 (해시 고정 -> 여러 무기에 공유되어 메타 집계가 의미를 가짐) ---
BARRELS = {
    2015611001: ("코르크스크루 라이플링", "Corkscrew Rifling"),
    2015611002: ("화살촉 제동기", "Arrowhead Brake"),
    2015611003: ("풀 보어", "Full Bore"),
    2015611004: ("라이플 총열", "Rifled Barrel"),
    2015611005: ("풀 초크", "Full Choke"),
    2015611006: ("연마된 총열", "Smallbore"),
}
MAGS = {
    3015611001: ("점결식 탄환", "Accurized Rounds"),
    3015611002: ("전술 탄창", "Tactical Mag"),
    3015611003: ("확장 탄창", "Extended Mag"),
    3015611004: ("추가 탄창", "Appended Mag"),
    3015611005: ("어썰트 탄창", "Assault Mag"),
}
TRAITS = {
    1015611457: ("무법자", "Outlaw"),
    1015611458: ("킬 클립", "Kill Clip"),
    1015611459: ("광란", "Frenzy"),
    1015611460: ("재구성", "Reconstruction"),
    1015611461: ("존속", "Subsistence"),
    1015611462: ("폭주", "Rampage"),
    1015611463: ("개방 일제사격", "Opening Shot"),
    1015611464: ("네 번째 시도", "Fourth Time's the Charm"),
    1015611465: ("선 모먼트", "Zen Moment"),
    1015611466: ("묘비", "Headstone"),
    1015611467: ("멀티킬 클립", "Multikill Clip"),
    1015611468: ("미끄러지기", "Slideshot"),
    1015611469: ("탄막", "Demolitionist"),
    1015611470: ("골절", "Adagio"),
}


def perk(plug_hash, kind, cat_table, curated=False, can_roll=True):
    ko, en = cat_table[plug_hash]
    return {
        "plug_hash": plug_hash,
        "name_ko": ko,
        "name_en": en,
        "icon": None,
        "plug_category": kind,
        "is_enhanced": 0,
        "base_plug_hash": None,
        "currently_can_roll": 1 if can_roll else 0,
        "is_curated": 1 if curated else 0,
    }


def column(index, kind, items):
    return {"index": index, "kind": kind, "perks": items}


WEAPONS = [
    {
        "item_hash": 3184681056,
        "name_ko": "프랙테시스트",
        "name_en": "Fractethyst",
        "tier": 5,
        "weapon_subtype": 7,   # Shotgun
        "ammo_type": 2,        # Special
        "slot": "Energy",
        "default_damage_type": "Stasis",
        "columns": [
            column(0, "barrel", [perk(2015611004, "barrel", BARRELS, curated=True),
                                 perk(2015611005, "barrel", BARRELS),
                                 perk(2015611006, "barrel", BARRELS)]),
            column(1, "magazine", [perk(3015611001, "magazine", MAGS, curated=True),
                                   perk(3015611004, "magazine", MAGS),
                                   perk(3015611005, "magazine", MAGS)]),
            column(2, "trait", [perk(1015611463, "trait", TRAITS, curated=True),
                                perk(1015611468, "trait", TRAITS),
                                perk(1015611460, "trait", TRAITS),
                                perk(1015611461, "trait", TRAITS)]),
            column(3, "trait", [perk(1015611466, "trait", TRAITS, curated=True),
                                perk(1015611462, "trait", TRAITS),
                                perk(1015611459, "trait", TRAITS),
                                perk(1015611458, "trait", TRAITS)]),
        ],
    },
    {
        "item_hash": 2009277538,
        "name_ko": "팔린드롬",
        "name_en": "The Palindrome",
        "tier": 5,
        "weapon_subtype": 9,   # Hand Cannon
        "ammo_type": 1,        # Primary
        "slot": "Energy",
        "default_damage_type": "Void",
        "columns": [
            column(0, "barrel", [perk(2015611001, "barrel", BARRELS, curated=True),
                                 perk(2015611002, "barrel", BARRELS),
                                 perk(2015611003, "barrel", BARRELS)]),
            column(1, "magazine", [perk(3015611001, "magazine", MAGS),
                                   perk(3015611002, "magazine", MAGS, curated=True),
                                   perk(3015611003, "magazine", MAGS)]),
            column(2, "trait", [perk(1015611457, "trait", TRAITS, curated=True),
                                perk(1015611464, "trait", TRAITS),
                                perk(1015611460, "trait", TRAITS),
                                perk(1015611465, "trait", TRAITS)]),
            column(3, "trait", [perk(1015611458, "trait", TRAITS, curated=True),
                                perk(1015611462, "trait", TRAITS),
                                perk(1015611467, "trait", TRAITS),
                                perk(1015611463, "trait", TRAITS)]),
        ],
    },
    {
        "item_hash": 3851176026,
        "name_ko": "BxR-55 배틀러",
        "name_en": "BxR-55 Battler",
        "tier": 5,
        "weapon_subtype": 13,  # Pulse Rifle
        "ammo_type": 1,
        "slot": "Kinetic",
        "default_damage_type": "Kinetic",
        "columns": [
            column(0, "barrel", [perk(2015611001, "barrel", BARRELS),
                                 perk(2015611003, "barrel", BARRELS, curated=True),
                                 perk(2015611006, "barrel", BARRELS)]),
            column(1, "magazine", [perk(3015611001, "magazine", MAGS, curated=True),
                                   perk(3015611002, "magazine", MAGS),
                                   perk(3015611003, "magazine", MAGS)]),
            column(2, "trait", [perk(1015611457, "trait", TRAITS),
                                perk(1015611460, "trait", TRAITS, curated=True),
                                perk(1015611461, "trait", TRAITS),
                                perk(1015611465, "trait", TRAITS)]),
            column(3, "trait", [perk(1015611458, "trait", TRAITS),
                                perk(1015611459, "trait", TRAITS, curated=True),
                                perk(1015611462, "trait", TRAITS),
                                perk(1015611470, "trait", TRAITS)]),
        ],
    },
    {
        "item_hash": 2933076918,
        "name_ko": "퍼널웹",
        "name_en": "Funnelweb",
        "tier": 5,
        "weapon_subtype": 24,  # SMG
        "ammo_type": 1,
        "slot": "Energy",
        "default_damage_type": "Void",
        "columns": [
            column(0, "barrel", [perk(2015611001, "barrel", BARRELS, curated=True),
                                 perk(2015611002, "barrel", BARRELS),
                                 perk(2015611006, "barrel", BARRELS)]),
            column(1, "magazine", [perk(3015611001, "magazine", MAGS),
                                   perk(3015611003, "magazine", MAGS, curated=True),
                                   perk(3015611004, "magazine", MAGS)]),
            column(2, "trait", [perk(1015611461, "trait", TRAITS, curated=True),
                                perk(1015611460, "trait", TRAITS),
                                perk(1015611469, "trait", TRAITS),
                                perk(1015611457, "trait", TRAITS)]),
            column(3, "trait", [perk(1015611459, "trait", TRAITS, curated=True),
                                perk(1015611462, "trait", TRAITS),
                                perk(1015611458, "trait", TRAITS),
                                perk(1015611470, "trait", TRAITS)]),
        ],
    },
]

# --- roll_stats (메타/인기도 부트스트랩) : 합성 빈도 ---
# 무기별·열별 퍼크 인기도(커뮤니티 voltron 부트스트랩을 흉내).
POPULARITY = {
    3184681056: {2: {1015611463: 120, 1015611460: 95, 1015611461: 60, 1015611468: 30},
                 3: {1015611466: 140, 1015611459: 110, 1015611462: 70, 1015611458: 45}},
    2009277538: {2: {1015611457: 200, 1015611460: 130, 1015611465: 80, 1015611464: 40},
                 3: {1015611458: 175, 1015611467: 120, 1015611462: 90, 1015611463: 35}},
    3851176026: {2: {1015611460: 150, 1015611457: 140, 1015611461: 70, 1015611465: 55},
                 3: {1015611459: 160, 1015611458: 130, 1015611470: 60, 1015611462: 50}},
    2933076918: {2: {1015611461: 180, 1015611460: 100, 1015611457: 75, 1015611469: 65},
                 3: {1015611459: 190, 1015611458: 120, 1015611462: 80, 1015611470: 40}},
}


# --- 스탯 정의 (key 는 정규화 키, hash 는 실제 Bungie statHash 참고용) ---
STAT_DEFS = [
    {"stat_hash": 4043523819, "key": "impact", "name_ko": "충격력", "name_en": "Impact"},
    {"stat_hash": 1240592695, "key": "range", "name_ko": "사거리", "name_en": "Range"},
    {"stat_hash": 155624089, "key": "stability", "name_ko": "안정성", "name_en": "Stability"},
    {"stat_hash": 943549884, "key": "handling", "name_ko": "조작성", "name_en": "Handling"},
    {"stat_hash": 4188031367, "key": "reload", "name_ko": "재장전 속도", "name_en": "Reload Speed"},
    {"stat_hash": 3871231066, "key": "magazine", "name_ko": "탄창", "name_en": "Magazine"},
    {"stat_hash": 1345867579, "key": "aim_assist", "name_ko": "조준 보정", "name_en": "Aim Assistance"},
    {"stat_hash": 2715839340, "key": "recoil", "name_ko": "반동 방향", "name_en": "Recoil Direction"},
    {"stat_hash": 3022809290, "key": "zoom", "name_ko": "확대", "name_en": "Zoom"},
    {"stat_hash": 4284893561, "key": "rpm", "name_ko": "분당 발사수", "name_en": "Rounds Per Minute"},
]

# --- 무기 기본 표시 스탯 (0~100, rpm/magazine 은 raw) ---
WEAPON_STATS = {
    3184681056: {"impact": 80, "range": 35, "stability": 45, "handling": 52, "reload": 50, "magazine": 5, "rpm": 55, "aim_assist": 48},
    2009277538: {"impact": 84, "range": 68, "stability": 50, "handling": 47, "reload": 45, "magazine": 11, "rpm": 140, "aim_assist": 70},
    3851176026: {"impact": 27, "range": 62, "stability": 55, "handling": 40, "reload": 42, "magazine": 37, "rpm": 340, "aim_assist": 65},
    2933076918: {"impact": 22, "range": 40, "stability": 60, "handling": 58, "reload": 53, "magazine": 37, "rpm": 900, "aim_assist": 72},
}

# --- 퍽 스탯 델타 (배럴/탄창; 특성은 보통 기본 스탯 미변경) ---
PERK_STAT_DELTAS = {
    2015611001: {"range": 5, "stability": 5, "handling": 5},   # 코르크스크루 라이플링
    2015611002: {"handling": 15},                               # 화살촉 제동기
    2015611003: {"range": 10, "stability": -10, "handling": -5},# 풀 보어
    2015611004: {"range": 25, "handling": -10},                 # 라이플 총열(산탄)
    2015611005: {"range": 5, "stability": 5},                   # 풀 초크
    2015611006: {"range": 7, "stability": 7},                   # 연마된 총열
    3015611001: {"range": 10},                                  # 점결식 탄환
    3015611002: {"stability": 10, "reload": 10},                # 전술 탄창
    3015611003: {"reload": -10, "handling": -5},                # 확장 탄창
    3015611005: {"stability": 10},                              # 어썰트 탄창
}


# --- 무기 프레임(고유 특성) : (이름, frame_hash) ---
FRAMES = {
    3184681056: ("경량 프레임", 9001),      # 프랙테시스트
    2009277538: ("적응형 프레임", 9002),    # 팔린드롬
    3851176026: ("고속 연사 프레임", 9003),  # BxR-55
    2933076918: ("적응형 프레임", 9002),    # 퍼널웹 (팔린드롬과 동일 프레임 — 프레임 집계 데모)
}


def build():
    roll_stats = []
    for whash, cols in POPULARITY.items():
        for col_idx, perks in cols.items():
            for plug_hash, count in perks.items():
                roll_stats.append({
                    "weapon_hash": whash,
                    "column_index": col_idx,
                    "plug_hash": plug_hash,
                    "count": count,
                    "source": "voltron",
                })
    # 무기/퍼크에 스탯·프레임 부착
    for w in WEAPONS:
        w["stats"] = WEAPON_STATS.get(w["item_hash"], {})
        fr = FRAMES.get(w["item_hash"])
        if fr:
            w["frame"], w["frame_hash"] = fr
        for col in w["columns"]:
            for p in col["perks"]:
                delta = PERK_STAT_DELTAS.get(p["plug_hash"])
                if delta:
                    p["stats"] = delta
    return {
        "manifest": {"version": "SEED-SAMPLE-v3", "locale": "ko"},
        "weapons": WEAPONS,
        "stat_defs": STAT_DEFS,
        "roll_stats": roll_stats,
    }


if __name__ == "__main__":
    data = build()
    out_path = os.path.join(os.path.dirname(__file__), "seed_data.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"seed_data.json 생성 완료: {len(data['weapons'])} weapons, "
          f"{len(data['roll_stats'])} roll_stats -> {out_path}")
