from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .views import (
    AttributeDefinitionViewSet, EventFeedbackView, EventRegistrationView,
    LoginView, MeView, OrganizerEventViewSet, ParticipantRegistrationViewSet,
    PublicEventResultsView, PublicEventViewSet, RegisterView, StageRoleViewSet,
    StageViewSet,
)

router = DefaultRouter()
router.register("public/events", PublicEventViewSet, basename="public-events")
router.register("organizer/events", OrganizerEventViewSet, basename="organizer-events")
router.register("organizer/stages", StageViewSet, basename="organizer-stages")
router.register("organizer/stage-roles", StageRoleViewSet, basename="organizer-stage-roles")
router.register("organizer/attributes", AttributeDefinitionViewSet, basename="organizer-attributes")
router.register("participant/registrations", ParticipantRegistrationViewSet, basename="participant-registrations")

urlpatterns = [
    path("auth/register/", RegisterView.as_view(), name="auth-register"),
    path("auth/login/", LoginView.as_view(), name="auth-login"),
    path("auth/me/", MeView.as_view(), name="auth-me"),
    path("participant/events/<int:event_id>/register/", EventRegistrationView.as_view(), name="event-register"),
    path("participant/events/<int:event_id>/feedback/", EventFeedbackView.as_view(), name="event-feedback"),
    path("public/events/<int:event_id>/results/", PublicEventResultsView.as_view(), name="public-event-results"),
    path("", include(router.urls)),
]
