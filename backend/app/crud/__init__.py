# Ce fichier est nécessaire pour faire de ce répertoire un package Python

from .crud_contest import contest
from .crud_user import user  
from .crud_media import media
from .crud_voting import vote, voting_stats, voting_session
from .crud_geography import continent, region, country, city
from .crud_kyc import kyc_verification, kyc_document, kyc_audit_log
from .crud_contestant import crud_contestant as contestant
from .crud_favorite import favorite
# Modules affiliés
from .crud_affiliate import (
    affiliate_tree, affiliate_commission, referral_link, 
    referral_click, revenue_share, founding_member
)

# Modules non implémentés - commentés temporairement
# from .crud_clubs import fan_club, club_membership, club_wallet
# from .crud_dsp import dsp_wallet, dsp_transaction, digital_product
# from .crud_advertising import ad_campaign, ad_creative, ad_impression
# from .crud_accounting import chart_of_accounts, journal_entry, revenue_transaction
