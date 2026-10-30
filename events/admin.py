from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import AttributeDefinition, Event, EventAttributeValue, EventResult, Feedback, Registration, Stage, StageRole, User

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("Event Planet", {"fields": ("role",)}),)
    add_fieldsets = UserAdmin.add_fieldsets + (("Event Planet", {"fields": ("role", "email")}),)
    list_display = ("username", "email", "role", "is_staff", "is_active")
    list_filter = ("role", "is_staff", "is_active")

class StageInline(admin.TabularInline):
    model = Stage
    extra = 0

class AttributeValueInline(admin.TabularInline):
    model = EventAttributeValue
    extra = 0

@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("title", "organizer", "status", "starts_at", "ends_at", "capacity")
    list_filter = ("status", "starts_at")
    search_fields = ("title", "description", "organizer__username")
    inlines = (StageInline, AttributeValueInline)

@admin.register(Stage)
class StageAdmin(admin.ModelAdmin):
    list_display = ("title", "event", "order", "starts_at", "ends_at")
    list_filter = ("event",)

@admin.register(StageRole)
class StageRoleAdmin(admin.ModelAdmin):
    list_display = ("stage", "user", "role")

@admin.register(AttributeDefinition)
class AttributeDefinitionAdmin(admin.ModelAdmin):
    list_display = ("key", "label", "data_type", "created_by")
    search_fields = ("key", "label")

@admin.register(Registration)
class RegistrationAdmin(admin.ModelAdmin):
    list_display = ("event", "participant", "registered_at")
    list_filter = ("event",)

@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ("registration", "rating", "created_at")

@admin.register(EventResult)
class EventResultAdmin(admin.ModelAdmin):
    list_display = ("event", "title", "is_published", "published_at")
