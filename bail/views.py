from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
import logging
from algo.encadrement_loyer.ile_de_france.main_2 import ile_de_france
logger = logging.getLogger(__name__)

@csrf_exempt
def check_zone(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            address = data.get("address", "")

            logger.info(f"🔍 Adresse reçue : {address}")

            if not address:
                return JsonResponse({"message": "Adresse requise"}, status=400)

            # Ici, on appelle une fonction existante `is_critical_zone(address)`
            is_critical = ile_de_france(address)

            if is_critical:
                return JsonResponse({"message": "⚠️ Cette adresse est dans une zone critique."})
            else:
                return JsonResponse({"message": "✅ Cette adresse est sûre."})

        except Exception as e:
            logger.error(f"❌ Erreur Django: {str(e)}")
            return JsonResponse({"message": f"Erreur: {str(e)}"}, status=500)

    return JsonResponse({"message": "Méthode non autorisée"}, status=405)