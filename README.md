# 나랏님 시선

## 프로젝트 정보
- 충북대학교 소프트웨어학부 2025학년도 1학기 오픈소스소프트웨어기초프로젝트
- 개발팀: 2024042051 성우석, 2024042081 손상준, 2023041047 우유정

## 개요
국회 회의록을 수집·분석하여 감성 및 주요 이슈를 시각화하는 플랫폼입니다. Python(Django, Celery, Streamlit) 기반으로 백엔드와 프론트엔드를 통합 관리합니다.

## 기술 스택
- **백엔드**: Python, Django, Django REST Framework, Celery, Redis, PostgreSQL
- **프론트엔드**: Python, Streamlit
- **AI/분석**: Google Gemini API, pdfplumber, BeautifulSoup, lxml

---

## 설치 및 실행 가이드 (Step-by-Step)

### 1. 저장소 클론 및 디렉토리 이동
```bash
git clone https://github.com/MercuriusDream/NaratNimSiseon.git
cd NaratNimSiseon
```

### 2. 가상환경 생성 및 활성화
```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate
```

### 3. 필수 패키지 설치
```bash
pip install -r requirements.txt
```

### 4. 환경 변수(.env) 설정
프로젝트 루트에 `.env` 파일을 생성하고 아래 예시를 참고해 환경변수를 입력하세요.

```
DJANGO_SECRET_KEY=your-django-secret-key
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
PGDATABASE=assembly_sentiment
PGUSER=postgres
PGPASSWORD=yourpassword
PGHOST=localhost
PGPORT=5432
REDIS_URL=redis://localhost:6379/0
ASSEMBLY_API_KEY=your-assembly-api-key
GEMINI_API_KEY=your-google-gemini-api-key
```

### 5. 데이터베이스 준비 및 마이그레이션
```bash
# PostgreSQL에서 DB 생성 (이미 생성되어 있다면 생략)
# psql -U postgres
# CREATE DATABASE assembly_sentiment;

# 마이그레이션
cd backend
python manage.py migrate
```

### 6. 정적 파일 수집
```bash
python manage.py collectstatic --noinput
```

### 7. Redis 서버 실행
- **Windows**: [Redis 공식 사이트](https://github.com/microsoftarchive/redis/releases)에서 Windows용 Redis 다운로드 후 실행
- **macOS/Linux**: 
```bash
redis-server
```

### 8. 데이터 수집 (국회 API & Gemini AI)
```bash
# 관리 명령어로 데이터 수집 시작
python manage.py start_collection
```

### 9. 서비스 개별 실행 (수동)
#### Django 서버
```bash
python manage.py runserver
```
#### Celery 워커
```bash
celery -A backend worker -l info
```
#### Celery Beat (스케줄러)
```bash
celery -A backend beat -l info
```
#### Streamlit 프론트엔드
```bash
cd ../frontend
streamlit run app.py
```

### 10. 전체 서비스 자동 실행 (권장)
프로젝트 루트에서 아래 스크립트로 모든 서비스를 한 번에 실행할 수 있습니다.
```bash
python start_services.py
```
- Django: http://localhost:8000
- Streamlit: http://localhost:8501

---

## 주요 환경 변수 설명
- `DJANGO_SECRET_KEY`: Django 비밀키
- `PG*`: PostgreSQL 접속 정보
- `REDIS_URL`: Redis 브로커 주소
- `ASSEMBLY_API_KEY`: 국회 OPEN API 키
- `GEMINI_API_KEY`: Google Gemini API 키

---

## 문제 해결 & FAQ
- **ModuleNotFoundError**: `pip install -r requirements.txt`로 패키지 재설치
- **DB 연결 오류**: `.env`의 DB 정보 확인, PostgreSQL 실행 여부 확인
- **Redis 오류**: Redis 서버가 실행 중인지 확인
- **정적 파일/템플릿 오류**: `collectstatic` 실행 및 `backend/templates/index.html` 존재 확인
- **포트 충돌**: 기존 프로세스 종료 후 재실행 (autorun 스크립트가 자동으로 처리)

---

## 기타
- Streamlit 프론트엔드가 아닌 React를 사용할 경우, `frontend/build` 디렉토리 생성 및 빌드 필요
- 추가 문의: 팀원에게 연락