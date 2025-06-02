# National Assembly Sentiment Analysis Platform

A full-stack platform for analyzing sentiments in Korean National Assembly meeting records.

## Features

- Periodic fetching of National Assembly meeting records
- PDF parsing and text extraction
- Sentiment analysis using Google's Gemini API
- Structured data storage
- Interactive web interface for visualization

## Tech Stack

- Backend: Django + Django REST Framework
- Frontend: React + TailwindCSS
- Database: PostgreSQL
- Task Queue: Celery + Redis
- PDF Processing: pdfplumber
- LLM: Google Gemini API

## Setup

1. Clone the repository
2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Set up environment variables in `.env`:
   ```
   ASSEMBLY_API_KEY=your_assembly_api_key
   GEMINI_API_KEY=your_gemini_api_key
   DATABASE_URL=postgresql://user:password@localhost:5432/dbname
   REDIS_URL=redis://localhost:6379/0
   ```
5. Run migrations:
   ```bash
   python manage.py migrate
   ```
6. Start the development server:
   ```bash
   python manage.py runserver
   ```

## Project Structure

```
├── backend/                 # Django backend
│   ├── api/                # REST API endpoints
│   ├── core/              # Core functionality
│   └── tasks/             # Celery tasks
├── frontend/              # React frontend
│   ├── src/
│   └── public/
└── 웹 페이지/             # Generated frontend pages
```

## API Documentation

The API documentation is available at `/api/docs/` when running the development server.

## License

MIT 