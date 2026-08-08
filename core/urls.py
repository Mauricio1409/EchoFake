from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('apps.api.urls')),
    path('', TemplateView.as_view(template_name='api/home.html', extra_context={'active': 'home'}), name='home'),
    path('nuevo/', TemplateView.as_view(template_name='api/create-choice.html', extra_context={'active': 'create'}), name='create'),
    path('nuevo/manual/', TemplateView.as_view(template_name='api/create-manual.html', extra_context={'active': 'create'}), name='create-manual'),
    path('nuevo/automatico/', TemplateView.as_view(template_name='api/create-auto.html', extra_context={'active': 'create'}), name='create-auto'),
    path('sujetos/', TemplateView.as_view(template_name='api/list.html', extra_context={'active': 'list'}), name='subject-list'),
    path('como-funciona/', TemplateView.as_view(template_name='api/how-it-works.html', extra_context={'active': 'how'}), name='how-it-works'),
    path('panel/<uuid:subject_id>/', TemplateView.as_view(template_name='api/panel.html'), name='panel'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
