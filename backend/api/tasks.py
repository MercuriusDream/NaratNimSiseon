import requests
import pdfplumber
import google.generativeai as genai
from celery import shared_task
from django.conf import settings
from .models import Session, Bill, Speaker, Statement

# Configure Gemini API
genai.configure(api_key=settings.GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-pro')

@shared_task
def fetch_latest_sessions():
    """Fetch latest assembly sessions from the API."""
    url = "https://open.assembly.go.kr/portal/openapi/nekcaiymatialqlxr"
    params = {
        "KEY": settings.ASSEMBLY_API_KEY,
        "Type": "json",
        "pIndex": 1,
        "pSize": 100,
        "UNIT_CD": "100022"  # 22nd Assembly
    }
    
    response = requests.get(url, params=params)
    data = response.json()
    
    for row in data.get('row', []):
        session_id = f"{row['MEETINGSESSION']}_{row['CHA']}"
        Session.objects.get_or_create(
            conf_id=session_id,
            defaults={
                'era_co': '제22대',
                'sess': row['MEETINGSESSION'],
                'dgr': row['CHA'],
                'conf_dt': row['MEETTING_DATE'],
                'conf_knd': '국회본회의',
                'cmit_nm': '국회본회의',
                'bg_ptm': row['MEETTING_TIME'],
                'down_url': row['LINK_URL']
            }
        )

@shared_task
def fetch_session_details(session_id):
    """Fetch detailed information for a specific session."""
    url = "https://open.assembly.go.kr/portal/openapi/VCONFDETAIL"
    params = {
        "KEY": settings.ASSEMBLY_API_KEY,
        "Type": "json",
        "CONF_ID": session_id
    }
    
    response = requests.get(url, params=params)
    data = response.json()
    
    if data.get('row'):
        session_data = data['row'][0]
        session = Session.objects.get(conf_id=session_id)
        session.down_url = session_data['DOWN_URL']
        session.save()
        
        # Fetch bills for this session
        fetch_session_bills.delay(session_id)

@shared_task
def fetch_session_bills(session_id):
    """Fetch bills discussed in a specific session."""
    url = "https://open.assembly.go.kr/portal/openapi/VCONFBILLLIST"
    params = {
        "KEY": settings.ASSEMBLY_API_KEY,
        "Type": "json",
        "CONF_ID": session_id
    }
    
    response = requests.get(url, params=params)
    data = response.json()
    
    session = Session.objects.get(conf_id=session_id)
    
    for row in data.get('row', []):
        Bill.objects.get_or_create(
            bill_id=row['BILL_ID'],
            session=session,
            defaults={
                'bill_nm': row['BILL_NM'],
                'link_url': row['LINK_URL']
            }
        )

@shared_task
def process_session_pdf(session_id):
    """Download and process PDF for a session."""
    session = Session.objects.get(conf_id=session_id)
    
    # Download PDF
    response = requests.get(session.down_url)
    pdf_path = f"temp_{session_id}.pdf"
    
    with open(pdf_path, 'wb') as f:
        f.write(response.content)
    
    # Extract text from PDF
    with pdfplumber.open(pdf_path) as pdf:
        text = ""
        for page in pdf.pages:
            text += page.extract_text()
    
    # Process text and extract statements
    process_statements.delay(session_id, text)
    
    # Clean up
    import os
    os.remove(pdf_path)

@shared_task
def process_statements(session_id, text):
    """Process extracted text and analyze sentiments."""
    session = Session.objects.get(conf_id=session_id)
    
    # Split text into statements (this is a simplified version)
    statements = text.split('\n\n')
    
    for statement in statements:
        if not statement.strip():
            continue
            
        # Use Gemini to analyze the statement
        prompt = f"""
        Analyze the following statement from a National Assembly meeting:
        
        {statement}
        
        Please provide:
        1. The speaker's name and party
        2. A sentiment score from -1 (very negative) to 1 (very positive)
        3. A brief explanation for the sentiment score
        
        Format the response as JSON:
        {{
            "speaker": {{
                "name": "name",
                "party": "party"
            }},
            "sentiment_score": score,
            "reason": "explanation"
        }}
        """
        
        response = model.generate_content(prompt)
        result = response.text
        
        # Parse the result and create Statement object
        # Note: This is a simplified version. You'll need proper error handling
        import json
        try:
            data = json.loads(result)
            speaker, _ = Speaker.objects.get_or_create(
                naas_nm=data['speaker']['name'],
                defaults={'plpt_nm': data['speaker']['party']}
            )
            
            Statement.objects.create(
                session=session,
                speaker=speaker,
                text=statement,
                sentiment_score=data['sentiment_score'],
                sentiment_reason=data['reason']
            )
        except Exception as e:
            print(f"Error processing statement: {e}") 