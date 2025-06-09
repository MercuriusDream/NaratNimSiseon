from rest_framework import serializers
from .models import Session, Bill, Speaker, Statement, Party, Category, Subcategory, StatementCategory, VotingRecord
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
    # Optionally, you can add explicit fields for clarity
    elecd_nm = serializers.ListField(child=serializers.CharField(),
                                     required=False)
    elecd_div_nm = serializers.ListField(child=serializers.CharField(),
                                         required=False)
    cmit_nm = serializers.ListField(child=serializers.CharField(),
                                    required=False)
    blng_cmit_nm = serializers.ListField(child=serializers.CharField(),
                                         required=False)
    gtelt_eraco = serializers.ListField(child=serializers.IntegerField(),
                                        required=False)
    era_int = serializers.IntegerField(required=False, allow_null=True)
    nth_term = serializers.IntegerField(required=False, allow_null=True)
    naas_pic = serializers.URLField(required=False,
                                    allow_blank=True,
                                    allow_null=True)

    class Meta:
        model = Speaker
        fields = '__all__'

    def to_representation(self, instance):
        """
        Ensure all list/integer fields are serialized with correct types for frontend.
        Lists are always [], never null. Integers are always int or null.
        """
        rep = super().to_representation(instance)
        # Always output lists for JSONField-backed fields
        for field in [
                'elecd_nm', 'elecd_div_nm', 'cmit_nm', 'blng_cmit_nm',
                'gtelt_eraco'
        ]:
            value = getattr(instance, field, None)
            if not isinstance(value, list):
                rep[field] = [] if value is None else [value]
            else:
                rep[field] = value
        # Integer fields: output as int or None
        rep['era_int'] = instance.era_int if instance.era_int is not None else None
        rep['nth_term'] = instance.nth_term if instance.nth_term is not None else None
        # naas_pic as URL or empty string
        rep['naas_pic'] = instance.naas_pic or ""
        return rep

    def to_internal_value(self, data):
        """
        Accept string or list for JSONFields. Accept string or int for integer fields.
        Defensive: always coerce to correct type.
        """
        import re
        for field in ['elecd_nm', 'elecd_div_nm', 'cmit_nm', 'blng_cmit_nm']:
            value = data.get(field)
            if value is None:
                data[field] = []
            elif isinstance(value, str):
                sep = ',' if field in ['cmit_nm', 'blng_cmit_nm'] else '/'
                data[field] = [
                    v.strip() for v in value.split(sep) if v.strip()
                ]
            elif not isinstance(value, list):
                data[field] = [str(value)]
        # gtelt_eraco: accept string like '제21대, 제22대' or list of ints
        gtelt = data.get('gtelt_eraco')
        if gtelt is None:
            data['gtelt_eraco'] = []
        elif isinstance(gtelt, str):
            data['gtelt_eraco'] = [
                int(num) for num in re.findall(r'제(\d+)대', gtelt)
            ]
        elif isinstance(gtelt, list):
            # Coerce all to int
            data['gtelt_eraco'] = [int(x) for x in gtelt if str(x).isdigit()]
        else:
            data['gtelt_eraco'] = []
        # Defensive for integer fields
        for int_field in ['era_int', 'nth_term']:
            value = data.get(int_field)
            if value in (None, "", []):
                data[int_field] = None
            elif isinstance(value, str) and value.isdigit():
                data[int_field] = int(value)
            elif isinstance(value, int):
                data[int_field] = value
            else:
                data[int_field] = None
        # naas_pic: always string or ""
        pic = data.get('naas_pic')
        data['naas_pic'] = str(pic) if pic else ""
        return super().to_internal_value(data)


# PATCH: PartySerializer doesn't need extra logic as all fields are scalar, but can ensure consistency if needed.
class PartySerializer(serializers.ModelSerializer):

    class Meta:
        model = Party
        fields = '__all__'

    def to_internal_value(self, data):
        """Allow input as string or list for JSONFields."""
        for field in ['elecd_nm', 'elecd_div_nm', 'cmit_nm', 'blng_cmit_nm']:
            value = data.get(field)
            if value and isinstance(value, str):
                # Accept comma or slash separated strings
                sep = ',' if field in ['cmit_nm', 'blng_cmit_nm'] else '/'
                data[field] = [
                    v.strip() for v in value.split(sep) if v.strip()
                ]
        # gtelt_eraco: accept string like '제21대, 제22대' or list of ints
        gtelt = data.get('gtelt_eraco')
        import re
        if gtelt and isinstance(gtelt, str):
            data['gtelt_eraco'] = [
                int(num) for num in re.findall(r'제(\d+)대', gtelt)
            ]
        return super().to_internal_value(data)

    def validate_naas_nm(self, value):
        if len(value) < 2:
            raise serializers.ValidationError("의원 이름은 2글자 이상이어야 합니다.")
        return value

    def validate_plpt_nm(self, value):
        if not value:
            raise serializers.ValidationError("소속 정당은 필수입니다.")
        return value


class BillSerializer(serializers.ModelSerializer):
    bill_name = serializers.SerializerMethodField()
    session_date = serializers.DateField(source='session.conf_dt',
                                         read_only=True)
    content = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()

    class Meta:
        model = Bill
        fields = [
            'bill_id', 'bill_nm', 'bill_name', 'bill_no', 'session',
            'session_date', 'proposer', 'propose_dt', 'content', 'status',
            'link_url', 'created_at', 'updated_at'
        ]

    def get_bill_name(self, obj):
        """Clean bill name by removing leading numbers like '10. '"""
        clean_title = obj.bill_nm
        if clean_title and '. ' in clean_title:
            parts = clean_title.split('. ', 1)
            if parts[0].isdigit():
                clean_title = parts[1]
        return clean_title

    def get_content(self, obj):
        """Clean content by removing leading numbers like '10. '"""
        clean_title = obj.bill_nm
        if clean_title and '. ' in clean_title:
            parts = clean_title.split('. ', 1)
            if parts[0].isdigit():
                clean_title = parts[1]
        return clean_title

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
    content = serializers.CharField(
        source='text',
        read_only=True)  # Add content field for frontend compatibility

    class Meta:
        model = Statement
        fields = '__all__'

    def validate_text(self, value):
        if len(value.strip()) < 10:
            raise serializers.ValidationError("발언 내용은 10자 이상이어야 합니다.")
        return value

    def validate_sentiment_score(self, value):
        if value is not None and (value < -1 or value > 1):
            raise serializers.ValidationError("감정 점수는 -1에서 1 사이여야 합니다.")
        return value


class SessionListSerializer(serializers.ModelSerializer):
    """Optimized serializer for session list view without expensive joins"""

    class Meta:
        model = Session
        fields = [
            'conf_id', 'era_co', 'sess', 'dgr', 'conf_dt', 'conf_knd',
            'cmit_nm', 'title'
        ]


class SessionSerializer(serializers.ModelSerializer):
    bills = BillSerializer(many=True, read_only=True)
    statements = StatementSerializer(many=True, read_only=True)

    class Meta:
        model = Session
        fields = [
            'conf_id', 'era_co', 'sess', 'dgr', 'conf_dt', 'conf_knd',
            'cmit_nm', 'conf_plc', 'title', 'bg_ptm', 'ed_ptm', 'down_url',
            'bills', 'statements'
        ]

    def validate_conf_dt(self, value):
        if value > timezone.now().date():  # Compare date with date
            raise serializers.ValidationError("회의 날짜는 현재 날짜보다 이후일 수 없습니다.")
        return value

    def validate(self, data):
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


class VotingRecordSerializer(serializers.ModelSerializer):
    speaker_name = serializers.CharField(source='speaker.naas_nm',
                                         read_only=True)
    party_name = serializers.CharField(source='speaker.plpt_nm',
                                       read_only=True)
    bill_name = serializers.CharField(source='bill.bill_nm', read_only=True)

    class Meta:
        model = VotingRecord
        fields = [
            'id', 'bill', 'speaker', 'vote_result', 'vote_date',
            'sentiment_score', 'speaker_name', 'party_name', 'bill_name',
            'created_at'
        ]
