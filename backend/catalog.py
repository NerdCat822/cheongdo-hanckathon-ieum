"""고정된 가상 구성원과 확인일이 있는 공식 홈페이지 링크."""

PROFILE = {
    "alias": "가상 돌봄 공간 · 시연 전용 (실제 정보 입력 금지)",
    "region": "가상 청도군",
}

MEMBERS = [
    {"id": "member-1", "name": "가상 가족 1"},
    {"id": "member-2", "name": "가상 가족 2"},
    {"id": "member-3", "name": "가상 가족 3"},
]

SOURCES = [
    {
        "id": "benefit",
        "title": "복지 안내 홈페이지 · 가상 예시",
        "provider": "보건복지부",
        "url": "https://www.bokjiro.go.kr/ssis-tbu/index.do",
        "checked_at": "2026-11-05",
        "summary": "시연용 홈페이지 링크이며 실시간 제도 정보가 아닙니다. 자격과 세부 내용은 공식 기관에 확인하세요.",
    },
    {
        "id": "vaccination_checkup",
        "title": "예방접종 공공데이터 안내 · 가상 예시",
        "provider": "질병관리청 / 공공데이터포털",
        "url": "https://www.data.go.kr/data/15084296/openapi.do",
        "checked_at": "2026-11-05",
        "summary": "시연용 공개 데이터 안내 링크이며 실시간 접종 정보나 대상 판정이 아닙니다. 세부 내용은 공식 기관에 확인하세요.",
    },
    {
        "id": "regular_visit",
        "title": "정부 안내 홈페이지 · 가상 예시",
        "provider": "행정안전부",
        "url": "https://www.gov.kr/",
        "checked_at": "2026-11-05",
        "summary": "시연용 일반 홈페이지 링크입니다. 방문·안부 업무의 근거나 실시간 정보가 아닙니다.",
    },
]

MEMBER_IDS = frozenset(member["id"] for member in MEMBERS)
SOURCE_IDS = frozenset(source["id"] for source in SOURCES)
