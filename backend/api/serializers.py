from rest_framework import serializers
from .models import Session, Bill, Speaker, Statement
from django.utils import timezone

class SpeakerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Speaker
        fields = '__all__'

    def validate_naas_nm(self, value):
        if len(value) < 2:
            raise serializers.ValidationError("의원 이름은 2글자 이상이어야 합니다.")
        return value

    def validate_plpt_nm(self, value):
        if not value:
            raise serializers.ValidationError("소속 정당은 필수입니다.")
        return value

class BillSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bill
        fields = '__all__'

    def validate_proposal_date(self, value):
        if value > timezone.now():
            raise serializers.ValidationError("의안 제안 날짜는 현재 날짜보다 이후일 수 없습니다.")
        return value

    def validate(self, data):
        if data.get('proposal_date') and data.get('resolution_date'):
            if data['proposal_date'] > data['resolution_date']:
                raise serializers.ValidationError("의안 처리 날짜는 제안 날짜보다 이후여야 합니다.")
        return data

class StatementSerializer(serializers.ModelSerializer):
    speaker_name = serializers.CharField(source='speaker.naas_nm', read_only=True)
    party_name = serializers.CharField(source='speaker.plpt_nm', read_only=True)
    session_date = serializers.DateField(source='session.conf_dt', read_only=True)
    bill_name = serializers.CharField(source='bill.bill_nm', read_only=True)

    class Meta:
        model = Statement
        fields = '__all__'

    def validate_content(self, value):
        if len(value.strip()) < 10:
            raise serializers.ValidationError("발언 내용은 10자 이상이어야 합니다.")
        return value

    def validate_sentiment_score(self, value):
        if value < -1 or value > 1:
            raise serializers.ValidationError("감정 점수는 -1에서 1 사이여야 합니다.")
        return value

class SessionSerializer(serializers.ModelSerializer):
    bills = BillSerializer(many=True, read_only=True)
    statements = StatementSerializer(many=True, read_only=True)

    class Meta:
        model = Session
        fields = '__all__'

    def validate_conf_dt(self, value):
        if value > timezone.now():
            raise serializers.ValidationError("회의 날짜는 현재 날짜보다 이후일 수 없습니다.")
        return value

    def validate(self, data):
        if data.get('conf_dt') and data.get('conf_dt_end'):
            if data['conf_dt'] > data['conf_dt_end']:
                raise serializers.ValidationError("회의 종료 시간은 시작 시간보다 이후여야 합니다.")
        return data

class StatementCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Statement
        fields = ['session', 'bill', 'speaker', 'content', 'sentiment_score']

    def validate(self, data):
        # Check if session exists and is valid
        session = data.get('session')
        if not session:
            raise serializers.ValidationError("회의 정보는 필수입니다.")
        
        # Check if speaker exists and is valid
        speaker = data.get('speaker')
        if not speaker:
            raise serializers.ValidationError("발언자 정보는 필수입니다.")
        
        # Check if bill exists and is valid (optional)
        bill = data.get('bill')
        if bill and not Bill.objects.filter(id=bill.id).exists():
            raise serializers.ValidationError("유효하지 않은 의안입니다.")
        
        # Check if content is provided
        content = data.get('content')
        if not content or len(content.strip()) < 10:
            raise serializers.ValidationError("발언 내용은 10자 이상이어야 합니다.")
        
        # Validate sentiment score
        sentiment_score = data.get('sentiment_score')
        if sentiment_score is not None and (sentiment_score < -1 or sentiment_score > 1):
            raise serializers.ValidationError("감정 점수는 -1에서 1 사이여야 합니다.")
        
        return data 