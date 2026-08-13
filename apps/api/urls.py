from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.api.auth_views import LoginView, LogoutView, RefreshView
from apps.api.views import JobViewSet, SubjectViewSet

router = DefaultRouter()
router.register("subjects", SubjectViewSet, basename="subject")
router.register("jobs", JobViewSet, basename="job")

urlpatterns = [
    path("auth/login/", LoginView.as_view(), name="auth-login"),
    path("auth/logout/", LogoutView.as_view(), name="auth-logout"),
    path("auth/refresh/", RefreshView.as_view(), name="auth-refresh"),
] + router.urls
