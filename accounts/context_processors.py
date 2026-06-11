from django.contrib.auth import get_user_model


def pending_users(request):
    if request.user.is_authenticated and request.user.is_staff:
        count = get_user_model().objects.filter(is_active=False).count()
        return {'pending_users_count': count}
    return {'pending_users_count': 0}
