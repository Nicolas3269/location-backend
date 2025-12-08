"""
Client d'authentification pour l'API Mila.

Gère l'obtention et le refresh automatique des tokens JWT.
"""

import logging
import time
from dataclasses import dataclass

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class MilaAuthError(Exception):
    """Erreur d'authentification Mila."""

    pass


class MilaConfigurationError(Exception):
    """Erreur de configuration Mila (credentials manquants)."""

    pass


@dataclass
class MilaToken:
    """Token JWT Mila avec expiration."""

    jwt_token: str
    expires_at: float  # timestamp

    @property
    def is_expired(self) -> bool:
        """Vérifie si le token est expiré (avec 60s de marge)."""
        return time.time() >= (self.expires_at - 60)


class MilaAuthClient:
    """
    Client d'authentification pour l'API Mila.

    Gère automatiquement le refresh des tokens JWT.

    Usage:
        auth = MilaAuthClient()
        token = auth.get_token()
        headers = {"Authorization": f"Bearer {token}"}
    """

    AUTH_ENDPOINT = "/auth/brk/v1/login"

    def __init__(
        self,
        base_url: str | None = None,
        username: str | None = None,
        password: str | None = None,
    ):
        """
        Initialise le client d'authentification.

        Args:
            base_url: URL de base de l'API (défaut: settings.MILA_API_URL)
            username: Identifiant API (défaut: settings.MILA_API_USERNAME)
            password: Mot de passe API (défaut: settings.MILA_API_PASSWORD)
        """
        self.base_url = (base_url or settings.MILA_API_URL or "").rstrip("/")
        self.username = username or settings.MILA_API_USERNAME
        self.password = password or settings.MILA_API_PASSWORD

        self._token: MilaToken | None = None
        self._session: requests.Session | None = None

    def _validate_config(self) -> None:
        """Valide que la configuration est complète."""
        missing = []
        if not self.base_url:
            missing.append("MILA_API_URL")
        if not self.username:
            missing.append("MILA_API_USERNAME")
        if not self.password:
            missing.append("MILA_API_PASSWORD")

        if missing:
            raise MilaConfigurationError(
                f"Configuration Mila incomplète. Variables manquantes: {', '.join(missing)}"
            )

    @property
    def session(self) -> requests.Session:
        """Session HTTP réutilisable."""
        if self._session is None:
            self._session = requests.Session()
            self._session.headers.update({"Content-Type": "application/json"})
        return self._session

    def _fetch_token(self) -> MilaToken:
        """Récupère un nouveau token depuis l'API."""
        self._validate_config()

        logger.debug("Fetching new Mila JWT token")

        url = f"{self.base_url}{self.AUTH_ENDPOINT}"

        try:
            response = self.session.post(
                url,
                json={"username": self.username, "password": self.password},
                timeout=30,
            )
            response.raise_for_status()
        except requests.HTTPError as e:
            logger.error(f"Mila auth failed: {e.response.status_code}")
            raise MilaAuthError(
                f"Authentification Mila échouée: {e.response.status_code}"
            ) from e
        except requests.RequestException as e:
            logger.error(f"Mila auth request failed: {e}")
            raise MilaAuthError(f"Erreur de connexion à Mila: {e}") from e

        data = response.json()
        jwt_token = data.get("jwt_token")
        expiration_delay = data.get("jwt_token_expiration_delay_seconds", 3600)

        if not jwt_token:
            raise MilaAuthError("Réponse Mila invalide: jwt_token manquant")

        return MilaToken(
            jwt_token=jwt_token,
            expires_at=time.time() + expiration_delay,
        )

    def get_token(self) -> str:
        """
        Retourne un token JWT valide.

        Le token est mis en cache et renouvelé automatiquement avant expiration.

        Returns:
            Token JWT valide

        Raises:
            MilaAuthError: Si l'authentification échoue
            MilaConfigurationError: Si les credentials sont manquants
        """
        if self._token is None or self._token.is_expired:
            self._token = self._fetch_token()
            logger.debug("Mila token refreshed")

        return self._token.jwt_token

    def get_auth_headers(self) -> dict[str, str]:
        """Retourne les headers d'authentification."""
        return {"Authorization": f"Bearer {self.get_token()}"}

    def invalidate_token(self) -> None:
        """Force le refresh du token au prochain appel."""
        self._token = None

    def close(self) -> None:
        """Ferme la session HTTP."""
        if self._session:
            self._session.close()
            self._session = None

    def __enter__(self) -> "MilaAuthClient":
        return self

    def __exit__(self, *args) -> None:
        self.close()
