from rest_framework.routers import DefaultRouter

from apps.api.views import JobViewSet, SubjectViewSet

router = DefaultRouter()
router.register("subjects", SubjectViewSet, basename="subject")
router.register("jobs", JobViewSet, basename="job")

urlpatterns = router.urls
