from rest_framework.permissions import BasePermission

class IsOrganizer(BasePermission):
    message = "Organizer role is required."
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == "organizer")

class IsParticipant(BasePermission):
    message = "Participant role is required."
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == "participant")
