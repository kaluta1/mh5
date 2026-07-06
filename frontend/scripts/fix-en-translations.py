#!/usr/bin/env python3
"""Replace French strings accidentally stored in en.json with proper English."""
import json
from pathlib import Path

REPLACEMENTS = {
    "Confirmer la suppression": "Confirm deletion",
    "Effacer": "Clear",
    "Continuer": "Continue",
    "Modifier": "Edit",
    "Le mot de passe est requis": "Password is required",
    "La confirmation du mot de passe est requise": "Password confirmation is required",
    "Les mots de passe ne correspondent pas": "Passwords do not match",
    "Redirection vers la page de connexion...": "Redirecting to sign in...",
    "Token manquant": "Missing token",
    "Entrez votre nouveau mot de passe ci-dessous.": "Enter your new password below.",
    "Nouveau mot de passe": "New password",
    "Confirmer le mot de passe": "Confirm password",
    "Envoi en cours...": "Sending...",
    "Aucune description disponible": "No description available",
    "Titre": "Title",
    "Utilisateur": "User",
    "Total de partages": "Total shares",
    "Partages par plateforme": "Shares by platform",
    "Statut": "Status",
    "Partages": "Shares",
    "Sexe": "Gender",
    "Homme": "Male",
    "Femme": "Female",
    "Biographie": "Biography",
    "Signaler": "Report",
    "Autre": "Other",
    "Signaler un participant": "Report a contestant",
    "Envoi...": "Sending...",
    "Partager ce participant": "Share this contestant",
    "Copier": "Copy",
    "Partager nativement": "Share natively",
    "Ce mois": "This month",
    "7 jours": "7 days",
    "Taux de conversion": "Conversion rate",
    "Toutes les transactions": "All transactions",
    "Historique complet de vos transactions": "Full history of your transactions",
    "Exporter": "Export",
    "Tout": "All",
    "Achats": "Purchases",
    "Achat": "Purchase",
    "Payer": "Pay",
    "Facture": "Invoice",
    "KYC en cours": "KYC in progress",
    "niveaux": "levels",
    "Rechercher par nom ou email...": "Search by name or email...",
    "Tous les niveaux": "All levels",
    "Tous les statuts": "All statuses",
    "Tous KYC": "All KYC",
    "Parrainages": "Referrals",
    "Affichage": "Showing",
    "sur": "of",
    "Liens": "Links",
    "10 niveaux de commission": "10 commission levels",
    "Aucune commission": "No commissions",
    "Inviter un ami": "Invite a friend",
    "Adresse email": "Email address",
    "Salut ! Rejoins-moi sur MyHigh5...": "Hi! Join me on MyHigh5...",
    "Croissance": "Growth",
    "Par date": "By date",
    "Par montant": "By amount",
    "Par type": "By type",
    "Aucune participation pour le moment": "No entries yet",
    "Progression des utilisateurs": "User progress",
    "Approuvez ou rejetez les candidatures": "Approve or reject applications",
    "Rechercher par nom ou titre...": "Search by name or title...",
    "Tous": "All",
    "Auteur": "Author",
    "Voir": "View",
    "Approuver": "Approve",
    "Rejeter": "Reject",
    "Rechercher une suggestion...": "Search suggestions...",
    "Aucune suggestion pour le moment": "No suggestions yet",
    "Auteur non disponible": "Author not available",
    "Tous les types": "All types",
    "Rechercher": "Search",
    "Aucune transaction pour le moment": "No transactions yet",
    "Le nom est obligatoire": "Name is required",
    "Modifier un Round": "Edit round",
    "Nom du Round": "Round name",
    "Rechercher un round...": "Search rounds...",
    "Cliquez pour changer": "Click to change",
    "Cliquez pour ajouter un document": "Click to upload a document",
    "Description de la preuve": "Proof description",
    "Cliquez pour ajouter une preuve": "Click to upload proof",
    "Selfie avec votre animal": "Selfie with your pet",
    "Selfie avec document": "Selfie with document",
    "Importer une image": "Upload an image",
    "Appuyez pour enregistrer": "Tap to record",
    "Inviter maintenant": "Invite now",
    "Le nom est requis": "Last name is required",
    "La bio est requise": "Bio is required",
    "La date de naissance est requise": "Date of birth is required",
    "Le genre est requis": "Gender is required",
    "Nom": "Last name",
    "Localisation": "Location",
    "Genre": "Gender",
    "Le continent est requis": "Continent is required",
    "Photo, nom et bio": "Photo, name and bio",
    "Le mot de passe actuel est requis": "Current password is required",
    "Le nouveau mot de passe est requis": "New password is required",
    "Confirmer le nouveau mot de passe": "Confirm new password",
    "Modifier le mot de passe": "Change password",
    "Modifiez votre photo, nom et biographie": "Update your photo, name, and bio",
    "Localisation actuelle": "Current location",
    "Liens rapides": "Quick links",
    "Acheter des services": "Buy services",
    "Ajouter un autre utilisateur": "Add another user",
    "Entrez le montant": "Enter amount",
    "Nouveau (Participation)": "New (participation)",
    "Nouveau (Nomination)": "New (nomination)",
    "Nouveau Round": "New round",
    # Wallet / dashboard placeholders
    "Payment Video Title": "How payments work",
    "Payment Video Subtitle": "Watch a quick guide to paying with crypto",
    "Pending Description": "Funds awaiting confirmation",
    "Buy Service": "Buy a service",
    "Since Registration": "Since registration",
}

# Path-specific overrides (dot paths from JSON root)
PATH_OVERRIDES = {
    "dashboard.wallet.title": "Wallet",
    "dashboard.wallet.subtitle": "Manage your balance, purchases, and commissions",
    "dashboard.affiliates.title": "Affiliates",
    "dashboard.affiliates.subtitle": "Grow your network and earn commissions",
    "dashboard.commissions.title": "My commissions",
    "dashboard.following.title": "Following",
    "dashboard.following.subtitle": "People you follow and your followers",
    "auth.reset_password.title": "Reset password",
    "auth.reset_password.description": "Enter your new password below.",
    "dashboard.contests.suggest_contest.title": "Suggest a contest",
}


def fix_value(path: str, value: str) -> str:
    if path in PATH_OVERRIDES:
        return PATH_OVERRIDES[path]
    return REPLACEMENTS.get(value, value)


def walk(obj, path: str = ""):
    if isinstance(obj, dict):
        for key, val in obj.items():
            child_path = f"{path}.{key}" if path else key
            obj[key] = walk(val, child_path)
        return obj
    if isinstance(obj, list):
        return [walk(item, f"{path}[{i}]") for i, item in enumerate(obj)]
    if isinstance(obj, str):
        return fix_value(path, obj)
    return obj


def main() -> None:
    path = Path(__file__).resolve().parents[1] / "lib" / "translations" / "en.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    fixed = walk(data)
    path.write_text(json.dumps(fixed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Updated {path}")


if __name__ == "__main__":
    main()
