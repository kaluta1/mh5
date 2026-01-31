"""
Enhanced Groups API Endpoints
WhatsApp-like private groups with invitation links and email/username member addition
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query, Body
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel, EmailStr

from app.db.session import get_db
from app.api.deps import get_current_active_user
from app.models.user import User
from app.models.social_group import SocialGroup, GroupMember, GroupType, GroupMemberRole
from app.crud.crud_social import crud_social_group
from app.crud.crud_user import crud_user
from app.schemas.social import SocialGroupResponse

router = APIRouter()


class AddMemberRequest(BaseModel):
    """Request to add a member by email or username"""
    email: Optional[EmailStr] = None
    username: Optional[str] = None
    role: Optional[GroupMemberRole] = GroupMemberRole.MEMBER


class InvitationLinkResponse(BaseModel):
    """Response with invitation link"""
    group_id: int
    invite_code: str
    invitation_link: str
    expires_at: Optional[str] = None


@router.post("/groups/{group_id}/members/add", status_code=status.HTTP_200_OK)
def add_member_by_email_or_username(
    *,
    db: Session = Depends(get_db),
    group_id: int,
    member_request: AddMemberRequest,
    current_user: User = Depends(get_current_active_user)
) -> dict:
    """
    Add a member to a group by email or username.
    Only admins and owners can add members.
    """
    # Check if current user is admin or owner
    user_role = crud_social_group.get_member_role(db, group_id, current_user.id)
    if user_role not in [GroupMemberRole.ADMIN, GroupMemberRole.OWNER]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs peuvent ajouter des membres"
        )
    
    # Find user by email or username
    user_to_add = None
    if member_request.email:
        user_to_add = crud_user.get_by_email(db, member_request.email)
        if not user_to_add:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Aucun utilisateur trouvé avec l'email: {member_request.email}"
            )
    elif member_request.username:
        user_to_add = crud_user.get_by_username(db, member_request.username)
        if not user_to_add:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Aucun utilisateur trouvé avec le nom d'utilisateur: {member_request.username}"
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous devez fournir soit un email, soit un nom d'utilisateur"
        )
    
    # Add member
    try:
        member = crud_social_group.add_member(
            db,
            group_id=group_id,
            user_id=user_to_add.id,
            role=member_request.role or GroupMemberRole.MEMBER
        )
        return {
            "success": True,
            "message": f"Utilisateur {user_to_add.username or user_to_add.email} ajouté au groupe",
            "member_id": member.id,
            "user": {
                "id": user_to_add.id,
                "username": user_to_add.username,
                "email": user_to_add.email,
                "avatar_url": user_to_add.avatar_url
            }
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/groups/{group_id}/invitation-link", response_model=InvitationLinkResponse)
def get_invitation_link(
    *,
    db: Session = Depends(get_db),
    group_id: int,
    current_user: User = Depends(get_current_active_user)
) -> InvitationLinkResponse:
    """
    Get the invitation link for a group.
    Only admins and owners can get the invitation link.
    """
    group = crud_social_group.get(db, group_id)
    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Groupe introuvable"
        )
    
    # Check if user is admin or owner
    user_role = crud_social_group.get_member_role(db, group_id, current_user.id)
    if user_role not in [GroupMemberRole.ADMIN, GroupMemberRole.OWNER]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs peuvent obtenir le lien d'invitation"
        )
    
    if not group.invite_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ce groupe n'a pas de code d'invitation"
        )
    
    # Build invitation link path (frontend will construct full URL)
    invitation_link = f"/groups/join/{group.invite_code}"
    
    return InvitationLinkResponse(
        group_id=group.id,
        invite_code=group.invite_code,
        invitation_link=invitation_link
    )


@router.post("/groups/join-by-link/{invite_code}", status_code=status.HTTP_200_OK)
def join_group_by_invitation_link(
    *,
    db: Session = Depends(get_db),
    invite_code: str,
    current_user: User = Depends(get_current_active_user)
) -> dict:
    """
    Join a group using an invitation link (invite code).
    Works like WhatsApp - anyone with the link can join.
    """
    # Find group by invite code
    group = crud_social_group.get_by_invite_code(db, invite_code)
    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lien d'invitation invalide ou expiré"
        )
    
    # Check if already a member
    if crud_social_group.is_member(db, group.id, current_user.id):
        return {
            "success": True,
            "message": "Vous êtes déjà membre de ce groupe",
            "group_id": group.id,
            "group_name": group.name
        }
    
    # Check max members
    if group.max_members and group.member_count >= group.max_members:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Le groupe est complet"
        )
    
    # Add member
    try:
        member = crud_social_group.add_member(
            db,
            group_id=group.id,
            user_id=current_user.id,
            role=GroupMemberRole.MEMBER
        )
        return {
            "success": True,
            "message": f"Vous avez rejoint le groupe '{group.name}'",
            "group_id": group.id,
            "group_name": group.name,
            "member_id": member.id
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/groups/{group_id}/members", response_model=List[dict])
def get_group_members(
    *,
    db: Session = Depends(get_db),
    group_id: int,
    current_user: User = Depends(get_current_active_user)
) -> List[dict]:
    """
    Get all members of a group (WhatsApp-like member list).
    Only members can see the member list.
    """
    # Check if user is a member
    if not crud_social_group.is_member(db, group_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous devez être membre du groupe pour voir la liste des membres"
        )
    
    group = crud_social_group.get(db, group_id)
    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Groupe introuvable"
        )
    
    # Get all members with user details
    from sqlalchemy.orm import joinedload
    members = db.query(GroupMember).options(
        joinedload(GroupMember.user)
    ).filter(
        GroupMember.group_id == group_id
    ).order_by(
        GroupMember.role.desc(),  # Admins/Owners first
        GroupMember.joined_at.asc()  # Then by join date
    ).all()
    
    result = []
    for member in members:
        result.append({
            "id": member.id,
            "user_id": member.user_id,
            "role": member.role.value,
            "joined_at": member.joined_at.isoformat(),
            "is_muted": member.is_muted,
            "is_banned": member.is_banned,
            "user": {
                "id": member.user.id,
                "username": member.user.username,
                "email": member.user.email,
                "avatar_url": member.user.avatar_url,
                "full_name": member.user.full_name or f"{member.user.first_name or ''} {member.user.last_name or ''}".strip()
            } if member.user else None
        })
    
    return result


@router.put("/groups/{group_id}/members/{user_id}/role", status_code=status.HTTP_200_OK)
def update_member_role(
    *,
    db: Session = Depends(get_db),
    group_id: int,
    user_id: int,
    new_role: GroupMemberRole = Body(...),
    current_user: User = Depends(get_current_active_user)
) -> dict:
    """
    Update a member's role (promote to admin, etc.).
    Only owners can change roles.
    """
    # Check if current user is owner
    current_role = crud_social_group.get_member_role(db, group_id, current_user.id)
    if current_role != GroupMemberRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seul le propriétaire du groupe peut modifier les rôles"
        )
    
    # Get the member
    member = db.query(GroupMember).filter(
        GroupMember.group_id == group_id,
        GroupMember.user_id == user_id
    ).first()
    
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Membre introuvable"
        )
    
    # Update role
    member.role = new_role
    db.commit()
    
    return {
        "success": True,
        "message": f"Rôle mis à jour vers {new_role.value}",
        "member_id": member.id,
        "new_role": new_role.value
    }


@router.delete("/groups/{group_id}/members/{user_id}", status_code=status.HTTP_200_OK)
def remove_member(
    *,
    db: Session = Depends(get_db),
    group_id: int,
    user_id: int,
    current_user: User = Depends(get_current_active_user)
) -> dict:
    """
    Remove a member from the group.
    Admins and owners can remove members.
    """
    # Check if current user is admin or owner
    current_role = crud_social_group.get_member_role(db, group_id, current_user.id)
    if current_role not in [GroupMemberRole.ADMIN, GroupMemberRole.OWNER]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs peuvent retirer des membres"
        )
    
    # Can't remove owner
    target_role = crud_social_group.get_member_role(db, group_id, user_id)
    if target_role == GroupMemberRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Le propriétaire du groupe ne peut pas être retiré"
        )
    
    # Remove member
    success = crud_social_group.remove_member(db, group_id, user_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Membre introuvable"
        )
    
    return {
        "success": True,
        "message": "Membre retiré du groupe"
    }
