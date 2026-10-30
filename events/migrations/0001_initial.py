import django.contrib.auth.models
import django.contrib.auth.validators
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models

class Migration(migrations.Migration):
    initial = True
    dependencies = [("auth", "0012_alter_user_first_name_max_length")]
    operations = [
        migrations.CreateModel(
            name="User",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("password", models.CharField(max_length=128, verbose_name="password")),
                ("last_login", models.DateTimeField(blank=True, null=True, verbose_name="last login")),
                ("is_superuser", models.BooleanField(default=False, help_text="Designates that this user has all permissions without explicitly assigning them.", verbose_name="superuser status")),
                ("username", models.CharField(error_messages={"unique": "A user with that username already exists."}, help_text="Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only.", max_length=150, unique=True, validators=[django.contrib.auth.validators.UnicodeUsernameValidator()], verbose_name="username")),
                ("first_name", models.CharField(blank=True, max_length=150, verbose_name="first name")),
                ("last_name", models.CharField(blank=True, max_length=150, verbose_name="last name")),
                ("email", models.EmailField(max_length=254, unique=True, verbose_name="email address")),
                ("is_staff", models.BooleanField(default=False, help_text="Designates whether the user can log into this admin site.", verbose_name="staff status")),
                ("is_active", models.BooleanField(default=True, help_text="Designates whether this user should be treated as active. Unselect this instead of deleting accounts.", verbose_name="active")),
                ("date_joined", models.DateTimeField(default=django.utils.timezone.now, verbose_name="date joined")),
                ("role", models.CharField(choices=[("participant", "Participant"), ("organizer", "Organizer")], db_index=True, default="participant", max_length=20)),
                ("groups", models.ManyToManyField(blank=True, help_text="The groups this user belongs to. A user will get all permissions granted to each of their groups.", related_name="user_set", related_query_name="user", to="auth.group", verbose_name="groups")),
                ("user_permissions", models.ManyToManyField(blank=True, help_text="Specific permissions for this user.", related_name="user_set", related_query_name="user", to="auth.permission", verbose_name="user permissions")),
            ],
            options={"verbose_name": "user", "verbose_name_plural": "users", "abstract": False},
            managers=[("objects", django.contrib.auth.models.UserManager())],
        ),
        migrations.CreateModel(
            name="AttributeDefinition",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.SlugField(max_length=80, unique=True)),
                ("label", models.CharField(max_length=120)),
                ("data_type", models.CharField(choices=[("text", "Text"), ("integer", "Integer"), ("decimal", "Decimal"), ("boolean", "Boolean"), ("datetime", "Date/time")], max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="attribute_definitions", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("key",)},
        ),
        migrations.CreateModel(
            name="Event",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=200)),
                ("description", models.TextField()),
                ("starts_at", models.DateTimeField()),
                ("ends_at", models.DateTimeField()),
                ("capacity", models.PositiveIntegerField()),
                ("status", models.CharField(choices=[("draft", "Draft"), ("published", "Published"), ("closed", "Closed"), ("finished", "Finished")], db_index=True, default="draft", max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("organizer", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="events", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("starts_at", "id")},
        ),
        migrations.CreateModel(
            name="EventResult",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=200)),
                ("content", models.TextField()),
                ("is_published", models.BooleanField(default=False)),
                ("published_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("event", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="result", to="events.event")),
            ],
        ),
        migrations.CreateModel(
            name="EventAttributeValue",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("text_value", models.TextField(blank=True, null=True)),
                ("integer_value", models.BigIntegerField(blank=True, null=True)),
                ("decimal_value", models.DecimalField(blank=True, decimal_places=4, max_digits=16, null=True)),
                ("boolean_value", models.BooleanField(blank=True, null=True)),
                ("datetime_value", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("attribute_definition", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="event_values", to="events.attributedefinition")),
                ("event", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="attribute_values", to="events.event")),
            ],
        ),
        migrations.CreateModel(
            name="Registration",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("registered_at", models.DateTimeField(auto_now_add=True)),
                ("status", models.CharField(choices=[("confirmed", "Confirmed"), ("cancelled", "Cancelled")], db_index=True, default="confirmed", max_length=20)),
                ("event", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="registrations", to="events.event")),
                ("participant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="event_registrations", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-registered_at",)},
        ),
        migrations.CreateModel(
            name="Stage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=200)),
                ("description", models.TextField(blank=True)),
                ("order", models.PositiveIntegerField()),
                ("starts_at", models.DateTimeField()),
                ("ends_at", models.DateTimeField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("event", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="stages", to="events.event")),
            ],
            options={"ordering": ("order", "id")},
        ),
        migrations.CreateModel(
            name="StageRole",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("role", models.CharField(choices=[("speaker", "Speaker"), ("judge", "Judge"), ("coach", "Coach")], max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("stage", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="assigned_roles", to="events.stage")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="stage_roles", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="Feedback",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("rating", models.PositiveSmallIntegerField()),
                ("comment", models.TextField(blank=True, max_length=2000)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("registration", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="feedback", to="events.registration")),
            ],
            options={"ordering": ("-created_at",)},
        ),
        migrations.AddConstraint(model_name="event", constraint=models.CheckConstraint(condition=models.Q(("capacity__gt", 0)), name="event_capacity_positive")),
        migrations.AddConstraint(model_name="event", constraint=models.CheckConstraint(condition=models.Q(("starts_at__lt", models.F("ends_at"))), name="event_start_before_end")),
        migrations.AddIndex(model_name="event", index=models.Index(fields=["status", "starts_at"], name="event_status_start_idx")),
        migrations.AddConstraint(model_name="eventattributevalue", constraint=models.UniqueConstraint(fields=("event", "attribute_definition"), name="uniq_event_attr_val")),
        migrations.AddConstraint(model_name="eventattributevalue", constraint=models.CheckConstraint(condition=(models.Q(("text_value__isnull", False), ("integer_value__isnull", True), ("decimal_value__isnull", True), ("boolean_value__isnull", True), ("datetime_value__isnull", True)) | models.Q(("text_value__isnull", True), ("integer_value__isnull", False), ("decimal_value__isnull", True), ("boolean_value__isnull", True), ("datetime_value__isnull", True)) | models.Q(("text_value__isnull", True), ("integer_value__isnull", True), ("decimal_value__isnull", False), ("boolean_value__isnull", True), ("datetime_value__isnull", True)) | models.Q(("text_value__isnull", True), ("integer_value__isnull", True), ("decimal_value__isnull", True), ("boolean_value__isnull", False), ("datetime_value__isnull", True)) | models.Q(("text_value__isnull", True), ("integer_value__isnull", True), ("decimal_value__isnull", True), ("boolean_value__isnull", True), ("datetime_value__isnull", False))), name="event_attr_one_value")),
        migrations.AddConstraint(model_name="registration", constraint=models.UniqueConstraint(fields=("event", "participant"), name="uniq_reg_event_user")),
        migrations.AddIndex(model_name="registration", index=models.Index(fields=["event", "registered_at"], name="registration_event_date_idx")),
        migrations.AddConstraint(model_name="stage", constraint=models.UniqueConstraint(fields=("event", "order"), name="unique_stage_order_per_event")),
        migrations.AddConstraint(model_name="stage", constraint=models.CheckConstraint(condition=models.Q(("starts_at__lt", models.F("ends_at"))), name="stage_start_before_end")),
        migrations.AddConstraint(model_name="stagerole", constraint=models.UniqueConstraint(fields=("stage", "user", "role"), name="unique_user_role_per_stage")),
        migrations.AddConstraint(model_name="feedback", constraint=models.CheckConstraint(condition=models.Q(("rating__gte", 1), ("rating__lte", 5)), name="feedback_rating_1_to_5")),
    ]
