from django.contrib.auth import authenticate
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.authtoken.models import Token

from .models import AttributeDefinition, Event, EventAttributeValue, EventResult, Feedback, Registration, Stage, StageRole, User
from .permissions import IsOrganizer, IsParticipant
from .serializers import (
    AttributeDefinitionSerializer, EventAttributeValueSerializer, EventResultSerializer,
    EventWriteSerializer, FeedbackCreateSerializer, FeedbackSerializer, LoginSerializer,
    PublicEventSerializer, RegisterSerializer, RegistrationSerializer, StageRoleSerializer,
    StageSerializer, UserSummarySerializer,
)


class RegisterView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        token, _ = Token.objects.get_or_create(user=user)
        return Response({"token": token.key, "user": UserSummarySerializer(user).data}, status=status.HTTP_201_CREATED)


class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(request=request, username=serializer.validated_data["username"], password=serializer.validated_data["password"])
        if user is None:
            return Response({"detail": "Invalid username or password."}, status=status.HTTP_400_BAD_REQUEST)
        token, _ = Token.objects.get_or_create(user=user)
        return Response({"token": token.key, "user": UserSummarySerializer(user).data})


class MeView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        return Response({"id": request.user.id, "username": request.user.username, "email": request.user.email, "first_name": request.user.first_name, "last_name": request.user.last_name, "role": request.user.role})


class PublicEventViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = PublicEventSerializer
    queryset = Event.objects.filter(status=Event.Status.PUBLISHED).prefetch_related("stages", "attribute_values__attribute_definition")


class OrganizerEventViewSet(viewsets.ModelViewSet):
    serializer_class = EventWriteSerializer
    permission_classes = [IsAuthenticated, IsOrganizer]

    def get_queryset(self):
        return Event.objects.filter(organizer=self.request.user).prefetch_related("stages", "attribute_values__attribute_definition")

    def perform_create(self, serializer):
        serializer.save(organizer=self.request.user, status=Event.Status.DRAFT)

    def perform_destroy(self, instance):
        if instance.status != Event.Status.DRAFT:
            raise ValidationError("Only draft events can be deleted. Close or finish published events instead.")
        instance.delete()

    @action(detail=True, methods=["post"], url_path="transition")
    def transition(self, request, pk=None):
        event = self.get_object()
        target = request.data.get("status")
        transitions = {
            Event.Status.DRAFT: {Event.Status.PUBLISHED},
            Event.Status.PUBLISHED: {Event.Status.CLOSED},
            Event.Status.CLOSED: {Event.Status.FINISHED},
            Event.Status.FINISHED: set(),
        }
        if target not in Event.Status.values:
            raise ValidationError({"status": "Provide a valid event status."})
        if target not in transitions[event.status]:
            raise ValidationError({"status": f"Transition from '{event.status}' to '{target}' is not allowed."})
        event.status = target
        event.save(update_fields=["status", "updated_at"])
        return Response(EventWriteSerializer(event, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["get", "post"], url_path="stages")
    def stages(self, request, pk=None):
        event = self.get_object()
        if request.method == "GET":
            return Response(StageSerializer(event.stages.prefetch_related("assigned_roles__user"), many=True).data)
        payload = request.data.copy()
        payload["event"] = event.pk
        serializer = StageSerializer(data=payload, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        serializer.save(event=event)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get", "post"], url_path="attributes")
    def attributes(self, request, pk=None):
        event = self.get_object()
        if request.method == "GET":
            values = event.attribute_values.select_related("attribute_definition").all()
            return Response(EventAttributeValueSerializer(values, many=True).data)
        serializer = EventAttributeValueSerializer(data=request.data, context={**self.get_serializer_context(), "event": event})
        serializer.is_valid(raise_exception=True)
        value = serializer.save()
        return Response(EventAttributeValueSerializer(value).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"], url_path="registrations")
    def registrations(self, request, pk=None):
        event = self.get_object()
        queryset = event.registrations.select_related("participant", "event").all()
        return Response(RegistrationSerializer(queryset, many=True).data)

    @action(detail=True, methods=["get"], url_path="feedback")
    def feedback(self, request, pk=None):
        event = self.get_object()
        queryset = Feedback.objects.filter(registration__event=event).select_related("registration__participant")
        return Response(FeedbackSerializer(queryset, many=True).data)

    @action(detail=True, methods=["get", "post"], url_path="results")
    def results(self, request, pk=None):
        event = self.get_object()
        if request.method == "GET":
            result = get_object_or_404(EventResult, event=event)
            return Response(EventResultSerializer(result).data)
        if event.status != Event.Status.FINISHED:
            raise ValidationError("Results can be published only after the event has finished.")
        existing = EventResult.objects.filter(event=event).first()
        if existing:
            serializer = EventResultSerializer(existing, data=request.data, partial=True, context=self.get_serializer_context())
        else:
            serializer = EventResultSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        result = serializer.save(event=event, is_published=True, published_at=timezone.now())
        return Response(EventResultSerializer(result).data, status=status.HTTP_201_CREATED if existing is None else status.HTTP_200_OK)


class StageViewSet(viewsets.ModelViewSet):
    serializer_class = StageSerializer
    permission_classes = [IsAuthenticated, IsOrganizer]

    def get_queryset(self):
        return Stage.objects.filter(event__organizer=self.request.user).select_related("event").prefetch_related("assigned_roles__user")

    def perform_create(self, serializer):
        event = serializer.validated_data["event"]
        if event.organizer_id != self.request.user.id:
            raise PermissionDenied("You can manage stages only for your own events.")
        serializer.save()

    def perform_update(self, serializer):
        event = serializer.validated_data.get("event", serializer.instance.event)
        if event.organizer_id != self.request.user.id:
            raise PermissionDenied("You can manage stages only for your own events.")
        serializer.save()


class StageRoleViewSet(viewsets.ModelViewSet):
    serializer_class = StageRoleSerializer
    permission_classes = [IsAuthenticated, IsOrganizer]

    def get_queryset(self):
        return StageRole.objects.filter(stage__event__organizer=self.request.user).select_related("stage", "user")

    def perform_create(self, serializer):
        stage = serializer.validated_data["stage"]
        if stage.event.organizer_id != self.request.user.id:
            raise PermissionDenied("You can assign roles only on stages of your own events.")
        serializer.save()

    def perform_update(self, serializer):
        stage = serializer.validated_data.get("stage", serializer.instance.stage)
        if stage.event.organizer_id != self.request.user.id:
            raise PermissionDenied("You can assign roles only on stages of your own events.")
        serializer.save()


class AttributeDefinitionViewSet(viewsets.ModelViewSet):
    serializer_class = AttributeDefinitionSerializer
    permission_classes = [IsAuthenticated, IsOrganizer]
    queryset = AttributeDefinition.objects.all().prefetch_related("event_values")

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        if serializer.instance.created_by_id != self.request.user.id:
            raise PermissionDenied("Only the creator can edit an attribute definition.")
        serializer.save()

    def perform_destroy(self, instance):
        if instance.created_by_id != self.request.user.id:
            raise PermissionDenied("Only the creator can delete an attribute definition.")
        if instance.event_values.exists():
            raise ValidationError("An attribute definition used by events cannot be deleted.")
        instance.delete()


class ParticipantRegistrationViewSet(viewsets.ModelViewSet):
    serializer_class = RegistrationSerializer
    permission_classes = [IsAuthenticated, IsParticipant]
    http_method_names = ["get", "head", "options", "delete"]

    def get_queryset(self):
        return Registration.objects.filter(participant=self.request.user).select_related("event", "participant")

    def destroy(self, request, *args, **kwargs):
        registration = self.get_object()
        if registration.status == Registration.Status.CANCELLED:
            raise ValidationError("This registration is already cancelled.")
        if registration.event.starts_at <= timezone.now():
            raise ValidationError("A registration cannot be cancelled after the event has started.")
        registration.status = Registration.Status.CANCELLED
        registration.save(update_fields=["status"])
        return Response(RegistrationSerializer(registration).data, status=status.HTTP_200_OK)


class EventRegistrationView(APIView):
    permission_classes = [IsAuthenticated, IsParticipant]

    def post(self, request, event_id):
        # Locking the event row makes the capacity check and insert atomic on PostgreSQL.
        try:
            with transaction.atomic():
                event = get_object_or_404(Event.objects.select_for_update(), pk=event_id)
                if event.status != Event.Status.PUBLISHED:
                    raise ValidationError("Only published events accept registrations.")
                existing = Registration.objects.filter(event=event, participant=request.user).first()
                if existing and existing.status == Registration.Status.CONFIRMED:
                    raise ValidationError("You are already registered for this event.")
                if event.registrations.filter(status=Registration.Status.CONFIRMED).count() >= event.capacity:
                    raise ValidationError("This event has reached its capacity.")
                if existing and existing.status == Registration.Status.CANCELLED:
                    existing.status = Registration.Status.CONFIRMED
                    existing.registered_at = timezone.now()
                    existing.save(update_fields=["status", "registered_at"])
                    registration = existing
                else:
                    registration = Registration.objects.create(event=event, participant=request.user)
        except IntegrityError:
            raise ValidationError("You are already registered for this event.")
        return Response(RegistrationSerializer(registration).data, status=status.HTTP_201_CREATED)


class EventFeedbackView(APIView):
    permission_classes = [IsAuthenticated, IsParticipant]

    def post(self, request, event_id):
        event = get_object_or_404(Event, pk=event_id)
        if event.status != Event.Status.FINISHED:
            raise ValidationError("Feedback can be submitted only after the event has finished.")
        registration = get_object_or_404(Registration, event=event, participant=request.user, status=Registration.Status.CONFIRMED)
        if Feedback.objects.filter(registration=registration).exists():
            raise ValidationError("Feedback has already been submitted for this event.")
        serializer = FeedbackCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                feedback = serializer.save(registration=registration)
        except IntegrityError:
            raise ValidationError("Feedback has already been submitted for this event.")
        return Response(FeedbackSerializer(feedback).data, status=status.HTTP_201_CREATED)


class PublicEventResultsView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, event_id):
        event = get_object_or_404(Event, pk=event_id, status=Event.Status.FINISHED)
        result = get_object_or_404(EventResult, event=event, is_published=True)
        return Response(EventResultSerializer(result).data)
