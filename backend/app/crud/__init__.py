# Ce fichier est nécessaire pour faire de ce répertoire un package Python

from .crud_contest import contest
from .crud_user import user  
from .crud_media import media
from .crud_voting import vote, voting_stats, voting_session
from .crud_suggested_contest import suggested_contest
from .crud_geography import continent, region, country, city
from .crud_kyc import kyc_verification, kyc_document, kyc_audit_log
from .crud_contestant import crud_contestant as contestant, contest_submission
from .crud_favorite import favorite
from .crud_favorite import favorite
from .crud_report import report
from .crud_round import round
# Modules affiliés
from .crud_affiliate import (
    affiliate_tree, affiliate_commission, referral_link, 
    referral_click, revenue_share, founding_member
)

# RBAC - Rôles et Permissions
from .crud_role import role, permission

# Module crud_contestants pour compatibilité avec myfav_contests.py
class _CRUDContestants:
    """Wrapper pour accéder aux CRUDs contestants et submissions"""
    def __init__(self):
        from .crud_contestant import crud_contestant, contest_submission
        self.contestant = crud_contestant
        self.contest_submission = contest_submission

crud_contestants = _CRUDContestants()

# Modules non implémentés - commentés temporairement
# from .crud_clubs import fan_club, club_membership, club_wallet
# from .crud_dsp import dsp_wallet, dsp_transaction, digital_product
# from .crud_advertising import ad_campaign, ad_creative, ad_impression
# from .crud_accounting import chart_of_accounts, journal_entry, revenue_transaction
