from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.cache import cache_control, never_cache
from django.views.decorators.http import require_GET


PWA_ASSETS_DIR = Path(settings.BASE_DIR) / "pwa"
PWA_ICON_SIZES = {180, 192, 512}


@require_GET
@cache_control(public=True, max_age=3600)
def webmanifest(request):
    manifest = {
        "id": "/",
        "name": "myAppFinanceiro",
        "short_name": "Financeiro",
        "description": "Finanças pessoais e profissionais.",
        "lang": "pt-BR",
        "start_url": "/?source=pwa",
        "scope": "/",
        "display": "standalone",
        "background_color": "#f3f6fa",
        "theme_color": "#102747",
        "categories": ["finance", "business", "productivity"],
        "icons": [
            {
                "src": reverse("pwa_icon", kwargs={"size": 192}),
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any maskable",
            },
            {
                "src": reverse("pwa_icon", kwargs={"size": 512}),
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any maskable",
            },
        ],
        "shortcuts": [
            {
                "name": "Novo lançamento",
                "short_name": "Novo",
                "url": reverse("evento_novo"),
            },
            {
                "name": "Lançamentos",
                "short_name": "Lançamentos",
                "url": reverse("eventos"),
            },
            {
                "name": "Cartões e faturas",
                "short_name": "Faturas",
                "url": reverse("cartoes_faturas"),
            },
        ],
    }
    return JsonResponse(
        manifest,
        content_type="application/manifest+json",
        json_dumps_params={"ensure_ascii": False},
    )


@require_GET
@cache_control(public=True, max_age=604800, immutable=True)
def icon(request, size):
    if size not in PWA_ICON_SIZES:
        raise Http404("Ícone da PWA não encontrado.")
    return FileResponse(
        (PWA_ASSETS_DIR / f"icon-{size}.png").open("rb"),
        content_type="image/png",
    )


@require_GET
@never_cache
def service_worker(request):
    response = HttpResponse(
        (PWA_ASSETS_DIR / "service-worker.js").read_text(encoding="utf-8"),
        content_type="application/javascript; charset=utf-8",
    )
    response["Service-Worker-Allowed"] = "/"
    return response


@require_GET
def offline(request):
    return render(request, "pwa/offline.html")
