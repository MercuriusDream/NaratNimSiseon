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

## API 설정

### 국회 OPEN API
1. [국회 OPEN API](https://open.assembly.go.kr/portal/mainPage.do)에 접속
2. 회원가입 및 로그인
3. API 키 발급 신청
4. 발급받은 API 키를 `.env` 파일에 추가:
```
ASSEMBLY_API_KEY=your_api_key_here
```

### Google Gemini AI
1. [Google AI Studio](https://makersuite.google.com/app/apikey)에 접속
2. Google 계정으로 로그인
3. API 키 생성
4. 발급받은 API 키를 `.env` 파일에 추가:
```
GEMINI_API_KEY=your_api_key_here
```

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

## 데이터 수집 및 처리

### 자동 수집
- 매일 자정에 자동으로 최신 국회 회의록을 수집합니다.
- 수집된 데이터는 자동으로 처리되어 데이터베이스에 저장됩니다.

### 수동 수집
수동으로 데이터를 강제 수집하려면 다음 명령어를 실행하세요:
```bash
# 모든 데이터 강제 수집
python manage.py collect_data --force

# 특정 기간 데이터 수집
python manage.py collect_data --start-date 2024-01-01 --end-date 2024-01-31
```

### 데이터 처리 과정
1. 국회 OPEN API를 통해 회의록 데이터 수집
2. PDF 파일 다운로드 및 텍스트 추출
3. Google Gemini AI를 사용한 감성 분석
4. 분석 결과 데이터베이스 저장

## API 문서

API 문서는 다음 URL에서 확인할 수 있습니다:
```
http://localhost:8000/api/docs/
```

## 환경 변수 설정

`.env` 파일에 다음 환경 변수들을 설정해야 합니다:

```env
# Django 설정
DEBUG=True
SECRET_KEY=your_secret_key
ALLOWED_HOSTS=localhost,127.0.0.1

# 데이터베이스 설정
DB_NAME=assembly_db
DB_USER=your_db_user
DB_PASSWORD=your_db_password
DB_HOST=localhost
DB_PORT=5432

# API 키
ASSEMBLY_API_KEY=your_assembly_api_key
GEMINI_API_KEY=your_gemini_api_key

# Celery 설정
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
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