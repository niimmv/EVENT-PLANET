from datetime import timedelta
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework import status
from .models import AttributeDefinition, Event, EventAttributeValue, EventResult, Feedback, Registration, Stage, User


class EventPlanetAPITests(APITestCase):
    def setUp(self):
        self.organizer = User.objects.create_user(username="organizer", email="organizer@example.com", password="Strong-pass-123", role=User.Role.ORGANIZER)
        self.other_organizer = User.objects.create_user(username="organizer2", email="organizer2@example.com", password="Strong-pass-123", role=User.Role.ORGANIZER)
        self.participant = User.objects.create_user(username="participant", email="participant@example.com", password="Strong-pass-123", role=User.Role.PARTICIPANT)
        self.event = Event.objects.create(
            title="Django Summit", description="A test event", starts_at=timezone.now() + timedelta(days=3),
            ends_at=timezone.now() + timedelta(days=3, hours=2), capacity=1, organizer=self.organizer,
        )
        self.client.force_authenticate(self.organizer)

    def test_public_registration_cannot_self_assign_organizer_role(self):
        response = self.client.post("/api/auth/register/", {
            "username": "selfpromote", "email": "selfpromote@example.com",
            "password": "Strong-pass-123!", "role": "organizer",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["user"]["role"], User.Role.PARTICIPANT)

    def test_public_list_exposes_only_published_events(self):
        public = Event.objects.create(title="Public", description="Visible", starts_at=timezone.now()+timedelta(days=4), ends_at=timezone.now()+timedelta(days=4, hours=1), capacity=10, organizer=self.organizer, status=Event.Status.PUBLISHED)
        response = self.client.get("/api/public/events/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [item["id"] for item in response.data["results"]]
        self.assertIn(public.id, ids)
        self.assertNotIn(self.event.id, ids)

    def test_organizer_cannot_edit_another_organizers_event(self):
        foreign = Event.objects.create(title="Private", description="No access", starts_at=timezone.now()+timedelta(days=4), ends_at=timezone.now()+timedelta(days=4, hours=1), capacity=10, organizer=self.other_organizer)
        response = self.client.patch(f"/api/organizer/events/{foreign.id}/", {"title": "Tampered"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_lifecycle_rejects_skipping_states(self):
        response = self.client.post(f"/api/organizer/events/{self.event.id}/transition/", {"status": "finished"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response = self.client.post(f"/api/organizer/events/{self.event.id}/transition/", {"status": "published"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.event.refresh_from_db()
        self.assertEqual(self.event.status, Event.Status.PUBLISHED)

    def test_registration_checks_capacity_and_duplicate(self):
        self.event.status = Event.Status.PUBLISHED
        self.event.save(update_fields=["status"])
        self.client.force_authenticate(self.participant)
        first = self.client.post(f"/api/participant/events/{self.event.id}/register/", {}, format="json")
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        second = self.client.post(f"/api/participant/events/{self.event.id}/register/", {}, format="json")
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
        another = User.objects.create_user(username="participant2", email="p2@example.com", password="Strong-pass-123", role=User.Role.PARTICIPANT)
        self.client.force_authenticate(another)
        full = self.client.post(f"/api/participant/events/{self.event.id}/register/", {}, format="json")
        self.assertEqual(full.status_code, status.HTTP_400_BAD_REQUEST)

    def test_participant_can_cancel_registration_before_event_starts(self):
        self.event.status = Event.Status.PUBLISHED
        self.event.save(update_fields=["status"])
        self.client.force_authenticate(self.participant)
        created = self.client.post(f"/api/participant/events/{self.event.id}/register/", {}, format="json")
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        registration_id = created.data["id"]
        cancelled = self.client.delete(f"/api/participant/registrations/{registration_id}/")
        self.assertEqual(cancelled.status_code, status.HTTP_200_OK)
        self.assertEqual(cancelled.data["status"], Registration.Status.CANCELLED)
        another = User.objects.create_user(username="participant3", email="p3@example.com", password="Strong-pass-123", role=User.Role.PARTICIPANT)
        self.client.force_authenticate(another)
        second = self.client.post(f"/api/participant/events/{self.event.id}/register/", {}, format="json")
        self.assertEqual(second.status_code, status.HTTP_201_CREATED)

    def test_dynamic_attributes_are_stored_in_typed_columns(self):
        definition = AttributeDefinition.objects.create(key="difficulty", label="Difficulty", data_type=AttributeDefinition.DataType.INTEGER, created_by=self.organizer)
        response = self.client.post(f"/api/organizer/events/{self.event.id}/attributes/", {"attribute_definition": definition.id, "value": 3}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        value = EventAttributeValue.objects.get(event=self.event, attribute_definition=definition)
        self.assertEqual(value.integer_value, 3)
        self.assertIsNone(value.text_value)
        invalid = self.client.post(f"/api/organizer/events/{self.event.id}/attributes/", {"attribute_definition": definition.id, "value": "three"}, format="json")
        self.assertEqual(invalid.status_code, status.HTTP_400_BAD_REQUEST)

    def test_feedback_requires_finished_event_and_registration(self):
        self.client.force_authenticate(self.participant)
        early = self.client.post(f"/api/participant/events/{self.event.id}/feedback/", {"rating": 5, "comment": "Great"}, format="json")
        self.assertEqual(early.status_code, status.HTTP_400_BAD_REQUEST)
        self.event.status = Event.Status.FINISHED
        self.event.save(update_fields=["status"])
        no_registration = self.client.post(f"/api/participant/events/{self.event.id}/feedback/", {"rating": 5}, format="json")
        self.assertEqual(no_registration.status_code, status.HTTP_404_NOT_FOUND)
        Registration.objects.create(event=self.event, participant=self.participant)
        accepted = self.client.post(f"/api/participant/events/{self.event.id}/feedback/", {"rating": 5, "comment": "Great"}, format="json")
        self.assertEqual(accepted.status_code, status.HTTP_201_CREATED)
        duplicate = self.client.post(f"/api/participant/events/{self.event.id}/feedback/", {"rating": 4}, format="json")
        self.assertEqual(duplicate.status_code, status.HTTP_400_BAD_REQUEST)

    def test_results_are_not_public_until_finished_and_published(self):
        EventResult.objects.create(event=self.event, title="Results", content="Winners", is_published=False)
        response = self.client.get(f"/api/public/events/{self.event.id}/results/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.event.status = Event.Status.FINISHED
        self.event.save(update_fields=["status"])
        response = self.client.get(f"/api/public/events/{self.event.id}/results/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        result = self.event.result
        result.is_published = True
        result.save(update_fields=["is_published"])
        response = self.client.get(f"/api/public/events/{self.event.id}/results/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_stage_order_is_unique_per_event(self):
        now = timezone.now()
        Stage.objects.create(event=self.event, title="First", order=1, starts_at=now+timedelta(days=3), ends_at=now+timedelta(days=3, minutes=30))
        response = self.client.post(f"/api/organizer/events/{self.event.id}/stages/", {"title": "Duplicate order", "order": 1, "starts_at": (now+timedelta(days=3)).isoformat(), "ends_at": (now+timedelta(days=3, minutes=30)).isoformat()}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
