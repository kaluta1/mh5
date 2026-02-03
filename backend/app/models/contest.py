from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, Integer, ForeignKey, Boolean, DateTime, Enum, Text, Date, Float, JSON
from sqlalchemy.orm import relationship, Mapped, mapped_column
from datetime import datetime, date
import enum

if TYPE_CHECKING:
    from app.models.round import Round

from app.db.base_class import Base

class VotingRestriction(str, enum.Enum):
    NONE = "none"
    MALE_ONLY = "male_only"
    FEMALE_ONLY = "female_only"
    GEOGRAPHIC = "geographic"
    AGE_RESTRICTED = "age_restricted"


class VerificationType(str, enum.Enum):
    """Types de vérification requis pour participer à un concours."""
    NONE = "none"                      # Aucune vérification spécifique
    VISUAL = "visual"                  # Vérification visuelle (Beauty, Handsome, Pet)
    VOICE = "voice"                    # Vérification vocale (Musique, Chant)
    BRAND = "brand"                    # Vérification de marque/club
    CONTENT_OWNERSHIP = "content"      # Vérification propriété du contenu


class ParticipantType(str, enum.Enum):
    """Type de participant au concours."""
    INDIVIDUAL = "individual"          # Personne physique
    PET = "pet"                        # Animal de compagnie
    CLUB = "club"                      # Club sportif ou fan club
    CONTENT = "content"                # Contenu (musique, vidéo, etc.)


class ContestantVerificationStatus(str, enum.Enum):
    """Statut de vérification d'un contestant."""
    PENDING = "pending"                # En attente de validation
    APPROVED = "approved"              # Approuvé
    REJECTED = "rejected"              # Rejeté


class ContestantVerificationType(str, enum.Enum):
    """Types de vérification pour un contestant."""
    SELFIE = "selfie"                          # Selfie simple
    SELFIE_WITH_PET = "selfie_with_pet"        # Selfie avec animal
    SELFIE_WITH_DOCUMENT = "selfie_with_doc"   # Selfie avec document
    VOICE_RECORDING = "voice_recording"        # Enregistrement vocal
    VIDEO_VERIFICATION = "video_verification"  # Vidéo de vérification
    BRAND_PROOF = "brand_proof"                # Preuve de marque/club


class VotingLevel(str, enum.Enum):
    """Niveau de vote pour un type de vote."""
    CITY = "city"
    COUNTRY = "country"
    REGIONAL = "regional"
    CONTINENT = "continent"
    GLOBAL = "global"


class CommissionSource(str, enum.Enum):
    """Source de commission."""
    ADVERT = "advert"
    AFFILIATE = "affiliate"
    KYC = "kyc"
    MFM = "MFM"


class SuggestedContestStatus(str, enum.Enum):
    """Statut d'une suggestion de concours."""
    PENDING = "pending"      # En attente de traitement
    APPROVED = "approved"    # Approuvé
    REJECTED = "rejected"    # Rejeté

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.media import Media
    from app.models.comment import Comment, Like
    from app.models.transaction import UserTransaction
    from app.models.prize import Prize

class Contest(Base):
    __tablename__ = "contest"
    
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    contest_type: Mapped[str] = mapped_column(String(50), nullable=False)  # beauty, handsome, latest_hits, etc.
    cover_image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # URL de l'image de couverture
    
    # Template de référence
    template_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("contest_template.id"), nullable=True)
    
    # État
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_submission_open: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_voting_open: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Structure géographique
    level: Mapped[str] = mapped_column(String(20), nullable=False)  # 'city', 'country', 'region', 'continent', 'global'
    location_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("location.id"), nullable=True)
    
    # Type de vote (optionnel)
    voting_type_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("voting_type.id"), nullable=True)
    
    # Catégorie (optionnel)
    category_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("categories.id"), nullable=True)
    
    # Relations
    template: Mapped[Optional["ContestTemplate"]] = relationship("ContestTemplate", back_populates="contests")
    location: Mapped[Optional["Location"]] = relationship("Location", back_populates="contests")
    voting_type: Mapped[Optional["VotingType"]] = relationship("VotingType")
    category: Mapped[Optional["Category"]] = relationship("Category", back_populates="contests")
    entries: Mapped[List["ContestEntry"]] = relationship("ContestEntry", back_populates="contest")
    transactions: Mapped[List["UserTransaction"]] = relationship("UserTransaction", back_populates="contest")
    prizes: Mapped[List["Prize"]] = relationship("Prize", back_populates="contest")
    seasons: Mapped[List["ContestSeasonLink"]] = relationship("ContestSeasonLink", back_populates="contest")
    legacy_rounds: Mapped[List["Round"]] = relationship("Round", back_populates="contest")
    rounds: Mapped[List["Round"]] = relationship("Round", secondary="round_contests", back_populates="contests")
    
    # Règles du concours
    gender_restriction: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # male, female, ou null si pas de restriction
    max_entries_per_user: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    
    # Restriction de vote (pour l'admin)
    voting_restriction: Mapped[VotingRestriction] = mapped_column(Enum(VotingRestriction), default=VotingRestriction.NONE, nullable=False)
    
    # Image du concours
    image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # Dates du concours (gestion centralisée ou override des rounds)
    submission_start_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    submission_end_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    voting_start_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    voting_end_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    
    # Dates des saisons (optionnel)
    city_season_start_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    city_season_end_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    country_season_start_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    country_season_end_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    regional_start_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    regional_end_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    continental_start_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    continental_end_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    global_start_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    global_end_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)

    # Nombre de participants
    participant_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # ============== VERIFICATION REQUIREMENTS ==============
    # KYC obligatoire pour participer (défaut: oui)
    requires_kyc: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Type de vérification requis
    verification_type: Mapped[VerificationType] = mapped_column(
        Enum(VerificationType, values_callable=lambda x: [e.value for e in x]), 
        default=VerificationType.NONE, 
        nullable=False
    )
    
    # Type de participant
    participant_type: Mapped[ParticipantType] = mapped_column(
        Enum(ParticipantType, values_callable=lambda x: [e.value for e in x]), 
        default=ParticipantType.INDIVIDUAL, 
        nullable=False
    )
    
    # Vérification visuelle: comparer le contenu avec l'identité vérifiée
    requires_visual_verification: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Vérification vocale: pour les concours de musique/chant
    requires_voice_verification: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Vérification de marque/propriété: pour les clubs, marques
    requires_brand_verification: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Vérification de propriété du contenu (pas de plagiat)
    requires_content_verification: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Âge minimum pour participer (null = pas de restriction)
    min_age: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Âge maximum pour participer (null = pas de restriction)
    max_age: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # ============== MEDIA REQUIREMENTS ==============
    # Vidéo obligatoire pour la participation
    requires_video: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Nombre maximum de vidéos autorisées (pour la participation)
    max_videos: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    
    # Durée max des vidéos de participation en secondes (défaut: 50 min = 3000s)
    video_max_duration: Mapped[int] = mapped_column(Integer, default=3000, nullable=False)
    
    # Taille max des vidéos en MB
    video_max_size_mb: Mapped[int] = mapped_column(Integer, default=500, nullable=False)
    
    # Nombre minimum d'images requises
    min_images: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Nombre maximum d'images autorisées
    max_images: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    
    # ============== VERIFICATION MEDIA LIMITS ==============
    # Durée max des vidéos de vérification en secondes (défaut: 30s)
    verification_video_max_duration: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    
    # Taille max des médias de vérification en MB
    verification_max_size_mb: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    
    # Soft delete
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class ContestTemplate(Base):
    __tablename__ = "contest_template"
    
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    contest_type: Mapped[str] = mapped_column(String(50), nullable=False)
    
    # Configuration du template
    has_geo_restrictions: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_gender_restrictions: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    default_submission_days: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    default_voting_days: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    
    # ============== VERIFICATION DEFAULTS ==============
    # KYC obligatoire par défaut
    default_requires_kyc: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Type de vérification par défaut
    default_verification_type: Mapped[VerificationType] = mapped_column(
        Enum(VerificationType, values_callable=lambda x: [e.value for e in x]), 
        default=VerificationType.NONE, 
        nullable=False
    )
    
    # Type de participant par défaut
    default_participant_type: Mapped[ParticipantType] = mapped_column(
        Enum(ParticipantType, values_callable=lambda x: [e.value for e in x]), 
        default=ParticipantType.INDIVIDUAL, 
        nullable=False
    )
    
    # Vérifications par défaut
    default_visual_verification: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    default_voice_verification: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    default_brand_verification: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    default_content_verification: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Restrictions d'âge par défaut
    default_min_age: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    default_max_age: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Relations
    contests: Mapped[List["Contest"]] = relationship("Contest", back_populates="template")



class LocationLevel(str, enum.Enum):
    """Niveau de localisation."""
    CITY = "city"
    COUNTRY = "country"
    REGION = "region"
    CONTINENT = "continent"
    GLOBAL = "global"


class Location(Base):
    __tablename__ = "location"
    
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    level: Mapped[LocationLevel] = mapped_column(
        Enum(LocationLevel, name='location_level', values_callable=lambda x: [e.value for e in x]),
        nullable=False
    )
    
    # Relations hiérarchiques
    parent_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("location.id"), nullable=True)
    parent: Mapped[Optional["Location"]] = relationship("Location", remote_side="Location.id", back_populates="children")
    children: Mapped[List["Location"]] = relationship("Location", back_populates="parent")
    
    # Relations avec les concours
    contests: Mapped[List["Contest"]] = relationship("Contest", back_populates="location")


class ContestEntry(Base):
    __tablename__ = "contest_entry"
    
    contest_id: Mapped[int] = mapped_column(Integer, ForeignKey("contest.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    media_id: Mapped[int] = mapped_column(Integer, ForeignKey("media.id"), nullable=False)
    
    # Score et classement
    total_score: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Relations
    user: Mapped["User"] = relationship("User", back_populates="contest_entries")
    contest: Mapped["Contest"] = relationship("Contest", back_populates="entries")
    media: Mapped["Media"] = relationship("Media", back_populates="contest_entries")
    votes: Mapped[List["ContestVote"]] = relationship("ContestVote", back_populates="entry")


class ContestVote(Base):
    __tablename__ = "contest_votes"
    
    entry_id: Mapped[int] = mapped_column(Integer, ForeignKey("contest_entry.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    round_id: Mapped[int] = mapped_column(Integer, ForeignKey("rounds.id"), nullable=True) # Optional for backward compatibility/migration
    score: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-5 pour MyHigh5
    
    # Relations
    entry: Mapped["ContestEntry"] = relationship("ContestEntry", back_populates="votes")
    user: Mapped["User"] = relationship("User")
    round: Mapped["Round"] = relationship("Round")


class ContestFavorite(Base):
    __tablename__ = "contest_favorites"
    
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    contest_id: Mapped[int] = mapped_column(Integer, ForeignKey("contest.id"), nullable=False)
    added_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relations
    user: Mapped["User"] = relationship("User")
    contest: Mapped["Contest"] = relationship("Contest")


class ContestantVerification(Base):
    """
    Table de vérification des contestants.
    Chaque concours qui exige une vérification aura une entrée par contestant.
    Les vérifications sont spécifiques à chaque participation (pas réutilisables).
    """
    __tablename__ = "contestant_verifications"
    
    # Référence au contestant
    contestant_id: Mapped[int] = mapped_column(Integer, ForeignKey("contestants.id"), nullable=False)
    
    # Type de vérification
    verification_type: Mapped[ContestantVerificationType] = mapped_column(
        Enum(ContestantVerificationType, values_callable=lambda x: [e.value for e in x]),
        nullable=False
    )
    
    # URL du média de vérification (image, vidéo, audio)
    media_url: Mapped[str] = mapped_column(String(500), nullable=False)
    
    # Type de média (image, video, audio)
    media_type: Mapped[str] = mapped_column(String(20), nullable=False)  # 'image', 'video', 'audio'
    
    # Durée en secondes (pour vidéo/audio)
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Taille en bytes
    file_size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Statut de la vérification
    status: Mapped[ContestantVerificationStatus] = mapped_column(
        Enum(ContestantVerificationStatus, values_callable=lambda x: [e.value for e in x]),
        default=ContestantVerificationStatus.PENDING,
        nullable=False
    )
    
    # Raison du rejet (si rejeté)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Admin qui a validé/rejeté
    reviewed_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Relations
    contestant: Mapped["Contestant"] = relationship("Contestant", back_populates="verifications")
    reviewer: Mapped[Optional["User"]] = relationship("User", foreign_keys=[reviewed_by])


class VotingType(Base):
    """
    Table des types de vote.
    Table indépendante qui définit les règles de commission et le niveau de vote.
    """
    __tablename__ = "voting_type"
    
    # Nom du type de vote
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # Niveau de vote (city, country, regional, continent, global)
    voting_level: Mapped[VotingLevel] = mapped_column(
        Enum(VotingLevel, values_callable=lambda x: [e.value for e in x]),
        nullable=False
    )
    
    # Règles de commission (JSON) - peut contenir plusieurs règles comme L1, L2-10
    commission_rules: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    
    # Source de commission (advert, affiliate, kyc, MFM)
    commission_source: Mapped[CommissionSource] = mapped_column(
        Enum(CommissionSource, values_callable=lambda x: [e.value for e in x]),
        nullable=False
    )


class SuggestedContest(Base):
    """
    Table des concours suggérés par les utilisateurs.
    Permet aux utilisateurs de proposer de nouveaux concours.
    """
    __tablename__ = "suggested_contest"
    
    # Nom du concours suggéré
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # Description du concours suggéré
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Catégorie du concours (beauty, handsome, music, etc.)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    
    # Statut de la suggestion
    status: Mapped[SuggestedContestStatus] = mapped_column(
        Enum(SuggestedContestStatus, values_callable=lambda x: [e.value for e in x]),
        default=SuggestedContestStatus.PENDING,
        nullable=False
    )
