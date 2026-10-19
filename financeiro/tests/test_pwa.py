import json

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse


class PwaPublicAssetsTests(SimpleTestCase):
    def test_manifesto_tem_metadados_e_atalhos_instalaveis(self):
        response = self.client.get(reverse("pwa_manifest"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/manifest+json")
        manifest = json.loads(response.content)
        self.assertEqual(manifest["name"], "myAppFinanceiro")
        self.assertEqual(manifest["display"], "standalone")
        self.assertEqual(manifest["scope"], "/")
        self.assertEqual({icon["sizes"] for icon in manifest["icons"]}, {"192x192", "512x512"})
        self.assertEqual(len(manifest["shortcuts"]), 3)

    def test_service_worker_tem_escopo_raiz_e_nao_armazena_navegacao(self):
        response = self.client.get(reverse("pwa_service_worker"))
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("application/javascript"))
        self.assertEqual(response["Service-Worker-Allowed"], "/")
        self.assertIn('request.method !== "GET"', content)
        self.assertIn('request.mode === "navigate"', content)
        self.assertIn("fetch(request).catch", content)
        self.assertNotIn("cache.put(request", content)

    def test_icones_publicos_tem_tamanho_png_valido(self):
        for size in (180, 192, 512):
            with self.subTest(size=size):
                response = self.client.get(reverse("pwa_icon", kwargs={"size": size}))
                content = b"".join(response.streaming_content)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response["Content-Type"], "image/png")
                self.assertEqual(content[:8], b"\x89PNG\r\n\x1a\n")
                self.assertEqual(int.from_bytes(content[16:20], "big"), size)
                self.assertEqual(int.from_bytes(content[20:24], "big"), size)

    def test_tamanho_de_icone_inexistente_retorna_404(self):
        response = self.client.get(reverse("pwa_icon", kwargs={"size": 256}))
        self.assertEqual(response.status_code, 404)

    def test_pagina_offline_e_login_registram_a_pwa(self):
        offline = self.client.get(reverse("pwa_offline"))
        login = self.client.get(reverse("login"))

        self.assertContains(offline, "Tailscale está conectado")
        self.assertContains(offline, reverse("pwa_manifest"))
        self.assertContains(offline, reverse("pwa_service_worker"))
        self.assertContains(login, reverse("pwa_manifest"))
        self.assertContains(login, reverse("pwa_service_worker"))


class PwaAuthenticatedTemplateTests(TestCase):
    def test_layout_autenticado_registra_pwa_e_oferece_instalacao(self):
        user = get_user_model().objects.create_user(username="pwa", password="senha")
        self.client.force_login(user)

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("pwa_manifest"))
        self.assertContains(response, reverse("pwa_service_worker"))
        self.assertContains(response, "data-pwa-install")
