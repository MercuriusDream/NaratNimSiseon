from rest_framework import serializers
from .models import Session, Bill, Speaker, Statement, Party, Category, Subcategory, StatementCategory
from django.utils import timezone


class StatementCategorySerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name',
                                          read_only=True)
    subcategory_name = serializers.CharField(source='subcategory.name',
                                             read_only=True)

    class Meta:
        model = StatementCategory
        fields = [
            'category', 'subcategory', 'category_name', 'subcategory_name',
            'confidence_score'
        ]


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
    bill_name = serializers.CharField(source='bill_nm', read_only=True)
    bill_no = serializers.CharField(source='bill_id', read_only=True)
    session_date = serializers.DateField(source='session.conf_dt', read_only=True)
    proposer = serializers.SerializerMethodField()
    propose_dt = serializers.DateField(source='session.conf_dt', read_only=True)
    content = serializers.CharField(source='bill_nm', read_only=True)
    status = serializers.SerializerMethodField()

    class Meta:
        model = Bill
        fields = ['bill_id', 'bill_nm', 'bill_name', 'bill_no', 'session', 'session_date', 
                 'proposer', 'propose_dt', 'content', 'status', 'link_url', 'created_at', 'updated_at']

    def get_proposer(self, obj):
        return "국회"  # Default proposer since we don't have this field in the model
    
    def get_status(self, obj):
        return "pending"  # Default status since we don't have this field in the model


class StatementSerializer(serializers.ModelSerializer):
    speaker_name = serializers.CharField(source='speaker.naas_nm',
                                         read_only=True)
    party_name = serializers.CharField(source='speaker.plpt_nm',
                                       read_only=True)
    session_date = serializers.DateField(source='session.conf_dt',
                                         read_only=True)
    bill_name = serializers.CharField(source='bill.bill_nm', read_only=True)
    categories = StatementCategorySerializer(many=True, read_only=True)

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
        if value > timezone.now().date():  # Compare date with date
            raise serializers.ValidationError("회의 날짜는 현재 날짜보다 이후일 수 없습니다.")
        return value

    def validate(self, data):
        # if data.get('conf_dt') and data.get('conf_dt_end'): # conf_dt_end does not exist
        #     if data['conf_dt'] > data['conf_dt_end']:
        #         raise serializers.ValidationError("회의 종료 시간은 시작 시간보다 이후여야 합니다.")
        if 'bg_ptm' in data and 'ed_ptm' in data and data['bg_ptm'] and data[
                'ed_ptm']:
            if data['bg_ptm'] > data['ed_ptm']:
                raise serializers.ValidationError(
                    "회의 종료 시간은 시작 시간보다 이후여야 합니다 (bg_ptm, ed_ptm).")
        return data


class StatementCreateSerializer(serializers.ModelSerializer):

    class Meta:
        model = Statement
        fields = ['session', 'bill', 'speaker', 'text',
                  'sentiment_score']  # Changed 'content' to 'text'

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
        if bill and not Bill.objects.filter(
                bill_id=bill.bill_id).exists():  # Corrected to use bill_id
            raise serializers.ValidationError("유효하지 않은 의안입니다.")

        # Check if text content is provided and valid
        text_content = data.get('text')  # Changed from 'content'
        if not text_content or len(text_content.strip()) < 10:
            raise serializers.ValidationError(
                {"text":
                 "발언 내용은 10자 이상이어야 합니다."})  # Changed error field and message

        # Validate sentiment score
        sentiment_score = data.get('sentiment_score')
        if sentiment_score is not None and (sentiment_score < -1
                                            or sentiment_score > 1):
            raise serializers.ValidationError("감정 점수는 -1에서 1 사이여야 합니다.")

        return data


class PartySerializer(serializers.ModelSerializer):

    class Meta:
        model = Party
        fields = '__all__'


class SubcategorySerializer(serializers.ModelSerializer):

    class Meta:
        model = Subcategory
        fields = ['id', 'name', 'description']


class CategorySerializer(serializers.ModelSerializer):
    subcategories = SubcategorySerializer(many=True, read_only=True)

    class Meta:
        model = Category
        fields = ['id', 'name', 'description', 'subcategories']
