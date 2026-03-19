"""
URL configuration for bingo_project project.

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
from django.contrib import admin
from django.http import HttpResponse
from django.urls import path, include
from django.contrib.staticfiles.urls import staticfiles_urlpatterns


def favicon(_request):
    svg = (
        "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"64\" height=\"64\" viewBox=\"0 0 64 64\">"
        "<rect width=\"64\" height=\"64\" rx=\"12\" fill=\"#667eea\"/>"
        "<text x=\"32\" y=\"41\" font-size=\"32\" text-anchor=\"middle\" fill=\"#ffffff\" "
        "font-family=\"Arial, sans-serif\">B</text>"
        "</svg>"
    )
    response = HttpResponse(svg, content_type="image/svg+xml")
    response["Cache-Control"] = "public, max-age=86400"
    return response


def index(_request):
    return HttpResponse("Bingo backend is running", content_type="text/plain")


def healthz(_request):
    return HttpResponse("ok", content_type="text/plain")

urlpatterns = [
    path("", index, name="index"),
    path("healthz", healthz, name="healthz"),
    path("favicon.ico", favicon, name="favicon"),
    path("admin/", admin.site.urls),
    path("game/", include('game.urls')),
]

# Safety fallback: serve static assets through Django URL patterns if middleware-based
# static serving is unavailable in the current deployment configuration.
urlpatterns += staticfiles_urlpatterns()
