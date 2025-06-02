from rest_framework import serializers
from .models import Session, Bill, Speaker, Statement

class SpeakerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Speaker
        fields = '__all__'

class BillSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bill
        fields = '__all__'

class StatementSerializer(serializers.ModelSerializer):
    speaker = SpeakerSerializer(read_only=True)
    bill = BillSerializer(read_only=True)

    class Meta:
        model = Statement
        fields = '__all__'

class SessionSerializer(serializers.ModelSerializer):
    bills = BillSerializer(many=True, read_only=True)
    statements = StatementSerializer(many=True, read_only=True)

    class Meta:
        model = Session
        fields = '__all__'

class StatementCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Statement
        fields = ['session', 'bill', 'speaker', 'text', 'sentiment_score', 'sentiment_reason'] 