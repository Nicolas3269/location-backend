"""
Sujets d'email standardisés pour tous les templates MJML.

Usage:
    from core.email_subjects import EMAIL_SUBJECTS
    subject = EMAIL_SUBJECTS.get('bailleur/bail/demande_signature')
"""

EMAIL_SUBJECTS = {
    # === AUTH ===
    "auth/verification_otp": "Vérifiez votre adresse email",
    # === COMMON ===
    "common/otp_signature": "Code de vérification pour votre signature",
    "common/post_signature": "Votre signature est bien enregistrée",
    "common/annulation_signature": "La procédure de signature {document_type} a été annulée",
    "common/edl_en_cours_signature": "L'état des lieux est en attente de signature",
    # === BAILLEUR BAIL ===
    "bailleur/bail/demande_signature": "Votre signature est requise pour le bail",
    "bailleur/bail/relance_j1": "Petit rappel : votre signature est attendue",
    "bailleur/bail/relance_j3": "N'oubliez pas de signer votre bail",
    "bailleur/bail/relance_j7": "Dernier rappel : signez votre bail aujourd'hui",
    "bailleur/bail/bail_signe": "Votre bail est maintenant signé par toutes les parties",
    # === BAILLEUR EDL ===
    "bailleur/edl/demande_signature": "Votre signature est requise pour l'état des lieux",
    "bailleur/edl/relance_j1": "Votre état des lieux est prêt à être complété",
    "bailleur/edl/relance_j2": "Un état des lieux clair, une location sans souci",
    "bailleur/edl/relance_j3": "Dernier rappel - complétez votre état des lieux",
    "bailleur/edl/signe": "Votre état des lieux est signé et disponible",
    # === BAILLEUR AVENANT ===
    "bailleur/avenant/demande_signature": "Votre signature est requise pour l'avenant",
    "bailleur/avenant/en_attente_signature": "Votre avenant est signé, en attente des autres parties",
    "bailleur/avenant/relance_j1": "Pensez à compléter votre bail",
    "bailleur/avenant/relance_j3": "Votre bail n'est pas encore complet",
    "bailleur/avenant/relance_j7": "Dernier rappel - Vous prenez le risque d'être en infraction",
    "bailleur/avenant/signe": "Votre avenant est signé et disponible",
    # === MANDATAIRE BAIL ===
    "mandataire/bail/demande_signature": "Votre signature de mandataire est requise pour le bail",
    "mandataire/bail/relance_j1": "Rappel : signature mandataire attendue",
    "mandataire/bail/relance_j3": "Le bail attend votre signature de mandataire",
    "mandataire/bail/relance_j7": "Dernier rappel pour signer en tant que mandataire",
    "mandataire/bail/bail_signe": "Le bail est maintenant signé par toutes les parties",
    # === MANDATAIRE EDL ===
    "mandataire/edl/demande_signature": "Votre signature est requise pour l'état des lieux",
    "mandataire/edl/relance_j1": "Votre état des lieux est prêt à être complété",
    "mandataire/edl/relance_j2": "Un état des lieux clair, une location sans souci",
    "mandataire/edl/relance_j3": "Dernier rappel – finalisez votre état des lieux",
    "mandataire/edl/signe": "L'état des lieux est signé et disponible",
    # === MANDATAIRE AVENANT ===
    "mandataire/avenant/demande_signature": "Votre signature est requise pour l'avenant",
    "mandataire/avenant/en_attente_signature": "L'avenant est signé de votre côté, en attente du locataire",
    "mandataire/avenant/relance_j1": "Informations manquantes – complétez le bail",
    "mandataire/avenant/relance_j3": "Le bail n'est pas encore complet",
    "mandataire/avenant/relance_j7": "Dernier rappel – Le bail risque de ne pas être conforme",
    "mandataire/avenant/signe": "L'avenant est signé et disponible",
    # === LOCATAIRE BAIL ===
    "locataire/bail/demande_signature": "Votre bail est prêt à être signé avec Hestia",
    "locataire/bail/relance_j1": "Votre bail avance, à vous de le finaliser",
    "locataire/bail/relance_j2": "Plus vite vous signez, plus vite vous serez serein·e",
    "locataire/bail/relance_j3": "Votre logement vous attend, plus qu'une signature",
    "locataire/bail/bail_signe": "Votre bail est signé et disponible",
    # === LOCATAIRE EDL ===
    "locataire/edl/demande_signature": "Votre état des lieux est prêt à être signé",
    "locataire/edl/relance_j1": "Il vous reste à signer l'état des lieux",
    "locataire/edl/relance_j2": "Votre état des lieux n'est pas encore validé",
    "locataire/edl/relance_j3": "Dernier rappel : signez votre état des lieux aujourd'hui",
    "locataire/edl/entree_signe": "Votre état des lieux d'entrée est signé et disponible",
    "locataire/edl/sortie_signe": "Votre état des lieux de sortie est signé et disponible",
    # === LOCATAIRE AVENANT ===
    "locataire/avenant/demande_signature": "Votre avenant est prêt à être signé",
    "locataire/avenant/relance_j1": "Il ne manque plus que votre signature",
    "locataire/avenant/relance_j2": "Protégez vos droits en signant l'avenant",
    "locataire/avenant/relance_j3": "Dernier rappel : signez votre avenant maintenant",
    "locataire/avenant/signe": "Votre avenant est signé et valide",
    # === LOCATAIRE QUITTANCE ===
    "locataire/quittance/nouvelle": "Vous avez une nouvelle quittance de loyer",
}


def get_subject(template: str, **kwargs) -> str:
    """
    Récupère le sujet d'email pour un template donné.

    Args:
        template: Nom du template (ex: 'bailleur/bail/demande_signature')
        **kwargs: Variables pour le formatage (ex: mois='Janvier', annee=2025)

    Returns:
        Le sujet formaté ou le template si non trouvé
    """
    subject = EMAIL_SUBJECTS.get(template, template)
    if kwargs:
        try:
            return subject.format(**kwargs)
        except KeyError:
            return subject
    return subject
