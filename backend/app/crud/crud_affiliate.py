from typing import Any, Dict, Optional, List
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from app.models.affiliate import (
    AffiliateTree, AffiliateCommission, CommissionRate,
    ReferralLink, ReferralClick, FoundingMember, RevenueShare,
    CommissionStatus, CommissionType
)
from app.models.user import User


class CRUDAffiliateTree:
    def get(self, db: Session, id: int) -> Optional[AffiliateTree]:
        return db.query(AffiliateTree).filter(AffiliateTree.id == id).first()
    
    def get_by_user(self, db: Session, user_id: int) -> Optional[AffiliateTree]:
        return db.query(AffiliateTree).filter(AffiliateTree.user_id == user_id).first()
    
    def get_user_tree(self, db: Session, user_id: int) -> Optional[dict]:
        """Récupère l'arbre d'affiliation de l'utilisateur avec ses informations."""
        tree = self.get_by_user(db, user_id)
        if not tree:
            return None
        
        user = db.query(User).filter(User.id == user_id).first()
        sponsor = db.query(User).filter(User.id == tree.sponsor_id).first() if tree.sponsor_id else None
        
        # Compter les parrainages directs
        direct_count = db.query(func.count(AffiliateTree.id)).filter(
            AffiliateTree.sponsor_id == user_id
        ).scalar() or 0
        
        # Calculer les commissions totales
        total_commissions = db.query(func.sum(AffiliateCommission.commission_amount)).filter(
            AffiliateCommission.user_id == user_id,
            AffiliateCommission.status.in_([CommissionStatus.APPROVED, CommissionStatus.PAID])
        ).scalar() or 0.0
        
        return {
            "id": tree.id,
            "user_id": tree.user_id,
            "sponsor_id": tree.sponsor_id,
            "level": tree.level,
            "is_active": tree.is_active,
            "joined_at": tree.join_date,
            "user_name": user.full_name or user.username if user else None,
            "sponsor_name": sponsor.full_name or sponsor.username if sponsor else None,
            "direct_referrals_count": direct_count,
            "total_commissions_earned": float(total_commissions)
        }
    
    def get_direct_referrals(
        self, db: Session, sponsor_id: int, skip: int = 0, limit: int = 50
    ) -> List[dict]:
        """Récupère les parrainages directs avec informations utilisateur."""
        trees = db.query(AffiliateTree).filter(
            AffiliateTree.sponsor_id == sponsor_id
        ).offset(skip).limit(limit).all()
        
        result = []
        for tree in trees:
            user = db.query(User).filter(User.id == tree.user_id).first()
            
            # Commissions générées par cet affilié
            commissions = db.query(func.sum(AffiliateCommission.commission_amount)).filter(
                AffiliateCommission.source_user_id == tree.user_id,
                AffiliateCommission.user_id == sponsor_id
            ).scalar() or 0.0
            
            # Nombre de ses propres parrainages
            sub_referrals = db.query(func.count(AffiliateTree.id)).filter(
                AffiliateTree.sponsor_id == tree.user_id
            ).scalar() or 0
            
            result.append({
                "id": tree.id,
                "user_id": tree.user_id,
                "name": user.full_name or user.username or user.email if user else "Unknown",
                "email": user.email if user else None,
                "avatar": user.avatar_url if user else None,
                "level": 1,  # Direct = niveau 1
                "joined_at": tree.join_date.isoformat() if tree.join_date else None,
                "status": "active" if tree.is_active else "inactive",
                "commissions_generated": float(commissions),
                "referrals_count": sub_referrals
            })
        
        return result
    
    def get_user_stats(self, db: Session, user_id: int) -> dict:
        """Récupère les statistiques complètes d'affiliation."""
        user = db.query(User).filter(User.id == user_id).first()
        
        # Parrainages directs (niveau 1) - utiliser User.sponsor_id
        direct_referrals = db.query(func.count(User.id)).filter(
            User.sponsor_id == user_id
        ).scalar() or 0
        
        # Parrainages indirects (niveaux 2-10) via AffiliateTree si disponible
        tree = self.get_by_user(db, user_id)
        indirect_referrals = 0
        
        if tree and tree.path:
            # Compter tous les utilisateurs dont le path contient notre user_id
            indirect_referrals = db.query(func.count(AffiliateTree.id)).filter(
                AffiliateTree.path.like(f"%/{user_id}/%"),
                AffiliateTree.sponsor_id != user_id  # Exclure les directs
            ).scalar() or 0
        
        # Commissions totales gagnées
        total_earned = db.query(func.sum(AffiliateCommission.commission_amount)).filter(
            AffiliateCommission.user_id == user_id,
            AffiliateCommission.status.in_([CommissionStatus.APPROVED, CommissionStatus.PAID])
        ).scalar() or 0.0
        
        # Commissions en attente
        pending_commissions = db.query(func.sum(AffiliateCommission.commission_amount)).filter(
            AffiliateCommission.user_id == user_id,
            AffiliateCommission.status == CommissionStatus.PENDING
        ).scalar() or 0.0
        
        # Revenus partagés (membre fondateur)
        revenue_shared = db.query(func.sum(RevenueShare.share_amount)).filter(
            RevenueShare.user_id == user_id,
            RevenueShare.is_paid == True
        ).scalar() or 0.0
        
        # Vérifier si membre fondateur
        founding_member = db.query(FoundingMember).filter(
            FoundingMember.user_id == user_id,
            FoundingMember.is_active == True
        ).first()
        
        # Taux de conversion basé sur le nombre de filleuls directs
        clicks = 0
        conversions = direct_referrals  # Les filleuls sont les conversions
        
        # Vérifier les clics via ReferralLink si disponible
        referral_link = db.query(ReferralLink).filter(
            ReferralLink.user_id == user_id
        ).first()
        
        if referral_link:
            clicks = referral_link.clicks
        
        conversion_rate = (conversions / clicks * 100) if clicks > 0 else 0.0
        
        return {
            "total_affiliates": direct_referrals + indirect_referrals,
            "direct_referrals": direct_referrals,
            "indirect_referrals": indirect_referrals,
            "total_commissions": float(total_earned),
            "pending_commissions": float(pending_commissions),
            "revenue_shared": float(revenue_shared),
            "referral_code": user.personal_referral_code if user else None,
            "referral_link": None,  # Sera généré côté frontend avec l'URL du serveur
            "clicks": clicks,
            "conversions": conversions,
            "conversion_rate": round(conversion_rate, 2),
            "is_founding_member": founding_member is not None,
            "level_stats": self._get_level_stats(db, user_id)
        }
    
    def _get_level_stats(self, db: Session, user_id: int) -> List[dict]:
        """Récupère les statistiques par niveau (1-10)."""
        stats = []
        for level in range(1, 11):
            # Commissions par niveau
            level_commissions = db.query(func.sum(AffiliateCommission.commission_amount)).filter(
                AffiliateCommission.user_id == user_id,
                AffiliateCommission.level == level
            ).scalar() or 0.0
            
            # Nombre d'affiliés à ce niveau
            level_count = db.query(func.count(AffiliateCommission.id)).filter(
                AffiliateCommission.user_id == user_id,
                AffiliateCommission.level == level
            ).scalar() or 0
            
            rate = 20.0 if level == 1 else 2.0
            
            stats.append({
                "level": level,
                "rate": rate,
                "affiliates_count": level_count,
                "commissions": float(level_commissions)
            })
        
        return stats
    
    def join_via_referral(
        self, db: Session, user_id: int, referral_code: str
    ) -> dict:
        """Inscrit un utilisateur dans l'arbre via un code de parrainage."""
        # Vérifier si l'utilisateur n'est pas déjà dans l'arbre
        existing = self.get_by_user(db, user_id)
        if existing:
            return {"success": False, "error": "Utilisateur déjà inscrit dans le programme"}
        
        # Trouver le parrain par son code
        sponsor = db.query(User).filter(
            User.personal_referral_code == referral_code
        ).first()
        
        if not sponsor:
            return {"success": False, "error": "Code de parrainage invalide"}
        
        if sponsor.id == user_id:
            return {"success": False, "error": "Vous ne pouvez pas vous parrainer vous-même"}
        
        # Récupérer l'arbre du parrain pour calculer le path
        sponsor_tree = self.get_by_user(db, sponsor.id)
        
        if sponsor_tree:
            new_path = f"{sponsor_tree.path or ''}/{sponsor.id}"
            new_level = sponsor_tree.level + 1
        else:
            new_path = f"/{sponsor.id}"
            new_level = 1
        
        # Créer l'entrée dans l'arbre
        new_tree = AffiliateTree(
            user_id=user_id,
            sponsor_id=sponsor.id,
            level=new_level,
            path=new_path,
            join_date=datetime.utcnow(),
            is_active=True
        )
        
        db.add(new_tree)
        db.commit()
        db.refresh(new_tree)
        
        return {"success": True, "tree": new_tree}
    
    def get_genealogy(self, db: Session, user_id: int, levels: int = 10) -> dict:
        """Récupère la généalogie sur X niveaux."""
        user = db.query(User).filter(User.id == user_id).first()
        
        def build_tree(uid: int, current_level: int) -> dict:
            u = db.query(User).filter(User.id == uid).first()
            if not u:
                return None
            
            children = []
            if current_level < levels:
                direct = db.query(AffiliateTree).filter(
                    AffiliateTree.sponsor_id == uid
                ).all()
                
                for d in direct:
                    child = build_tree(d.user_id, current_level + 1)
                    if child:
                        children.append(child)
            
            # Commissions générées
            commissions = db.query(func.sum(AffiliateCommission.commission_amount)).filter(
                AffiliateCommission.source_user_id == uid
            ).scalar() or 0.0
            
            return {
                "user_id": uid,
                "name": u.full_name or u.username or u.email,
                "avatar": u.avatar_url,
                "level": current_level,
                "referrals": children,
                "total_descendants": len(children) + sum(c.get("total_descendants", 0) for c in children),
                "commissions": float(commissions)
            }
        
        return build_tree(user_id, 0)


class CRUDAffiliateCommission:
    # Taux de commission par niveau (niveau 1 = parrain direct = 20%, niveaux 2-10 = 2%)
    COMMISSION_RATES = {
        1: 0.20,   # 20% pour le parrain direct
        2: 0.02,   # 2% pour le niveau 2
        3: 0.02,   # 2% pour le niveau 3
        4: 0.02,   # 2% pour le niveau 4
        5: 0.02,   # 2% pour le niveau 5
        6: 0.02,   # 2% pour le niveau 6
        7: 0.02,   # 2% pour le niveau 7
        8: 0.02,   # 2% pour le niveau 8
        9: 0.02,   # 2% pour le niveau 9
        10: 0.02,  # 2% pour le niveau 10
    }
    
    def create_commission(
        self, db: Session, 
        source_user_id: int,  # L'utilisateur qui a payé
        commission_type: CommissionType,
        base_amount: float,  # Montant de la transaction
        reference_id: str = None,
        reference_type: str = None
    ) -> List[AffiliateCommission]:
        """
        Crée des commissions pour tous les sponsors dans la hiérarchie.
        Retourne la liste des commissions créées.
        """
        commissions_created = []
        
        # Trouver le parrain direct de l'utilisateur
        source_user = db.query(User).filter(User.id == source_user_id).first()
        if not source_user or not source_user.sponsor_id:
            return commissions_created
        
        # Remonter l'arbre des parrains jusqu'au niveau max
        current_sponsor_id = source_user.sponsor_id
        level = 1
        
        while current_sponsor_id and level <= len(self.COMMISSION_RATES):
            rate = self.COMMISSION_RATES.get(level, 0)
            if rate <= 0:
                break
            
            commission_amount = base_amount * rate
            
            # Créer la commission
            commission = AffiliateCommission(
                user_id=current_sponsor_id,  # Le parrain qui reçoit
                source_user_id=source_user_id,  # L'utilisateur qui a payé
                commission_type=commission_type,
                level=level,
                min_amount=base_amount,
                commission_rate=rate,
                commission_amount=commission_amount,
                reference_id=reference_id,
                reference_type=reference_type,
                status=CommissionStatus.APPROVED,  # Auto-approuvé
                transaction_date=datetime.utcnow()
            )
            
            db.add(commission)
            commissions_created.append(commission)
            
            # Trouver le parrain du parrain pour le niveau suivant
            sponsor = db.query(User).filter(User.id == current_sponsor_id).first()
            current_sponsor_id = sponsor.sponsor_id if sponsor else None
            level += 1
        
        if commissions_created:
            db.commit()
            for c in commissions_created:
                db.refresh(c)
        
        return commissions_created
    
    def get_user_commissions(
        self, db: Session, user_id: int, skip: int = 0, limit: int = 50,
        commission_type: Optional[str] = None
    ) -> List[AffiliateCommission]:
        query = db.query(AffiliateCommission).filter(
            AffiliateCommission.user_id == user_id
        )
        
        if commission_type:
            query = query.filter(AffiliateCommission.commission_type == commission_type)
        
        return query.order_by(AffiliateCommission.transaction_date.desc()).offset(skip).limit(limit).all()
    
    def get_commissions_summary(self, db: Session, user_id: int) -> List[dict]:
        """Résumé des commissions par type et statut."""
        summary = db.query(
            AffiliateCommission.commission_type,
            AffiliateCommission.status,
            func.sum(AffiliateCommission.commission_amount).label("total"),
            func.count(AffiliateCommission.id).label("count")
        ).filter(
            AffiliateCommission.user_id == user_id
        ).group_by(
            AffiliateCommission.commission_type,
            AffiliateCommission.status
        ).all()
        
        return [
            {
                "type": str(s.commission_type.value) if s.commission_type else None,
                "status": str(s.status.value) if s.status else None,
                "total": float(s.total or 0),
                "count": s.count
            }
            for s in summary
        ]


class CRUDReferralLink:
    def get_by_user(self, db: Session, user_id: int) -> List[ReferralLink]:
        return db.query(ReferralLink).filter(ReferralLink.user_id == user_id).all()
    
    def create_with_user(
        self, db: Session, obj_in: Any, user_id: int
    ) -> ReferralLink:
        import secrets
        code = secrets.token_urlsafe(8)
        
        db_obj = ReferralLink(
            user_id=user_id,
            referral_code=code,
            is_active=True
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj


class CRUDReferralClick:
    def track_click(
        self, db: Session, referral_code: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        referer: Optional[str] = None
    ) -> bool:
        link = db.query(ReferralLink).filter(
            ReferralLink.referral_code == referral_code
        ).first()
        
        if not link:
            return False
        
        # Créer le click
        click = ReferralClick(
            referral_link_id=link.id,
            ip_address=ip_address,
            user_agent=user_agent,
            referer=referer
        )
        
        # Incrémenter le compteur
        link.clicks += 1
        
        db.add(click)
        db.add(link)
        db.commit()
        
        return True


class CRUDRevenueShare:
    def get_user_shares(
        self, db: Session, user_id: int, skip: int = 0, limit: int = 50
    ) -> List[RevenueShare]:
        return db.query(RevenueShare).filter(
            RevenueShare.user_id == user_id
        ).order_by(RevenueShare.distribution_date.desc()).offset(skip).limit(limit).all()


class CRUDFoundingMember:
    def get_member_info(self, db: Session, user_id: int) -> Optional[dict]:
        member = db.query(FoundingMember).filter(
            FoundingMember.user_id == user_id
        ).first()
        
        if not member:
            return None
        
        # Total des revenus partagés
        total_shared = db.query(func.sum(RevenueShare.share_amount)).filter(
            RevenueShare.user_id == user_id,
            RevenueShare.source_type == "founding_member"
        ).scalar() or 0.0
        
        return {
            "id": member.id,
            "user_id": member.user_id,
            "founding_membership_ratio": float(member.founding_membership_ratio),
            "founding_date": member.founding_date.isoformat() if member.founding_date else None,
            "is_active": member.is_active,
            "total_revenue_shared": float(total_shared)
        }


# Instances singleton
affiliate_tree = CRUDAffiliateTree()
affiliate_commission = CRUDAffiliateCommission()
referral_link = CRUDReferralLink()
referral_click = CRUDReferralClick()
revenue_share = CRUDRevenueShare()
founding_member = CRUDFoundingMember()
