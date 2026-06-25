"""해시/코드 -> 한국어 라벨 매핑.

모든 명칭은 Bungie 매니페스트 ko 로케일의 인게임 공식 표기를 따른다
(2026-06-23 매니페스트 244122.* 기준으로 검증). 임의 번역/구어체 사용 금지.
"""

# itemSubType -> 인게임 itemTypeDisplayName(ko)
WEAPON_SUBTYPE_KO = {
    6: "자동 소총", 7: "산탄총", 8: "기관총", 9: "핸드 캐논", 10: "로켓 발사기",
    11: "융합 소총", 12: "저격총", 13: "파동 소총", 14: "정찰 소총", 17: "보조 무기",
    18: "검", 22: "선형 융합 소총", 23: "유탄 발사기", 24: "기관단총", 25: "추적 소총",
    31: "전투 활", 33: "월도",
}

COLUMN_KIND_KO = {
    "barrel": "총열", "magazine": "탄창", "trait": "특성",
    "origin": "기원 특성", "intrinsic": "고유 특성",
}

# DestinyDamageTypeDefinition(ko) 공식 명칭
DAMAGE_KO = {
    "Kinetic": "물리", "Arc": "전기", "Solar": "태양", "Void": "공허",
    "Stasis": "시공", "Strand": "초월", "Prismatic": "프리즘",
}

# inventory.tierTypeName(ko): 5=전설, 6=경이(구 "이국적")
TIER_KO = {5: "전설", 6: "경이"}

# 무기 슬롯(장착 칸). DestinyItemCategoryDefinition(ko) 기준.
SLOT_KO = {"Kinetic": "물리 무기", "Energy": "에너지 무기", "Power": "동력 무기"}

# 탄약 종류 (equippingBlock.ammoType)
AMMO_KO = {1: "주무기", 2: "특수", 3: "강력"}


# ---------- 텍스트 쿼리(is:) 토큰 역매핑 (EN + KO, 소문자·공백제거 키) ----------
def _norm(s: str) -> str:
    return (s or "").lower().replace(" ", "").replace("_", "")


# is:<token> → weapon_subtype
SUBTYPE_TOKENS = {
    "autorifle": 6, "자동소총": 6,
    "shotgun": 7, "산탄총": 7,
    "machinegun": 8, "기관총": 8,
    "handcannon": 9, "핸드캐논": 9, "핸드캐논": 9,
    "rocketlauncher": 10, "로켓발사기": 10, "로켓": 10,
    "fusionrifle": 11, "융합소총": 11,
    "sniperrifle": 12, "sniper": 12, "저격총": 12, "저격소총": 12,
    "pulserifle": 13, "pulse": 13, "파동소총": 13, "펄스소총": 13,
    "scoutrifle": 14, "scout": 14, "정찰소총": 14,
    "sidearm": 17, "보조무기": 17,
    "sword": 18, "검": 18,
    "linearfusionrifle": 22, "linearfusion": 22, "lfr": 22, "선형융합소총": 22,
    "grenadelauncher": 23, "gl": 23, "유탄발사기": 23,
    "submachinegun": 24, "smg": 24, "기관단총": 24,
    "tracerifle": 25, "trace": 25, "추적소총": 25,
    "bow": 31, "combatbow": 31, "전투활": 31, "활": 31,
    "glaive": 33, "월도": 33,
}

# is:<token> → default_damage_type
DAMAGE_TOKENS = {
    "kinetic": "Kinetic", "물리": "Kinetic",
    "arc": "Arc", "전기": "Arc",
    "solar": "Solar", "태양": "Solar",
    "void": "Void", "공허": "Void",
    "stasis": "Stasis", "시공": "Stasis",
    "strand": "Strand", "초월": "Strand",
    "prismatic": "Prismatic", "프리즘": "Prismatic",
}

# is:<token> → slot (장착 칸)
SLOT_TOKENS = {
    "kineticslot": "Kinetic", "물리무기": "Kinetic",
    "energy": "Energy", "에너지": "Energy", "에너지무기": "Energy",
    "power": "Power", "powerslot": "Power", "동력무기": "Power", "동력": "Power",
}

# is:<token> → tier
TIER_TOKENS = {
    "legendary": 5, "전설": 5,
    "exotic": 6, "경이": 6, "이국": 6, "이국적": 6,
}

# is:<token> → ammo_type
AMMO_TOKENS = {
    "primary": 1, "주무기": 1, "기본": 1,
    "special": 2, "특수": 2,
    "heavy": 3, "강력": 3, "대형": 3,
}


def weapon_type_label(subtype) -> str:
    return WEAPON_SUBTYPE_KO.get(subtype, "무기")


def column_label(kind: str, index: int) -> str:
    base = COLUMN_KIND_KO.get(kind, kind or "특성")
    # 특성 열이 둘이면 1/2 구분
    return base
