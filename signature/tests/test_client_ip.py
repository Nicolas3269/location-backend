"""
Tests pour la récupération de l'IP réelle du client (reverse proxy support).
"""
import pytest
from django.test import RequestFactory

from signature.certification_flow import get_client_ip


class TestGetClientIP:
    """Tests pour get_client_ip() avec différents headers de proxy."""

    def setup_method(self):
        self.factory = RequestFactory()

    def test_x_forwarded_for_single_ip(self):
        """X-Forwarded-For avec une seule IP (cas simple)."""
        request = self.factory.get("/", HTTP_X_FORWARDED_FOR="203.0.113.42")
        assert get_client_ip(request) == "203.0.113.42"

    def test_x_forwarded_for_multiple_ips(self):
        """X-Forwarded-For avec plusieurs IPs (client + proxies)."""
        request = self.factory.get(
            "/", HTTP_X_FORWARDED_FOR="203.0.113.42, 198.51.100.1, 192.0.2.1"
        )
        # Doit retourner la PREMIÈRE IP (client réel)
        assert get_client_ip(request) == "203.0.113.42"

    def test_x_forwarded_for_with_spaces(self):
        """X-Forwarded-For avec espaces autour des IPs."""
        request = self.factory.get(
            "/", HTTP_X_FORWARDED_FOR="  203.0.113.42  , 198.51.100.1  "
        )
        # Doit strip les espaces
        assert get_client_ip(request) == "203.0.113.42"

    def test_x_real_ip(self):
        """X-Real-IP (nginx, certains proxies)."""
        request = self.factory.get("/", HTTP_X_REAL_IP="203.0.113.42")
        assert get_client_ip(request) == "203.0.113.42"

    def test_x_forwarded_for_priority(self):
        """X-Forwarded-For a priorité sur X-Real-IP."""
        request = self.factory.get(
            "/",
            HTTP_X_FORWARDED_FOR="203.0.113.42",
            HTTP_X_REAL_IP="198.51.100.1",
        )
        # X-Forwarded-For doit être utilisé en priorité
        assert get_client_ip(request) == "203.0.113.42"

    def test_remote_addr_fallback(self):
        """Fallback sur REMOTE_ADDR si pas de headers de proxy."""
        request = self.factory.get("/")
        # REMOTE_ADDR est ajouté automatiquement par Django
        # En test, c'est généralement '127.0.0.1'
        result = get_client_ip(request)
        assert result in ["127.0.0.1", "0.0.0.0"]  # Selon environnement

    def test_no_request(self):
        """Gestion du cas où request est None."""
        assert get_client_ip(None) == "0.0.0.0"

    def test_railway_production_scenario(self):
        """Scénario réel Railway : X-Forwarded-For avec IP client + proxy."""
        request = self.factory.get(
            "/",
            HTTP_X_FORWARDED_FOR="81.56.123.45, 100.64.0.7",
            REMOTE_ADDR="100.64.0.7",
        )
        # Doit retourner l'IP du client (81.56.123.45), pas celle du proxy Railway
        assert get_client_ip(request) == "81.56.123.45"

    def test_ipv6_support(self):
        """Support des adresses IPv6."""
        request = self.factory.get(
            "/", HTTP_X_FORWARDED_FOR="2001:0db8:85a3:0000:0000:8a2e:0370:7334"
        )
        assert get_client_ip(request) == "2001:0db8:85a3:0000:0000:8a2e:0370:7334"

    def test_ipv6_abbreviated(self):
        """Support des adresses IPv6 abrégées."""
        request = self.factory.get("/", HTTP_X_FORWARDED_FOR="2001:db8::1")
        assert get_client_ip(request) == "2001:db8::1"
