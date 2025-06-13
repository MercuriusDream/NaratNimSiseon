
# 🏛️ 나랏님 시선 (NaratNim Siseon)

> **국회 회의록 감성 분석 및 정치 동향 시각화 플랫폼**

---

## 📋 프로젝트 정보

- **대학**: 충북대학교 소프트웨어학부
- **과목**: 2025학년도 1학기 오픈소스소프트웨어기초프로젝트
- **개발팀**: 
  - 2024042051 성우석

---

## 🎯 개요

국회 회의록을 자동으로 수집·분석하여 정치인들의 감성과 주요 이슈를 시각화하는 웹 플랫폼입니다. 
시민들이 정치 동향을 쉽게 파악할 수 있도록 도와줍니다.

---

## 🛠️ 기술 스택

### Backend
- **Framework**: Django, Django REST Framework
- **Task Queue**: Celery + Redis
- **Database**: PostgreSQL
- **AI Analysis**: Google Gemini API

### Frontend  
- **Framework**: React.js
- **Styling**: Tailwind CSS
- **HTTP Client**: Axios

### Data Processing
- **PDF Parser**: pdfplumber
- **Web Scraping**: BeautifulSoup, lxml
- **API Integration**: 국회 OPEN API

---

## 🚀 빠른 시작 가이드

### 1️⃣ 저장소 클론
```bash
git clone https://github.com/MercuriusDream/NaratNimSiseon.git
cd NaratNimSiseon
```

### 2️⃣ 가상환경 설정
```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux  
source .venv/bin/activate
```

### 3️⃣ 패키지 설치
```bash
pip install -r requirements.txt
```

### 4️⃣ 환경변수 설정
프로젝트 루트에 `.env` 파일을 생성하고 다음 내용을 입력하세요:

```env
# Django 설정
DJANGO_SECRET_KEY=your-django-secret-key
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1

# 데이터베이스 설정
PGDATABASE=assembly_sentiment
PGUSER=postgres
PGPASSWORD=yourpassword
PGHOST=localhost
PGPORT=5432

# Redis 설정
REDIS_URL=redis://localhost:6379/0

# API 키
ASSEMBLY_API_KEY=your-assembly-api-key
GEMINI_API_KEY=your-google-gemini-api-key
```

### 5️⃣ 데이터베이스 설정
```bash
# PostgreSQL에서 데이터베이스 생성 (필요시)
# psql -U postgres
# CREATE DATABASE assembly_sentiment;

# Django 마이그레이션
cd backend
python manage.py migrate
python manage.py collectstatic --noinput
```

### 6️⃣ Redis 서버 실행 (선택사항)
```bash
# Windows: Redis 설치 후 실행
# macOS: brew install redis && redis-server
# Linux: sudo systemctl start redis

redis-server
```

**⚠️ 참고**: Replit과 같은 제한된 환경에서는 Redis가 실행되지 않을 수 있습니다. 이 경우 시스템이 자동으로 동기식 처리로 전환되어 데이터 수집이 정상 작동합니다.

---

## ▶️ 실행 방법

### 🎯 원클릭 실행 (권장)
```bash
python start_services.py
```

### 🔧 개별 서비스 실행
```bash
# 1. Django 서버
cd backend
python manage.py runserver 0.0.0.0:3000

# 2. Celery 워커 (Redis 사용 가능 시)
celery -A backend worker -l info

# 3. Celery Beat 스케줄러 (Redis 사용 가능 시)
celery -A backend beat -l info

# 4. React 프론트엔드 (새 터미널) - 개발 모드
cd frontend
npm install
npm start
```

**💡 Redis 없이 실행하기**: Redis/Celery가 사용 불가능한 환경에서는 Django만 실행해도 데이터 수집이 동기식으로 정상 작동합니다.

### 📊 데이터 수집 시작
```bash
cd backend
python manage.py start_collection
```

### 📋 정책 카테고리 로드
정책 분석을 위한 카테고리 데이터를 CSV 파일에서 로드:
```bash
cd backend
python manage.py load_policy_categories --csv-file=../Additional_Files/code.txt
```

**옵션**:
- `--csv-file`: CSV 파일 경로 (필수)
- `--clear-existing`: 기존 카테고리 데이터 삭제 후 로드

**데이터 수집 모드**:
- **Redis 사용 가능**: 비동기 백그라운드 처리로 빠른 수집
- **Redis 불가능**: 동기식 처리로 안정적인 수집 (Replit 환경에서 권장)

### 🔧 API 파싱 문제 해결
API 응답 구조가 변경되어 파싱 오류가 발생하는 경우:

```bash
# 강제로 최신 데이터 수집 (기존 데이터 업데이트 포함)
cd backend
python manage.py force_collection

# 데이터 상태 확인
python manage.py check_data_status

# 실시간 모니터링 (파싱 오류 확인용)
python manage.py monitor_collection
```

---

## 🌐 접속 주소

### 로컬 개발환경
- **Django Backend**: http://localhost:3000
- **React Frontend**: http://localhost:3000 (프로덕션 빌드)
- **Django Admin**: http://localhost:3000/admin
- **API Documentation**: http://localhost:3000/api

### Replit 환경
- **웹 애플리케이션**: Replit 제공 URL (자동 할당)
- **Django Admin**: `[Replit-URL]/admin`
- **API Documentation**: `[Replit-URL]/api`

**💡 참고**: Replit에서는 포트 3000이 외부 접속용으로 자동 설정됩니다.

---

## 🔧 문제해결

### 일반적인 오류

| 문제 | 해결방법 |
|------|----------|
| `ModuleNotFoundError` | `pip install -r requirements.txt` 재실행 |
| 데이터베이스 연결 오류 | `.env` 파일의 DB 설정 확인, PostgreSQL 서버 상태 점검 |
| Redis 연결 오류 | Redis 서버 실행 상태 확인 (없어도 동기식으로 작동) |
| Redis TLS 할당 오류 (Replit) | 시스템이 자동으로 동기식 처리로 전환 |
| 정적 파일 오류 | `python manage.py collectstatic --noinput` 실행 |
| 포트 충돌 | 기존 프로세스 종료 후 재실행 |

### 🔧 Replit 환경 특화 문제해결

**Redis TLS 할당 오류**: Replit/Nix 환경에서 Redis가 jemalloc 라이브러리 문제로 실행되지 않을 수 있습니다. 이는 정상적인 현상이며, 시스템이 자동으로 동기식 처리로 전환하여 모든 기능이 정상 작동합니다.

**성능 차이**: 
- Redis 사용 시: 백그라운드 비동기 처리 (더 빠름)
- Redis 없이: 동기식 처리 (약간 느리지만 정상 작동)

### 로그 확인
```bash
# Django 로그
tail -f backend/logs/django.log

# Celery 로그  
tail -f backend/logs/celery.log
```

---

## 📁 프로젝트 구조

```
NaratNimSiseon/
├── backend/                 # Django 백엔드
│   ├── api/                # API 앱
│   ├── backend/            # Django 설정
│   └── templates/          # HTML 템플릿
├── frontend/               # React 프론트엔드
│   ├── src/
│   │   ├── components/     # 재사용 컴포넌트
│   │   └── pages/          # 페이지 컴포넌트
│   └── public/
├── .env                    # 환경변수 (생성 필요)
├── requirements.txt        # Python 패키지
└── start_services.py       # 자동 실행 스크립트
```

---

## 🤝 기여하기

1. Fork this repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

## 📞 문의사항

프로젝트 관련 문의사항이 있으시면 개발팀에게 연락해주세요.

# 이거 나 다 혼자 했어요. 제발 팀원들 다 버스탄거니까 어케 나쁘게 보지 좀 말아주세요...ㅠㅜㅜㅜㅜㅠㅜㅠㅜㅠㅜㅜㅠㅜㅠㅜㅠ

---

## 📄 라이선스

이 프로젝트는 MIT 라이선스 하에 배포됩니다.
