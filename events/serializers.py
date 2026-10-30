from decimal import Decimal, InvalidOperation
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import serializers
from rest_framework.authtoken.models import Token
from .models import (
    AttributeDefinition, Event, EventAttributeValue, EventResult, Feedback,
    Registration, Stage, StageRole, User,
)


class RawValueField(serializers.Field):
    """Pass a primitive JSON scalar through without storing a JSONField in the model."""
    def to_internal_value(self, data):
        return data
    def to_representation(self, value):
        return value


class UserSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username", "role")


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    role = serializers.ChoiceField(choices=User.Role.choices, read_only=True)

    class Meta:
        model = User
        fields = ("id", "username", "email", "password", "first_name", "last_name", "role")
        read_only_fields = ("id",)

    def validate_password(self, value):
        validate_password(value)
        return value

    def create(self, validated_data):
        password = validated_data.pop("password")
        return User.objects.create_user(password=password, **validated_data)


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(trim_whitespace=False, write_only=True)


class StageRoleSerializer(serializers.ModelSerializer):
    user_details = UserSummarySerializer(source="user", read_only=True)

    class Meta:
        model = StageRole
        fields = ("id", "stage", "user", "user_details", "role", "created_at")
        read_only_fields = ("id", "created_at", "user_details")


class StageSerializer(serializers.ModelSerializer):
    order = serializers.IntegerField(min_value=1)
    assigned_roles = StageRoleSerializer(many=True, read_only=True)

    class Meta:
        model = Stage
        fields = ("id", "event", "title", "description", "order", "starts_at", "ends_at", "assigned_roles", "created_at")
        read_only_fields = ("id", "created_at")

    def validate(self, attrs):
        starts = attrs.get("starts_at", getattr(self.instance, "starts_at", None))
        ends = attrs.get("ends_at", getattr(self.instance, "ends_at", None))
        if starts and ends and starts >= ends:
            raise serializers.ValidationError({"ends_at": "Stage end must be after its start."})
        event = attrs.get("event", getattr(self.instance, "event", None))
        order = attrs.get("order", getattr(self.instance, "order", None))
        if event is not None and order is not None:
            duplicate = Stage.objects.filter(event=event, order=order)
            if self.instance is not None:
                duplicate = duplicate.exclude(pk=self.instance.pk)
            if duplicate.exists():
                raise serializers.ValidationError({"order": "Stage order must be unique within an event."})
        return attrs


class AttributeDefinitionSerializer(serializers.ModelSerializer):
    created_by = UserSummarySerializer(read_only=True)

    class Meta:
        model = AttributeDefinition
        fields = ("id", "key", "label", "data_type", "created_by", "created_at")
        read_only_fields = ("id", "created_by", "created_at")

    def validate(self, attrs):
        if self.instance and self.instance.event_values.exists() and attrs.get("data_type", self.instance.data_type) != self.instance.data_type:
            raise serializers.ValidationError({"data_type": "Data type cannot be changed after this attribute is used by an event."})
        return attrs


class EventAttributeValueSerializer(serializers.ModelSerializer):
    value = RawValueField()
    attribute_key = serializers.CharField(source="attribute_definition.key", read_only=True)
    attribute_label = serializers.CharField(source="attribute_definition.label", read_only=True)
    data_type = serializers.CharField(source="attribute_definition.data_type", read_only=True)

    class Meta:
        model = EventAttributeValue
        fields = ("id", "event", "attribute_definition", "attribute_key", "attribute_label", "data_type", "value", "updated_at")
        read_only_fields = ("id", "event", "attribute_key", "attribute_label", "data_type", "updated_at")

    def validate(self, attrs):
        definition = attrs.get("attribute_definition")
        raw = attrs.get("value")
        if definition is None:
            raise serializers.ValidationError({"attribute_definition": "This field is required."})
        kind = definition.data_type
        try:
            if kind == AttributeDefinition.DataType.TEXT:
                if not isinstance(raw, str):
                    raise ValueError("Expected a string.")
                parsed = raw
            elif kind == AttributeDefinition.DataType.INTEGER:
                if isinstance(raw, bool) or not isinstance(raw, int):
                    raise ValueError("Expected an integer.")
                parsed = raw
            elif kind == AttributeDefinition.DataType.DECIMAL:
                if isinstance(raw, bool) or not isinstance(raw, (int, float, str, Decimal)):
                    raise ValueError("Expected a decimal number.")
                parsed = Decimal(str(raw))
                if not parsed.is_finite():
                    raise ValueError("Decimal must be finite.")
                if parsed.as_tuple().exponent < -4 or (parsed != 0 and parsed.adjusted() >= 12):
                    raise ValueError("Decimal supports at most 12 integer digits and 4 decimal places.")
            elif kind == AttributeDefinition.DataType.BOOLEAN:
                if not isinstance(raw, bool):
                    raise ValueError("Expected true or false.")
                parsed = raw
            elif kind == AttributeDefinition.DataType.DATETIME:
                if not isinstance(raw, str):
                    raise ValueError("Expected an ISO-8601 datetime string.")
                parsed = parse_datetime(raw)
                if parsed is None:
                    raise ValueError("Invalid datetime. Use ISO-8601 format.")
                if timezone.is_naive(parsed):
                    parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
            else:
                raise ValueError("Unsupported attribute type.")
        except (ValueError, InvalidOperation, TypeError) as exc:
            raise serializers.ValidationError({"value": str(exc)})
        attrs["value"] = parsed
        return attrs

    def create(self, validated_data):
        event = self.context["event"]
        definition = validated_data["attribute_definition"]
        value = validated_data["value"]
        columns = {
            AttributeDefinition.DataType.TEXT: "text_value",
            AttributeDefinition.DataType.INTEGER: "integer_value",
            AttributeDefinition.DataType.DECIMAL: "decimal_value",
            AttributeDefinition.DataType.BOOLEAN: "boolean_value",
            AttributeDefinition.DataType.DATETIME: "datetime_value",
        }
        instance, created = EventAttributeValue.objects.get_or_create(
            event=event,
            attribute_definition=definition,
            defaults={columns[definition.data_type]: value},
        )
        if not created:
            for column in columns.values():
                setattr(instance, column, None)
            setattr(instance, columns[definition.data_type], value)
            instance.full_clean()
            instance.save()
        else:
            instance.full_clean()
            instance.save()
        return instance


class EventWriteSerializer(serializers.ModelSerializer):
    organizer = UserSummarySerializer(read_only=True)

    class Meta:
        model = Event
        fields = ("id", "title", "description", "starts_at", "ends_at", "capacity", "organizer", "status", "created_at", "updated_at")
        read_only_fields = ("id", "organizer", "status", "created_at", "updated_at")

    def validate(self, attrs):
        start = attrs.get("starts_at", getattr(self.instance, "starts_at", None))
        end = attrs.get("ends_at", getattr(self.instance, "ends_at", None))
        capacity = attrs.get("capacity", getattr(self.instance, "capacity", None))
        if start and end and start >= end:
            raise serializers.ValidationError({"ends_at": "Event end must be after its start."})
        if capacity is not None and capacity < 1:
            raise serializers.ValidationError({"capacity": "Capacity must be at least 1."})
        if self.instance is not None and capacity is not None:
            confirmed = self.instance.registrations.filter(status="confirmed").count()
            if capacity < confirmed:
                raise serializers.ValidationError({"capacity": f"Capacity cannot be lower than the {confirmed} confirmed registrations."})
        return attrs


class PublicEventSerializer(serializers.ModelSerializer):
    stages = StageSerializer(many=True, read_only=True)
    attributes = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = ("id", "title", "description", "starts_at", "ends_at", "capacity", "status", "stages", "attributes")

    def get_attributes(self, obj):
        return EventAttributeValueSerializer(obj.attribute_values.select_related("attribute_definition").all(), many=True).data


class RegistrationSerializer(serializers.ModelSerializer):
    participant_details = UserSummarySerializer(source="participant", read_only=True)
    event_title = serializers.CharField(source="event.title", read_only=True)

    class Meta:
        model = Registration
        fields = ("id", "event", "event_title", "participant", "participant_details", "status", "registered_at")
        read_only_fields = fields


class FeedbackSerializer(serializers.ModelSerializer):
    participant = serializers.CharField(source="registration.participant.username", read_only=True)
    registration_id = serializers.IntegerField(source="registration.id", read_only=True)

    class Meta:
        model = Feedback
        fields = ("id", "registration_id", "participant", "rating", "comment", "created_at")
        read_only_fields = ("id", "registration_id", "participant", "created_at")


class FeedbackCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Feedback
        fields = ("rating", "comment")

    def validate_rating(self, value):
        if not 1 <= value <= 5:
            raise serializers.ValidationError("Rating must be between 1 and 5.")
        return value


class EventResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = EventResult
        fields = ("id", "event", "title", "content", "is_published", "published_at", "updated_at")
        read_only_fields = ("id", "event", "is_published", "published_at", "updated_at")
