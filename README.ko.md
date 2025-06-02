# 국회 감성 분석 플랫폼 (National Assembly Sentiment Analysis Platform)

국회 회의록을 분석하여 의원들의 발언에 대한 감성 분석을 제공하는 웹 플랫폼입니다.

## 주요 기능

- 국회 회의록 자동 수집 및 분석
- 의원별 발언 감성 분석
- 정당별 감성 분석 통계
- 의안별 발언 분석
- 실시간 대시보드

## 기술 스택

### 백엔드
- Django
- Django REST Framework
- Celery (작업 큐)
- Google Gemini AI (감성 분석)
- PostgreSQL

### 프론트엔드
- React
- Tailwind CSS
- Recharts (데이터 시각화)
- Axios

## 설치 방법

### 필수 요구사항
- Python 3.8 이상
- Node.js 16 이상
- PostgreSQL
- Redis (Celery용)

### 백엔드 설정
```bash
# 가상환경 생성 및 활성화
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# 의존성 설치
pip install -r requirements.txt

# 환경 변수 설정
cp .env.example .env
# .env 파일을 편집하여 필요한 설정 입력

# 데이터베이스 마이그레이션
python manage.py migrate

# 개발 서버 실행
python manage.py runserver
```

### 프론트엔드 설정
```bash
cd frontend

# 의존성 설치
npm install

# 개발 서버 실행
npm start
```

### Celery 설정
```bash
# Celery 워커 실행
celery -A backend worker -l info

# Celery Beat 스케줄러 실행
celery -A backend beat -l info
```

## 데이터 수집

- 매일 자정에 자동으로 최신 국회 회의록을 수집합니다.
- 수동으로 데이터를 강제 수집하려면 다음 명령어를 실행하세요:
```bash
python manage.py collect_data --force
```

## API 문서

API 문서는 다음 URL에서 확인할 수 있습니다:
```
http://localhost:8000/api/docs/
```

## 라이선스

이 프로젝트는 MIT 라이선스 하에 배포됩니다. 자세한 내용은 [LICENSE](LICENSE) 파일을 참조하세요.

## 기여 방법

1. 이 저장소를 포크합니다.
2. 새로운 기능 브랜치를 생성합니다 (`git checkout -b feature/amazing-feature`).
3. 변경사항을 커밋합니다 (`git commit -m 'Add some amazing feature'`).
4. 브랜치에 푸시합니다 (`git push origin feature/amazing-feature`).
5. Pull Request를 생성합니다.

## 연락처

프로젝트 관리자: [이메일 주소]

## 감사의 말

- 국회 OPEN API
- Google Gemini AI
- 모든 기여자들 