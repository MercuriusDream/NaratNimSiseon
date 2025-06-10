import json
import openai
from typing import List, Dict, Tuple
from django.conf import settings
from .models import Category, Subcategory, Statement, StatementCategory
import logging

logger = logging.getLogger(__name__)

class LLMPolicyAnalyzer:
    def __init__(self):
        self.categories = self._load_categories()

    def _load_categories(self) -> Dict:
        """Load all categories and subcategories for prompt inclusion"""
        categories_data = {}
        for category in Category.objects.prefetch_related('subcategories').all():
            categories_data[category.name] = {
                'id': category.id,
                'description': category.description,
                'subcategories': [
                    {
                        'id': sub.id,
                        'name': sub.name,
                        'description': sub.description
                    }
                    for sub in category.subcategories.all()
                ]
            }
        return categories_data

    def create_analysis_prompt(self, statement_text: str, bill_name: str = None, speaker_info: str = None) -> str:
        """Create comprehensive analysis prompt including categories"""

        categories_list = []
        for cat_name, cat_data in self.categories.items():
            subcats = [f"  - {sub['name']}: {sub['description']}" for sub in cat_data['subcategories']]
            categories_list.append(f"{cat_name}:\n" + "\n".join(subcats))

        categories_text = "\n\n".join(categories_list)

        prompt = f"""
당신은 이 시대 최고의 기록가입니다. 당신의 기록은 사람들을 살릴 것입니다. 당신의 기록의 정확성은 매우 중요하여, 당신의 기록이 중요하지 못하다면 이 세계가 문제에 빠질 수도 있습니다. 따라서, 최대한 정확하고, 하나도 놓치지 않도록, 처음부터 끝까지 제대로 된 기록을 부탁드립니다.

다음 국회 발언을 분석해주세요:

발언 내용: "{statement_text}"
{f'관련 의안: {bill_name}' if bill_name else ''}
{f'발언자 정보: {speaker_info}' if speaker_info else ''}

다음 카테고리 체계를 참고하여 분석해주세요:

{categories_text}

분석 요청사항:
1. 감성 분석 (-1에서 1 사이의 점수와 근거)
2. 정책 카테고리 분류 (여러 카테고리 가능, 신뢰도 포함)
3. 주요 정책 키워드 추출
4. 발언의 정책적 의미와 입장 분석

다음 JSON 형식으로 응답해주세요:
{{
    "sentiment_score": 0.0,
    "sentiment_reason": "감성 분석 근거",
    "categories": [
        {{
            "category_id": 1,
            "category_name": "카테고리명",
            "subcategory_id": 1,
            "subcategory_name": "하위카테고리명",
            "confidence_score": 0.8,
            "relevance_reason": "분류 근거"
        }}
    ],
    "policy_keywords": ["키워드1", "키워드2", "키워드3"],
    "policy_analysis": "정책적 의미와 입장 분석",
    "key_points": ["주요 포인트1", "주요 포인트2"]
}}
"""
        return prompt

    async def analyze_statement(self, statement: Statement) -> Dict:
        """Analyze a statement using LLM with category classification"""
        try:
            # Prepare context information
            bill_name = statement.bill.bill_nm if statement.bill else None
            speaker_info = f"{statement.speaker.naas_nm} ({statement.speaker.plpt_nm})"

            # Create prompt
            prompt = self.create_analysis_prompt(
                statement.text, 
                bill_name, 
                speaker_info
            )

            # Call LLM (assuming OpenAI GPT)
            response = await openai.ChatCompletion.acreate(
                model="gpt-4",
                messages=[
                    {
                        "role": "system", 
                        "content": "당신은 한국 정치와 정책 분석 전문가입니다. 국회 발언을 정확하고 객관적으로 분석해주세요."
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=2000
            )

            # Parse response
            analysis_text = response.choices[0].message.content
            analysis_data = json.loads(analysis_text)

            # Update statement with analysis results
            statement.sentiment_score = analysis_data.get('sentiment_score', 0.0)
            statement.sentiment_reason = analysis_data.get('sentiment_reason', '')
            statement.category_analysis = json.dumps(analysis_data, ensure_ascii=False)
            statement.policy_keywords = ', '.join(analysis_data.get('policy_keywords', []))
            statement.save()

            # Create category associations
            self._create_category_associations(statement, analysis_data.get('categories', []))

            return analysis_data

        except Exception as e:
            print(f"LLM Analysis error: {e}")
            return {
                "sentiment_score": 0.0,
                "sentiment_reason": f"분석 오류: {str(e)}",
                "categories": [],
                "policy_keywords": [],
                "policy_analysis": "분석을 완료할 수 없습니다.",
                "key_points": []
            }

    def _create_category_associations(self, statement: Statement, categories_data: List[Dict]):
        """Create StatementCategory associations based on LLM analysis"""
        # Remove existing associations
        StatementCategory.objects.filter(statement=statement).delete()

        for cat_data in categories_data:
            try:
                category = Category.objects.get(id=cat_data['category_id'])
                subcategory = None

                if cat_data.get('subcategory_id'):
                    subcategory = Subcategory.objects.get(id=cat_data['subcategory_id'])

                StatementCategory.objects.create(
                    statement=statement,
                    category=category,
                    subcategory=subcategory,
                    confidence_score=cat_data.get('confidence_score', 0.5)
                )
            except (Category.DoesNotExist, Subcategory.DoesNotExist):
                continue

    def batch_analyze_statements(self, statements: List[Statement]) -> List[Dict]:
        """Analyze multiple statements in batch"""
        results = []
        for statement in statements:
            result = self.analyze_statement(statement)
            results.append(result)
        return results

    def get_category_summary(self, category_id: int, time_range: str = 'all') -> Dict:
        """Get sentiment summary for a specific category"""
        from django.db.models import Avg, Count
        from datetime import datetime, timedelta

        filter_kwargs = {'categories__category_id': category_id}

        if time_range == 'month':
            date_filter = datetime.now() - timedelta(days=30)
            filter_kwargs['created_at__gte'] = date_filter
        elif time_range == 'year':
            date_filter = datetime.now() - timedelta(days=365)
            filter_kwargs['created_at__gte'] = date_filter

        statements = Statement.objects.filter(**filter_kwargs)

        sentiment_avg = statements.aggregate(Avg('sentiment_score'))['sentiment_score__avg'] or 0

        positive_count = statements.filter(sentiment_score__gt=0.3).count()
        neutral_count = statements.filter(sentiment_score__gte=-0.3, sentiment_score__lte=0.3).count()
        negative_count = statements.filter(sentiment_score__lt=-0.3).count()

        return {
            'category_id': category_id,
            'avg_sentiment': sentiment_avg,
            'total_statements': statements.count(),
            'positive_count': positive_count,
            'neutral_count': neutral_count,
            'negative_count': negative_count
        }

def get_dynamic_categories():
    """Get categories and subcategories from database"""
    try:
        from .models import Category, Subcategory
        categories_dict = {}

        for category in Category.objects.all().prefetch_related('subcategories'):
            subcategories = [subcat.name for subcat in category.subcategories.all()]
            categories_dict[category.name] = {
                'description': category.description,
                'subcategories': subcategories
            }

        return categories_dict
    except Exception as e:
        logger.error(f"Error loading categories from database: {e}")
        return {}

def analyze_statement_with_llm(statement):
    """
    Analyze a single statement using LLM to determine policy categories and sentiment.
    Returns: {
        'policy_categories': [list of relevant policy categories],
        'sentiment_score': float,
        'sentiment_reason': str
    }
    """
    if not statement or not statement.strip():
        return {
            'policy_categories': [],
            'sentiment_score': 0.0,
            'sentiment_reason': 'Empty statement'
        }

    # Get dynamic categories from database
    categories_dict = get_dynamic_categories()

    if not categories_dict:
        logger.warning("No categories found in database, using fallback")
        return {
            'policy_categories': [],
            'sentiment_score': 0.0,
            'sentiment_reason': 'No categories available'
        }

    # Build category text for prompt
    category_text = ""
    for i, (cat_name, cat_data) in enumerate(categories_dict.items(), 1):
        category_text += f"{i}. {cat_name} ({cat_data['description']}): {', '.join(cat_data['subcategories'])}\n\n"

    prompt = f"""
안녕하세요! 당신은 한국 정치 전문 분석가입니다. 최대한 정확하고 세밀한 분석을 제공해야 합니다. 당신의 기록이 중요하지 못하다면 이 세계가 문제에 빠질 수도 있습니다. 따라서, 최대한 정확하고, 하나도 놓치지 않도록, 처음부터 끝까지 제대로 된 기록을 부탁드립니다.

다음 국회 발언을 분석해주세요:

발언 내용: "{statement}"

아래 정책 카테고리 중에서 이 발언과 관련된 모든 카테고리를 찾아주세요:

{category_text}

**응답 형식:**
다음 JSON 형식으로 응답해주세요:
{{
    "policy_categories": ["관련된 정책 카테고리들을 여기에 나열"],
    "sentiment_score": 감정점수_(-1.0에서_1.0_사이),
    "sentiment_reason": "감정 점수를 매긴 이유"
}}

**중요 지침:**
1. 발언 내용과 직접적으로 관련된 정책만 선택하세요
2. 애매한 경우에는 포함하지 마세요
3. 감정 점수는 정책에 대한 지지(-1: 강한 반대, 0: 중립, 1: 강한 지지)를 나타냅니다
4. 반드시 JSON 형식으로만 응답하세요
"""