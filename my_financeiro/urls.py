from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from . import pwa


urlpatterns = [
    path("manifest.webmanifest", pwa.webmanifest, name="pwa_manifest"),
    path("service-worker.js", pwa.service_worker, name="pwa_service_worker"),
    path("offline/", pwa.offline, name="pwa_offline"),
    path("pwa/icon-<int:size>.png", pwa.icon, name="pwa_icon"),
    path("admin/", admin.site.urls),
    path(
        "accounts/login/",
        auth_views.LoginView.as_view(template_name="registration/login.html"),
        name="login",
    ),
    path(
        "accounts/logout/",
        auth_views.LogoutView.as_view(next_page="login"),
        name="logout",
    ),
    path("", include("financeiro.urls")),
]
