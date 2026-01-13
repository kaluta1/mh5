"""
Groups API Endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
import secrets
import string

from app.core.database import get_db
from app.api.dependencies import get_current_user
from app.models.group import SocialGroup, GroupMember, GroupType, GroupMemberRole
from app.schemas.group import GroupCreate, GroupResponse, GroupMemberResponse

router = APIRouter()


@router.post("", response_model=GroupResponse, status_code=status.HTTP_201_CREATED)
async def create_group(
    group_data: GroupCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Create a new social group"""
    user_id = current_user["user_id"]
    
    # Generate invite code if needed
    invite_code = None
    if group_data.group_type == GroupType.PRIVATE:
        invite_code = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
    
    # Create group
    group = SocialGroup(
        name=group_data.name,
        description=group_data.description,
        group_type=group_data.group_type,
        creator_id=user_id,
        max_members=group_data.max_members,
        invite_code=invite_code,
        requires_approval=group_data.requires_approval
    )
    
    db.add(group)
    db.commit()
    db.refresh(group)
    
    # Add creator as owner
    member = GroupMember(
        group_id=group.id,
        user_id=user_id,
        role=GroupMemberRole.OWNER
    )
    db.add(member)
    group.member_count = 1
    db.commit()
    
    return GroupResponse.from_orm(group)


@router.get("", response_model=List[GroupResponse])
async def list_groups(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    group_type: Optional[GroupType] = Query(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """List groups"""
    query = db.query(SocialGroup).filter(SocialGroup.is_deleted == False)
    
    if group_type:
        query = query.filter(SocialGroup.group_type == group_type)
    
    groups = query.offset(skip).limit(limit).all()
    return [GroupResponse.from_orm(g) for g in groups]


@router.get("/{group_id}", response_model=GroupResponse)
async def get_group(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get group details"""
    group = db.query(SocialGroup).filter(
        SocialGroup.id == group_id,
        SocialGroup.is_deleted == False
    ).first()
    
    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group not found"
        )
    
    return GroupResponse.from_orm(group)


@router.post("/{group_id}/join", status_code=status.HTTP_200_OK)
async def join_group(
    group_id: int,
    invite_code: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Join a group"""
    user_id = current_user["user_id"]
    
    group = db.query(SocialGroup).filter(
        SocialGroup.id == group_id,
        SocialGroup.is_deleted == False
    ).first()
    
    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group not found"
        )
    
    # Check if already a member
    existing = db.query(GroupMember).filter(
        GroupMember.group_id == group_id,
        GroupMember.user_id == user_id
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Already a member of this group"
        )
    
    # Check invite code for private groups
    if group.group_type == GroupType.PRIVATE:
        if not invite_code or invite_code != group.invite_code:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid invite code"
            )
    
    # Check max members
    if group.max_members and group.member_count >= group.max_members:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Group is full"
        )
    
    # Add member
    member = GroupMember(
        group_id=group_id,
        user_id=user_id,
        role=GroupMemberRole.MEMBER
    )
    db.add(member)
    group.member_count += 1
    db.commit()
    
    return {"message": "Successfully joined group"}


@router.delete("/{group_id}/leave", status_code=status.HTTP_200_OK)
async def leave_group(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Leave a group"""
    user_id = current_user["user_id"]
    
    member = db.query(GroupMember).filter(
        GroupMember.group_id == group_id,
        GroupMember.user_id == user_id
    ).first()
    
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not a member of this group"
        )
    
    # Don't allow owner to leave (must transfer ownership first)
    if member.role == GroupMemberRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Owner cannot leave group. Transfer ownership first."
        )
    
    group = db.query(SocialGroup).filter(SocialGroup.id == group_id).first()
    if group:
        group.member_count -= 1
    
    db.delete(member)
    db.commit()
    
    return {"message": "Successfully left group"}


@router.put("/{group_id}", response_model=GroupResponse)
async def update_group(
    group_id: int,
    group_data: GroupCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Update group settings (name, description, type)"""
    user_id = current_user["user_id"]
    
    # Verify ownership or admin role
    group = db.query(SocialGroup).filter(
        SocialGroup.id == group_id,
        SocialGroup.is_deleted == False
    ).first()
    
    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group not found"
        )
    
    # Check if user is owner or admin
    member = db.query(GroupMember).filter(
        GroupMember.group_id == group_id,
        GroupMember.user_id == user_id,
        GroupMember.role.in_([GroupMemberRole.OWNER, GroupMemberRole.ADMIN])
    ).first()
    
    if not member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only group owners and admins can update group settings"
        )
    
    # Update group
    group.name = group_data.name
    group.description = group_data.description
    group.group_type = group_data.group_type
    group.max_members = group_data.max_members
    group.requires_approval = group_data.requires_approval
    
    # Regenerate invite code if group type changed to private
    if group.group_type == GroupType.PRIVATE and not group.invite_code:
        group.invite_code = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
    
    db.commit()
    db.refresh(group)
    
    return GroupResponse.from_orm(group)


@router.get("/{group_id}/members", response_model=List[GroupMemberResponse])
async def get_group_members(
    group_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get list of group members"""
    user_id = current_user["user_id"]
    
    # Verify user is member
    member = db.query(GroupMember).filter(
        GroupMember.group_id == group_id,
        GroupMember.user_id == user_id
    ).first()
    
    if not member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a member of this group"
        )
    
    members = db.query(GroupMember).filter(
        GroupMember.group_id == group_id
    ).offset(skip).limit(limit).all()
    
    return [GroupMemberResponse.from_orm(m) for m in members]


@router.post("/{group_id}/members/{member_id}/ban", status_code=status.HTTP_200_OK)
async def ban_member(
    group_id: int,
    member_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Ban a member from the group"""
    user_id = current_user["user_id"]
    
    # Verify user is owner or admin
    admin_member = db.query(GroupMember).filter(
        GroupMember.group_id == group_id,
        GroupMember.user_id == user_id,
        GroupMember.role.in_([GroupMemberRole.OWNER, GroupMemberRole.ADMIN])
    ).first()
    
    if not admin_member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only group owners and admins can ban members"
        )
    
    # Get member to ban
    member = db.query(GroupMember).filter(
        GroupMember.group_id == group_id,
        GroupMember.user_id == member_id
    ).first()
    
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found"
        )
    
    # Don't allow banning owner
    if member.role == GroupMemberRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot ban group owner"
        )
    
    # Ban member
    member.is_banned = True
    group = db.query(SocialGroup).filter(SocialGroup.id == group_id).first()
    if group:
        group.member_count = max(0, group.member_count - 1)
    
    db.commit()
    
    return {"message": "Member banned successfully"}


@router.post("/{group_id}/members/{member_id}/promote", status_code=status.HTTP_200_OK)
async def promote_member(
    group_id: int,
    member_id: int,
    new_role: GroupMemberRole = Query(GroupMemberRole.MODERATOR),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Promote a member (change role)"""
    user_id = current_user["user_id"]
    
    # Verify user is owner
    owner = db.query(GroupMember).filter(
        GroupMember.group_id == group_id,
        GroupMember.user_id == user_id,
        GroupMember.role == GroupMemberRole.OWNER
    ).first()
    
    if not owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only group owner can promote members"
        )
    
    # Get member to promote
    member = db.query(GroupMember).filter(
        GroupMember.group_id == group_id,
        GroupMember.user_id == member_id
    ).first()
    
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found"
        )
    
    # Don't allow changing owner role
    if member.role == GroupMemberRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change owner role"
        )
    
    # Update role
    member.role = new_role
    db.commit()
    
    return {"message": f"Member promoted to {new_role.value}"}


@router.delete("/{group_id}/members/{member_id}", status_code=status.HTTP_200_OK)
async def remove_member(
    group_id: int,
    member_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Remove a member from the group"""
    user_id = current_user["user_id"]
    
    # Verify user is owner or admin
    admin_member = db.query(GroupMember).filter(
        GroupMember.group_id == group_id,
        GroupMember.user_id == user_id,
        GroupMember.role.in_([GroupMemberRole.OWNER, GroupMemberRole.ADMIN])
    ).first()
    
    if not admin_member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only group owners and admins can remove members"
        )
    
    # Get member to remove
    member = db.query(GroupMember).filter(
        GroupMember.group_id == group_id,
        GroupMember.user_id == member_id
    ).first()
    
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found"
        )
    
    # Don't allow removing owner
    if member.role == GroupMemberRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot remove group owner"
        )
    
    # Remove member
    group = db.query(SocialGroup).filter(SocialGroup.id == group_id).first()
    if group:
        group.member_count = max(0, group.member_count - 1)
    
    db.delete(member)
    db.commit()
    
    return {"message": "Member removed successfully"}