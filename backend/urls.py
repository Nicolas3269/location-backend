"""
URL configuration for backend project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.conf import settings

# urls.py
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve
from .pdf_views import serve_pdf_for_iframe

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/rent_control/", include("rent_control.urls")),
    path("api/", include("bail.urls")),
    path("api/auth/", include("authentication.urls")),
    path("api/notifications/", include("notifications.urls")),
    # Nouvelle route pour servir les PDFs en iframe sans X-Frame-Options
    path("pdf/<path:file_path>", serve_pdf_for_iframe, name="serve_pdf_iframe"),
]

# Ajouter ceci pour servir les fichiers médias en développement
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
else:
    # In production, you should serve media files using a web server like Nginx or Apache
    urlpatterns += [
        re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
    ]
