from .models import CustomerFeedback


def admin_pending_feedback_count(request):
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated or not (user.is_staff or user.is_superuser):
        return {'admin_pending_feedback_count': 0}

    try:
        # Notification badge tracks items that do not yet have an admin reply.
        count = CustomerFeedback.objects.filter(admin_note='').count()
    except Exception:
        # Keep templates safe even during migrations or early setup.
        count = 0

    return {'admin_pending_feedback_count': count}
