from django.core.management.base import BaseCommand
from api.models import Category, Subcategory


class Command(BaseCommand):
    help = 'Populate categories and subcategories from JSON data'

    def handle(self, *args, **options):
        # The category data from your JSON
        categories_data = [
            {
                "category": "헌법 및 정치제도",
                "subcategories": [
                    "헌법 개정",
                    "권력 분립 및 정부 형태",
                    "국가 상징과 국기",
                    "비상사태 및 계엄",
                    "기본권 및 인권 제도",
                    "국적 및 시민권"
                ]
            },
            {
                "category": "국회 및 의회제도",
                "subcategories": [
                    "국회 운영",
                    "의회 절차 및 규칙",
                    "국회의원 윤리 및 특권",
                    "의안 제출 및 심의 제도",
                    "국회 예산 및 조직",
                    "국회 사무처 운영"
                ]
            },
            {
                "category": "선거 및 정당",
                "subcategories": [
                    "선거 제도 일반",
                    "선거구 획정",
                    "정당 등록 및 해산",
                    "정당 운영과 회계",
                    "정치자금 및 후원금",
                    "선거운동 및 공정성"
                ]
            },
            {
                "category": "행정 및 지방자치",
                "subcategories": [
                    "중앙 행정조직",
                    "공무원 제도",
                    "행정절차",
                    "지방자치단체",
                    "지방재정",
                    "지방선거"
                ]
            },
            {
                "category": "경제 및 재정",
                "subcategories": [
                    "예산 및 결산",
                    "조세 제도",
                    "금융 정책",
                    "통화 정책",
                    "산업 정책",
                    "무역 정책"
                ]
            },
            {
                "category": "사회복지 및 보건",
                "subcategories": [
                    "국민연금",
                    "건강보험",
                    "사회보장",
                    "공중보건",
                    "의료 제도",
                    "장애인 복지"
                ]
            },
            {
                "category": "교육 및 문화",
                "subcategories": [
                    "초중등교육",
                    "고등교육",
                    "평생교육",
                    "문화예술",
                    "체육진흥",
                    "언론 정책"
                ]
            },
            {
                "category": "국방 및 외교",
                "subcategories": [
                    "국방 정책",
                    "군사 조직",
                    "외교 정책",
                    "통일 정책",
                    "국제협력",
                    "안보 정책"
                ]
            },
            {
                "category": "법무 및 사법",
                "subcategories": [
                    "형사법",
                    "민사법",
                    "사법제도",
                    "검찰 제도",
                    "변호사 제도",
                    "인권 보호"
                ]
            },
            {
                "category": "환경 및 에너지",
                "subcategories": [
                    "환경보호",
                    "대기오염",
                    "수질보전",
                    "에너지 정책",
                    "신재생에너지",
                    "기후변화"
                ]
            },
            {
                "category": "교통 및 건설",
                "subcategories": [
                    "도로교통",
                    "철도 정책",
                    "항공 정책",
                    "해운 정책",
                    "건설 정책",
                    "도시계획"
                ]
            },
            {
                "category": "농림수산업",
                "subcategories": [
                    "농업 정책",
                    "임업 정책",
                    "수산업 정책",
                    "농촌 개발",
                    "식품안전",
                    "농산물 유통"
                ]
            },
            {
                "category": "과학기술 및 정보통신",
                "subcategories": [
                    "과학기술 진흥",
                    "정보통신 정책",
                    "인터넷 규제",
                    "개인정보보호",
                    "디지털 혁신",
                    "AI 및 빅데이터"
                ]
            },
            {
                "category": "노동 및 고용",
                "subcategories": [
                    "노동법",
                    "고용 정책",
                    "산업안전",
                    "최저임금",
                    "노사관계",
                    "직업훈련"
                ]
            },
            {
                "category": "여성 및 가족",
                "subcategories": [
                    "여성 권익",
                    "성평등",
                    "가족 정책",
                    "육아 지원",
                    "청소년 정책",
                    "양성평등"
                ]
            }
        ]

        created_categories = 0
        created_subcategories = 0

        for cat_data in categories_data:
            # Create or get the category
            category, cat_created = Category.objects.get_or_create(
                name=cat_data['category'],
                defaults={'description': f"{cat_data['category']} 관련 정책 및 법안"}
            )

            if cat_created:
                created_categories += 1
                self.stdout.write(
                    self.style.SUCCESS(f'Created category: {category.name}')
                )

            # Create subcategories
            for subcat_name in cat_data['subcategories']:
                subcategory, subcat_created = Subcategory.objects.get_or_create(
                    category=category,
                    name=subcat_name,
                    defaults={'description': f"{subcat_name} 관련 세부 사항"}
                )

                if subcat_created:
                    created_subcategories += 1
                    self.stdout.write(
                        self.style.SUCCESS(f'  Created subcategory: {subcategory.name}')
                    )

        self.stdout.write(
            self.style.SUCCESS(
                f'\nCompleted! Created {created_categories} categories and {created_subcategories} subcategories.'
            )
        )