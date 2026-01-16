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
