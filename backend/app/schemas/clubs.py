from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime

from app.models.clubs import ClubStatus, MembershipType, MembershipStatus


# Fan Club schemas
class FanClubBase(BaseModel):
    name: str
    slug: str
    description: Optional[str] = None
    membership_fee: float = 0.0
    premium_fee: Optional[float] = None
    annual_discount_percentage: float = 20.0
    requires_approval: bool = False
    is_public: bool = True
    max_members: Optional[int] = None
    multisig_threshold: int = 1


class FanClubCreate(FanClubBase):
    pass


class FanClubUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    membership_fee: Optional[float] = None
    premium_fee: Optional[float] = None
    annual_discount_percentage: Optional[float] = None
    requires_approval: Optional[bool] = None
    is_public: Optional[bool] = None
    max_members: Optional[int] = None
    multisig_threshold: Optional[int] = None


class FanClub(FanClubBase):
    id: int
    owner_id: int
    status: ClubStatus = ClubStatus.ACTIVE
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    # Statistiques
    total_members: int = 0
    total_revenue: float = 0.0


class FanClubWithOwner(FanClub):
    """Club avec informations du propriétaire"""
    owner_name: Optional[str] = None
    owner_email: Optional[str] = None


# Club Admin schemas
class ClubAdminBase(BaseModel):
    club_id: int
    user_id: int
    role: str = "admin"
    can_manage_members: bool = True
    can_manage_content: bool = True
    can_manage_finances: bool = False


class ClubAdminCreate(ClubAdminBase):
    pass


class ClubAdminUpdate(BaseModel):
    role: Optional[str] = None
    can_manage_members: Optional[bool] = None
    can_manage_content: Optional[bool] = None
    can_manage_finances: Optional[bool] = None


class ClubAdmin(ClubAdminBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    appointed_at: Optional[datetime] = None


class ClubAdminWithUser(ClubAdmin):
    """Admin avec informations utilisateur"""
    user_name: Optional[str] = None
    user_email: Optional[str] = None


# Club Membership schemas
class ClubMembershipBase(BaseModel):
    club_id: int
    member_id: int
    membership_type: MembershipType
    start_date: datetime
    end_date: datetime
    amount_paid: float
    payment_method: str  # dsp, stripe, paypal
    auto_renewal: bool = True


class ClubMembershipCreate(BaseModel):
    membership_type: MembershipType
    payment_method: str
    payment_info: Optional[dict] = None


class ClubMembershipUpdate(BaseModel):
    auto_renewal: Optional[bool] = None
    status: Optional[MembershipStatus] = None


class ClubMembership(ClubMembershipBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    status: MembershipStatus = MembershipStatus.ACTIVE


class ClubMembershipWithUser(ClubMembership):
    """Membership avec informations utilisateur"""
    member_name: Optional[str] = None
    member_email: Optional[str] = None
    profile_picture_url: Optional[str] = None


# Club Wallet schemas
class ClubWalletBase(BaseModel):
    club_id: int
    balance_cad: float = 0.0
    balance_usd: float = 0.0
    balance_dsp: float = 0.0
    total_membership_revenue: float = 0.0
    total_ad_revenue: float = 0.0


class ClubWalletCreate(ClubWalletBase):
    pass


class ClubWalletUpdate(BaseModel):
    balance_cad: Optional[float] = None
    balance_usd: Optional[float] = None
    balance_dsp: Optional[float] = None


class ClubWallet(ClubWalletBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    last_updated: Optional[datetime] = None


# Club Transaction schemas
class ClubTransactionBase(BaseModel):
    wallet_id: int
    transaction_type: str  # deposit, withdrawal, fee, revenue
    amount: float
    currency: str
    description: Optional[str] = None
    reference_id: Optional[str] = None
    requires_approval: bool = False
    required_approvals: int = 1


class ClubTransactionCreate(ClubTransactionBase):
    pass


class ClubTransactionUpdate(BaseModel):
    is_approved: Optional[bool] = None


class ClubTransaction(ClubTransactionBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    approvals_count: int = 0
    is_approved: bool = False
    created_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None


# Club Content schemas
class ClubContentBase(BaseModel):
    club_id: int
    author_id: int
    title: str
    content: str
    content_type: str = "text"  # text, image, video, link
    is_premium: bool = False
    is_published: bool = True


class ClubContentCreate(ClubContentBase):
    pass


class ClubContentUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    is_premium: Optional[bool] = None
    is_published: Optional[bool] = None


class ClubContent(ClubContentBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    views_count: int = 0
    likes_count: int = 0
    comments_count: int = 0


class ClubContentWithAuthor(ClubContent):
    """Contenu avec informations auteur"""
    author_name: Optional[str] = None
    author_profile_picture: Optional[str] = None


# Club Content Comment schemas
class ClubContentCommentBase(BaseModel):
    content_id: int
    user_id: int
    comment_text: str
    parent_comment_id: Optional[int] = None


class ClubContentCommentCreate(ClubContentCommentBase):
    pass


class ClubContentCommentUpdate(BaseModel):
    comment_text: Optional[str] = None


class ClubContentComment(ClubContentCommentBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    created_at: Optional[datetime] = None


class ClubContentCommentWithUser(ClubContentComment):
    """Commentaire avec informations utilisateur"""
    user_name: Optional[str] = None
    user_profile_picture: Optional[str] = None


# Club Content Like schemas
class ClubContentLikeBase(BaseModel):
    content_id: int
    user_id: int


class ClubContentLikeCreate(ClubContentLikeBase):
    pass


class ClubContentLike(ClubContentLikeBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    created_at: Optional[datetime] = None


# Transaction Approval schemas
class TransactionApprovalBase(BaseModel):
    transaction_id: int
    admin_id: int
    approved: bool
    notes: Optional[str] = None


class TransactionApprovalCreate(TransactionApprovalBase):
    pass


class TransactionApproval(TransactionApprovalBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    approval_date: Optional[datetime] = None


class TransactionApprovalWithAdmin(TransactionApproval):
    """Approbation avec informations admin"""
    admin_name: Optional[str] = None


# Response schemas complexes
class ClubDashboard(BaseModel):
    """Tableau de bord complet d'un club"""
    club: FanClub
    wallet: ClubWallet
    total_members: int = 0
    active_members: int = 0
    premium_members: int = 0
    monthly_revenue: float = 0.0
    pending_transactions: int = 0
    recent_content: List[ClubContent] = []


class ClubMembersList(BaseModel):
    """Liste des membres avec pagination"""
    members: List[ClubMembershipWithUser] = []
    total_count: int = 0
    active_count: int = 0
    premium_count: int = 0


class ClubFinancialSummary(BaseModel):
    """Résumé financier d'un club"""
    total_revenue: float = 0.0
    membership_revenue: float = 0.0
    ad_revenue: float = 0.0
    total_expenses: float = 0.0
    net_profit: float = 0.0
    pending_withdrawals: float = 0.0
    available_balance: float = 0.0
