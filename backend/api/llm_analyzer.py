
import json
import openai
from typing import List, Dict, Tuple
from django.conf import settings
from .models import Category, Subcategory, Statement, StatementCategory

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
