from decimal import Decimal
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class User(AbstractUser):
    class Role(models.TextChoices):
        PARTICIPANT = "participant", "Participant"
        ORGANIZER = "organizer", "Organizer"

    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.PARTICIPANT, db_index=True)

    def __str__(self):
        return f"{self.username} ({self.role})"


class Event(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        CLOSED = "closed", "Closed"
        FINISHED = "finished", "Finished"

    title = models.CharField(max_length=200)
    description = models.TextField()
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    capacity = models.PositiveIntegerField()
    organizer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="events")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("starts_at", "id")
        constraints = [
            models.CheckConstraint(condition=Q(capacity__gt=0), name="event_capacity_positive"),
            models.CheckConstraint(condition=Q(starts_at__lt=F("ends_at")), name="event_start_before_end"),
        ]
        indexes = [models.Index(fields=("status", "starts_at"), name="event_status_start_idx")]

    def clean(self):
        super().clean()
        if self.starts_at and self.ends_at and self.starts_at >= self.ends_at:
            raise ValidationError({"ends_at": "Event end must be after its start."})
        if self.capacity is not None and self.capacity < 1:
            raise ValidationError({"capacity": "Capacity must be at least 1."})

    def __str__(self):
        return self.title


class Stage(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="stages")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField()
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("order", "id")
        constraints = [
            models.UniqueConstraint(fields=("event", "order"), name="unique_stage_order_per_event"),
            models.CheckConstraint(condition=Q(starts_at__lt=F("ends_at")), name="stage_start_before_end"),
        ]

    def clean(self):
        super().clean()
        if self.starts_at and self.ends_at and self.starts_at >= self.ends_at:
            raise ValidationError({"ends_at": "Stage end must be after its start."})

    def __str__(self):
        return f"{self.event.title} — {self.title}"


class StageRole(models.Model):
    class Role(models.TextChoices):
        SPEAKER = "speaker", "Speaker"
        JUDGE = "judge", "Judge"
        COACH = "coach", "Coach"

    stage = models.ForeignKey(Stage, on_delete=models.CASCADE, related_name="assigned_roles")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="stage_roles")
    role = models.CharField(max_length=20, choices=Role.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("stage", "user", "role"), name="unique_user_role_per_stage")]


class AttributeDefinition(models.Model):
    class DataType(models.TextChoices):
        TEXT = "text", "Text"
        INTEGER = "integer", "Integer"
        DECIMAL = "decimal", "Decimal"
        BOOLEAN = "boolean", "Boolean"
        DATETIME = "datetime", "Date/time"

    key = models.SlugField(max_length=80, unique=True)
    label = models.CharField(max_length=120)
    data_type = models.CharField(max_length=20, choices=DataType.choices)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="attribute_definitions")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("key",)

    def __str__(self):
        return f"{self.label} ({self.data_type})"


class EventAttributeValue(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="attribute_values")
    attribute_definition = models.ForeignKey(AttributeDefinition, on_delete=models.PROTECT, related_name="event_values")
    text_value = models.TextField(null=True, blank=True)
    integer_value = models.BigIntegerField(null=True, blank=True)
    decimal_value = models.DecimalField(max_digits=16, decimal_places=4, null=True, blank=True)
    boolean_value = models.BooleanField(null=True, blank=True)
    datetime_value = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("event", "attribute_definition"), name="uniq_event_attr_val"),
            models.CheckConstraint(
                condition=(
                    Q(text_value__isnull=False, integer_value__isnull=True, decimal_value__isnull=True, boolean_value__isnull=True, datetime_value__isnull=True)
                    | Q(text_value__isnull=True, integer_value__isnull=False, decimal_value__isnull=True, boolean_value__isnull=True, datetime_value__isnull=True)
                    | Q(text_value__isnull=True, integer_value__isnull=True, decimal_value__isnull=False, boolean_value__isnull=True, datetime_value__isnull=True)
                    | Q(text_value__isnull=True, integer_value__isnull=True, decimal_value__isnull=True, boolean_value__isnull=False, datetime_value__isnull=True)
                    | Q(text_value__isnull=True, integer_value__isnull=True, decimal_value__isnull=True, boolean_value__isnull=True, datetime_value__isnull=False)
                ),
                name="event_attr_one_value",
            ),
        ]

    @property
    def value(self):
        field_by_type = {
            AttributeDefinition.DataType.TEXT: "text_value",
            AttributeDefinition.DataType.INTEGER: "integer_value",
            AttributeDefinition.DataType.DECIMAL: "decimal_value",
            AttributeDefinition.DataType.BOOLEAN: "boolean_value",
            AttributeDefinition.DataType.DATETIME: "datetime_value",
        }
        return getattr(self, field_by_type[self.attribute_definition.data_type])

    def clean(self):
        super().clean()
        fields = {
            AttributeDefinition.DataType.TEXT: "text_value",
            AttributeDefinition.DataType.INTEGER: "integer_value",
            AttributeDefinition.DataType.DECIMAL: "decimal_value",
            AttributeDefinition.DataType.BOOLEAN: "boolean_value",
            AttributeDefinition.DataType.DATETIME: "datetime_value",
        }
        selected = [name for name in fields.values() if getattr(self, name) is not None]
        expected = fields.get(self.attribute_definition.data_type)
        if selected != [expected]:
            raise ValidationError("Exactly one value column must be set, matching the attribute's declared data type.")

    def __str__(self):
        return f"{self.event.title}: {self.attribute_definition.key}={self.value}"


class Registration(models.Model):
    class Status(models.TextChoices):
        CONFIRMED = "confirmed", "Confirmed"
        CANCELLED = "cancelled", "Cancelled"

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="registrations")
    participant = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="event_registrations")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.CONFIRMED, db_index=True)
    registered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-registered_at",)
        constraints = [models.UniqueConstraint(fields=("event", "participant"), name="uniq_reg_event_user")]
        indexes = [models.Index(fields=("event", "registered_at"), name="registration_event_date_idx")]

    def __str__(self):
        return f"{self.participant.username} → {self.event.title}"


class Feedback(models.Model):
    registration = models.OneToOneField(Registration, on_delete=models.CASCADE, related_name="feedback")
    rating = models.PositiveSmallIntegerField()
    comment = models.TextField(blank=True, max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [models.CheckConstraint(condition=Q(rating__gte=1, rating__lte=5), name="feedback_rating_1_to_5")]

    def clean(self):
        super().clean()
        if not 1 <= self.rating <= 5:
            raise ValidationError({"rating": "Rating must be between 1 and 5."})
        if self.registration_id and self.registration.event.status != Event.Status.FINISHED:
            raise ValidationError("Feedback is allowed only after the event has finished.")


class EventResult(models.Model):
    event = models.OneToOneField(Event, on_delete=models.CASCADE, related_name="result")
    title = models.CharField(max_length=200)
    content = models.TextField()
    is_published = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        super().clean()
        if self.is_published and self.event.status != Event.Status.FINISHED:
            raise ValidationError("Results can be published only after the event has finished.")

    def publish(self):
        if self.event.status != Event.Status.FINISHED:
            raise ValidationError("Results can be published only after the event has finished.")
        self.is_published = True
        self.published_at = timezone.now()
