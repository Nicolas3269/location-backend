"""
Tests unitaires pour le workflow PrefillFormState depuis un bien existant.

Ce test simule exactement le workflow frontend:
1. Frontend appelle GET /api/location/forms/bail/requirements/authenticated/ avec from_bien
2. Backend retourne prefill_data + bien_id + bailleur_id
3. Frontend soumet le formulaire avec bien_id/bailleur_id pour réutiliser les entités
4. Backend vérifie que le bien et bailleur sont réutilisés (pas de doublon)

Usage:
    pytest tests/test_prefill_from_bien.py -v
    pytest tests/test_prefill_from_bien.py::test_prefill_from_bien_returns_correct_data -v
"""

import pytest
from rest_framework.test import APIClient
from location.factories import BienFactory
from location.models import Bien, Bailleur, Location


@pytest.fixture
def auth_client(settings, django_user_model):
    """Client API authentifié configuré pour les tests."""
    settings.ALLOWED_HOSTS = ["localhost", "testserver"]
    settings.SECURE_SSL_REDIRECT = False  # Disable SSL redirect in tests
    user = django_user_model.objects.create_user(username="test", email="test@example.com", password="test")
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.mark.django_db
class TestPrefillFromBien:
    """Tests pour le workflow PrefillFormState depuis bien."""

    def test_prefill_from_bien_returns_correct_data(self, auth_client):
        """Test que l'API retourne les bonnes données de prefill depuis un bien."""
        # 1. Créer un bien avec un bailleur
        bien = BienFactory(
            adresse__voie="Rue Eugénie Eboué",
            adresse__numero="12",
            adresse__code_postal="75012",
            adresse__ville="Paris",
            adresse__latitude=48.8566,
            adresse__longitude=2.3522,
            type_bien="appartement",
            superficie=45.5,
            meuble=False,
            bailleurs__count=1
        )
        bailleur = bien.bailleurs.first()

        # 2. Appeler l'API comme le fait le frontend
        response = auth_client.get(
            "/api/location/forms/bail/requirements/authenticated/",
            {
                "country": "france",
                "context_mode": "from_bien",
                "context_source_id": str(bien.id),
            },
            follow=True  # Suivre les redirections
        )

        # 3. Vérifier la réponse
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()

        # Vérifier la structure de la réponse
        assert "prefill_data" in data, "prefill_data manquant dans la réponse"
        assert "bien_id" in data, "bien_id manquant dans la réponse"
        assert "bailleur_id" in data, "bailleur_id manquant dans la réponse"
        assert "formData" in data, "formData manquant dans la réponse"
        assert "location_id" in data["formData"], "location_id manquant dans formData"
        assert "locked_steps" in data, "locked_steps manquant dans la réponse"

        # Vérifier que les IDs sont corrects
        assert data["bien_id"] == str(bien.id), f"Expected bien_id={bien.id}, got {data['bien_id']}"
        assert data["bailleur_id"] == str(bailleur.id), f"Expected bailleur_id={bailleur.id}, got {data['bailleur_id']}"

        # Vérifier que prefill_data contient l'adresse
        prefill = data["prefill_data"]
        assert "bien" in prefill, "bien manquant dans prefill_data"
        assert "localisation" in prefill["bien"], "localisation manquant dans prefill_data.bien"
        assert "adresse" in prefill["bien"]["localisation"], "adresse manquant dans prefill_data.bien.localisation"
        # L'adresse dans prefill est maintenant un objet structuré
        assert "ville" in prefill["bien"]["localisation"]["adresse"], \
            f"ville manquant dans adresse: {prefill['bien']['localisation']['adresse']}"
        assert prefill["bien"]["localisation"]["adresse"]["ville"] == bien.adresse.ville, \
            f"Expected ville={bien.adresse.ville}, got {prefill['bien']['localisation']['adresse']['ville']}"

        # Vérifier les locked_steps
        locked_steps = set(data["locked_steps"])

        # L'adresse DOIT être lockée
        assert "bien.localisation.adresse" in locked_steps, \
            "L'adresse devrait être lockée depuis un bien existant"

        # Le type de bien DOIT être locké
        assert "bien.caracteristiques.type_bien" in locked_steps, \
            "Le type de bien devrait être locké depuis un bien existant"

        # La superficie NE DOIT PAS être lockée (unlocked_from_bien=True)
        assert "bien.caracteristiques.superficie" not in locked_steps, \
            "La superficie ne devrait PAS être lockée (unlocked_from_bien=True)"

        # Le meublé NE DOIT PAS être locké (unlocked_from_bien=True)
        assert "bien.caracteristiques.meuble" not in locked_steps, \
            "Le meublé ne devrait PAS être locké (unlocked_from_bien=True)"

        print("\n✅ Test passed: prefill_data structure correcte")
        print(f"   - bien_id: {data['bien_id']}")
        print(f"   - bailleur_id: {data['bailleur_id']}")
        print(f"   - adresse dans prefill: {prefill['bien']['localisation']['adresse']}")
        print(f"   - locked_steps: {len(locked_steps)} steps")
        print(f"   - adresse lockée: {'bien.localisation.adresse' in locked_steps}")
        print(f"   - superficie lockée: {'bien.caracteristiques.superficie' in locked_steps}")

    def test_bien_is_reused_not_duplicated(self, auth_client):
        """Test que le bien est réutilisé et non dupliqué lors de la soumission."""
        # 1. Créer un bien
        bien = BienFactory(
            adresse="12 Rue de la Paix, 75002 Paris",
            bailleurs__count=1
        )
        bailleur = bien.bailleurs.first()
        bien_count_before = Bien.objects.count()

        # 2. Récupérer les requirements
        response = auth_client.get(
            "/api/location/forms/bail/requirements/authenticated/",
            {
                "country": "france",
                "context_mode": "from_bien",
                "context_source_id": str(bien.id),
            },
            follow=True
        )
        data = response.json()

        # 3. Soumettre le formulaire avec bien_id
        # Note: Même avec bien_id, le serializer valide les champs requis
        # Mais le backend utilisera le bien_id pour réutiliser les données existantes
        payload = {
            "source": "bail",
            "country": "france",
            "bien_id": data["bien_id"],  # IMPORTANT: Réutiliser le bien
            "bailleur_id": data["bailleur_id"],  # IMPORTANT: Réutiliser le bailleur
            "location_id": data["formData"]["location_id"],

            # Bien (champs requis pour validation, mais bien_id sera utilisé)
            "bien": {
                "localisation": {
                    "adresse": str(bien.adresse),  # Adresse formatée (locked)
                },
                "caracteristiques": {
                    "type_bien": "appartement",
                    "superficie": 50.0,  # Modifiable (unlocked_from_bien)
                    "meuble": True,  # Modifiable (unlocked_from_bien)
                },
                "regime": {"regime_juridique": "monopropriete"},
                "equipements": {
                    "loi_alur": {},
                },
                "energie": {},
                "performance_energetique": {},
            },

            # Bailleur (requis pour validation, mais bailleur_id sera utilisé)
            "bailleur": {
                "bailleur_type": "physique",
                "personne": {
                    "firstName": "Test",
                    "lastName": "Bailleur",
                    "email": "bailleur@example.com",  # Email valide pour validation
                    "adresse": "1 Rue Test",
                }
            },

            # Locataires
            "locataires": [
                {
                    "firstName": "Marie",
                    "lastName": "Dupont",
                    "email": "marie.dupont@example.com",
                    "date_naissance": "1990-01-01",
                    "adresse": "10 Avenue Test, 75001 Paris",
                }
            ],
            "solidaires": False,

            # Modalités financières
            "modalites_financieres": {
                "loyer_hors_charges": 1200.0,
                "charges": 150.0,
                "type_charges": "provisionnelles",
            },

            # Dates
            "dates": {
                "date_debut": "2024-01-01",
            },
        }

        response = auth_client.post(
            "/api/location/create-or-update/",
            data=payload,
            format="json"
        )

        # Debug response
        print(f"\n🔍 POST Response status: {response.status_code}")
        if response.status_code != 201:
            print(f"🔍 Response content: {response.content.decode()}")
            print(f"🔍 Response headers: {dict(response.headers)}")

        # 4. Vérifier que le bien n'a PAS été dupliqué
        bien_count_after = Bien.objects.count()
        assert bien_count_after == bien_count_before, \
            f"Un nouveau bien a été créé! Before: {bien_count_before}, After: {bien_count_after}"

        # 5. Vérifier que c'est le même bien
        if response.status_code == 200:
            result = response.json()
            assert result["success"], f"Expected success=true, got {result}"

            location = Location.objects.get(id=result["location_id"])
            assert location.bien.id == bien.id, \
                f"Le bien n'est pas le même! Expected: {bien.id}, Got: {location.bien.id}"

            print("\n✅ Test passed: bien réutilisé correctement")
            print(f"   - Bien original: {bien.id}")
            print(f"   - Bien dans location: {location.bien.id}")
            print(f"   - Nombre de biens: {bien_count_after}")
        else:
            print(f"\n❌ Submission failed with status {response.status_code}")
            print(f"Response: {response.content.decode()}")
            pytest.fail(f"Submission failed: {response.status_code}")

    def test_bailleur_is_reused_not_duplicated(self, auth_client):
        """Test que le bailleur est réutilisé et non dupliqué."""
        # 1. Créer un bien avec bailleur
        bien = BienFactory(bailleurs__count=1)
        bailleur = bien.bailleurs.first()
        bailleur_count_before = Bailleur.objects.count()

        # 2. Récupérer requirements
        response = auth_client.get(
            "/api/location/forms/bail/requirements/authenticated/",
            {
                "country": "france",
                "context_mode": "from_bien",
                "context_source_id": str(bien.id),
            },
            follow=True
        )
        data = response.json()

        # 3. Soumettre avec bailleur_id
        payload = {
            "source": "bail",
            "country": "france",
            "bien_id": data["bien_id"],
            "bailleur_id": data["bailleur_id"],  # IMPORTANT
            "location_id": data["formData"]["location_id"],
            "bien": {
                "localisation": {"adresse": str(bien.adresse)},
                "caracteristiques": {
                    "type_bien": "appartement",
                    "superficie": 50.0,
                },
                "regime": {"regime_juridique": "monopropriete"},
                "equipements": {"loi_alur": {}},
                "energie": {},
                "performance_energetique": {},
            },
            "bailleur": {
                "bailleur_type": "physique",
                "personne": {
                    "firstName": "Test",
                    "lastName": "Bailleur",
                    "email": "bailleur@example.com",
                    "adresse": "1 Rue Test",
                }
            },
            "locataires": [{
                "firstName": "Test",
                "lastName": "User",
                "email": "test@example.com",
                "date_naissance": "1990-01-01",
                "adresse": "10 Avenue Test, 75001 Paris",
            }],
            "solidaires": False,
            "modalites_financieres": {
                "loyer_hors_charges": 1000.0,
                "charges": 100.0,
                "type_charges": "provisionnelles",
            },
            "dates": {"date_debut": "2024-01-01"},
        }

        response = auth_client.post(
            "/api/location/create-or-update/",
            data=payload,
            format="json"
        )

        # Debug response
        print(f"\n🔍 POST Response status: {response.status_code}")
        if response.status_code != 201:
            print(f"🔍 Response content: {response.content.decode()}")

        # 4. Vérifier qu'aucun nouveau bailleur n'a été créé
        bailleur_count_after = Bailleur.objects.count()
        assert bailleur_count_after == bailleur_count_before, \
            f"Un nouveau bailleur a été créé! Before: {bailleur_count_before}, After: {bailleur_count_after}"

        if response.status_code == 200:
            result = response.json()
            assert result["success"], f"Expected success=true, got {result}"

            location = Location.objects.get(id=result["location_id"])

            # Vérifier que c'est le même bailleur
            assert location.bien.bailleurs.filter(id=bailleur.id).exists(), \
                "Le bailleur original n'est pas lié au bien!"

            print("\n✅ Test passed: bailleur réutilisé correctement")
            print(f"   - Bailleur original: {bailleur.id}")
            print(f"   - Nombre de bailleurs: {bailleur_count_after}")
        else:
            print(f"\n❌ Submission failed: {response.status_code}")
            print(f"Response: {response.content.decode()}")
            pytest.fail(f"Submission failed: {response.status_code}")

    def test_locked_fields_not_in_prefill_data(self, auth_client):
        """Test que les champs lockés sont bien dans prefill_data mais cachés côté frontend."""
        # 1. Créer un bien
        bien = BienFactory(
            adresse="123 Test Street, Paris",
            type_bien="appartement",
            periode_construction="avant 1946",
        )

        # 2. Récupérer requirements
        response = auth_client.get(
            "/api/location/forms/bail/requirements/authenticated/",
            {
                "country": "france",
                "context_mode": "from_bien",
                "context_source_id": str(bien.id),
            },
            follow=True
        )
        data = response.json()
        prefill = data["prefill_data"]
        locked_steps = set(data["locked_steps"])

        # 3. Vérifier que les champs lockés SONT dans prefill_data
        assert "ville" in prefill["bien"]["localisation"]["adresse"], \
            "L'adresse devrait être dans prefill_data"

        # 4. Vérifier que ces champs SONT dans locked_steps
        assert "bien.localisation.adresse" in locked_steps, \
            "L'adresse devrait être dans locked_steps"

        assert "bien.caracteristiques.type_bien" in locked_steps, \
            "Le type de bien devrait être dans locked_steps"

        # 5. Les champs unlocked_from_bien NE DOIVENT PAS être lockés
        assert "bien.caracteristiques.superficie" not in locked_steps, \
            "La superficie ne devrait pas être lockée"

        print("\n✅ Test passed: locked fields correct")
        print(f"   - Adresse dans prefill: ✓")
        print(f"   - Adresse lockée: ✓")
        print(f"   - Type bien locké: ✓")
        print(f"   - Superficie unlocked: ✓")


@pytest.mark.django_db
class TestDebugAdresseReset:
    """Tests pour comprendre pourquoi l'adresse est reset."""

    def test_debug_adresse_in_response(self, settings, django_user_model):
        """Debug: Afficher tout le contenu de la réponse pour comprendre."""
        # 0. Configure ALLOWED_HOSTS
        settings.ALLOWED_HOSTS = ["localhost", "testserver"]
        settings.SECURE_SSL_REDIRECT = False  # Disable SSL redirect in tests

        # 1. Créer un utilisateur et authentifier
        user = django_user_model.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123"
        )

        # 2. Créer un bien
        bien = BienFactory(
            adresse="12 Rue Eugénie Eboué, 75012 Paris, France",
            type_bien="appartement",
        )

        # 3. Appeler l'API avec authentification
        client = APIClient()
        client.force_authenticate(user=user)
        response = client.get(
            "/api/location/forms/bail/requirements/authenticated/",
            {
                "country": "france",
                "context_mode": "from_bien",
                "context_source_id": str(bien.id),
            },
            follow=True
        )

        # Debug: afficher le statut
        print(f"\n🔍 Response status: {response.status_code}")
        print(f"🔍 Content-Type: {response.get('Content-Type')}")

        if response.status_code != 200:
            print(f"❌ Error: {response.content[:1000].decode()}")
            pytest.fail(f"API returned {response.status_code}")

        data = response.json()

        # 3. Afficher TOUT pour debug
        print("\n" + "="*80)
        print("DEBUG: Réponse complète de l'API")
        print("="*80)

        print(f"\n📋 Structure de la réponse:")
        print(f"   - Keys: {list(data.keys())}")

        print(f"\n🏠 bien_id: {data.get('bien_id')}")
        print(f"👤 bailleur_id: {data.get('bailleur_id')}")
        print(f"📍 location_id: {data.get('location_id')}")

        print(f"\n🔒 locked_steps ({len(data.get('locked_steps', []))}):")
        for step in sorted(data.get("locked_steps", [])):
            print(f"   - {step}")

        print(f"\n📝 prefill_data:")
        prefill = data.get("prefill_data", {})

        if "bien" in prefill:
            print(f"   bien: {list(prefill['bien'].keys())}")

            if "localisation" in prefill["bien"]:
                print(f"   bien.localisation:")
                for key, value in prefill["bien"]["localisation"].items():
                    print(f"      - {key}: {value}")

            if "caracteristiques" in prefill["bien"]:
                print(f"   bien.caracteristiques:")
                for key, value in prefill["bien"]["caracteristiques"].items():
                    print(f"      - {key}: {value}")

        if "bailleur" in prefill:
            print(f"   bailleur: {list(prefill['bailleur'].keys())}")

        print("\n" + "="*80)

        # 4. Vérifications critiques
        assert data.get("bien_id") == str(bien.id), "bien_id incorrect"
        assert "adresse" in prefill.get("bien", {}).get("localisation", {}), \
            "❌ PROBLÈME: adresse manquante dans prefill_data!"
        assert "ville" in prefill["bien"]["localisation"]["adresse"], \
            "❌ PROBLÈME: adresse incorrecte dans prefill_data!"

        print("\n✅ Adresse présente dans prefill_data")
