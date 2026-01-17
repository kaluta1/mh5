"""
Groups API Endpoints for Feed System
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
import secrets
import string

from app.db.session import get_db
from app.api.deps import get_current_active_user
from app.models.user import User
from app.models.social_group import SocialGroup, GroupMember, GroupType, GroupMemberRole
from app.schemas.feed_group import GroupCreate, GroupResponse, GroupMemberResponse

router = APIRouter()


@router.post("", response_model=GroupResponse, status_code=status.HTTP_201_CREATED)
def create_group(
    group_data: GroupCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Create a new social group"""
    try:
        user_id = current_user.id
        
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
            requires_approval=group_data.requires_approval,
            member_count=0,  # Initialize to 0, will be set after adding member
            post_count=0,
            is_active=True,
            is_deleted=False
        )
        
        db.add(group)
        db.flush()  # Flush to get the group ID without committing
        
        # Add creator as owner
        member = GroupMember(
            group_id=group.id,
            user_id=user_id,
            role=GroupMemberRole.OWNER
        )
        db.add(member)
        group.member_count = 1
        
        # Single commit for atomicity
        db.commit()
        db.refresh(group)
        
        # Load creator relationship if available
        try:
            # Eager load creator to avoid lazy loading issues
            from sqlalchemy.orm import joinedload
            group_with_creator = db.query(SocialGroup).options(joinedload(SocialGroup.creator)).filter(SocialGroup.id == group.id).first()
            if group_with_creator:
                group = group_with_creator
        except Exception as load_error:
            print(f"Warning: Could not eager load creator: {load_error}")
            # Continue without creator relationship
        
        # Create response with is_member flag
        group_response = GroupResponse.model_validate(group)
        group_dict = group_response.model_dump()
        group_dict['is_member'] = True
        
        return GroupResponse(**group_dict)
    except Exception as e:
        db.rollback()
        import traceback
        error_details = traceback.format_exc()
        print(f"Error creating group: {error_details}")
        # Return more detailed error for debugging
        error_message = str(e)
        if "duplicate key" in error_message.lower() or "unique constraint" in error_message.lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A group with this name or invite code already exists"
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create group: {error_message}"
        )


@router.get("", response_model=List[GroupResponse])
def list_groups(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    group_type: Optional[GroupType] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """List groups"""
    query = db.query(SocialGroup).filter(SocialGroup.is_deleted == False)
    
    if group_type:
        query = query.filter(SocialGroup.group_type == group_type)
    
    # Eager load creator relationship
    from sqlalchemy.orm import joinedload
    groups = query.options(joinedload(SocialGroup.creator)).offset(skip).limit(limit).all()
    
    # Get user's group memberships for is_member flag
    user_group_ids = set()
    if current_user:
        user_memberships = db.query(GroupMember.group_id).filter(
            GroupMember.user_id == current_user.id
        ).all()
        user_group_ids = {m[0] for m in user_memberships}
    
    result = []
    for g in groups:
        group_response = GroupResponse.model_validate(g)
        group_dict = group_response.model_dump()
        group_dict['is_member'] = g.id in user_group_ids
        result.append(GroupResponse(**group_dict))
    
    return result


@router.get("/{group_id}", response_model=GroupResponse)
def get_group(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
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
    
    # Check if current user is a member
    is_member = False
    if current_user:
        member = db.query(GroupMember).filter(
            GroupMember.group_id == group_id,
            GroupMember.user_id == current_user.id
        ).first()
        is_member = member is not None
    
    # Eager load creator
    from sqlalchemy.orm import joinedload
    group = db.query(SocialGroup).options(joinedload(SocialGroup.creator)).filter(SocialGroup.id == group_id).first()
    
    group_response = GroupResponse.model_validate(group)
    group_dict = group_response.model_dump()
    group_dict['is_member'] = is_member
    
    return GroupResponse(**group_dict)


@router.get("/{group_id}/members", response_model=List[GroupMemberResponse])
def list_group_members(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """List group members"""
    group = db.query(SocialGroup).filter(
        SocialGroup.id == group_id,
        SocialGroup.is_deleted == False
    ).first()
    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group not found"
        )

    from sqlalchemy.orm import joinedload
    members = db.query(GroupMember).options(joinedload(GroupMember.user)).filter(
        GroupMember.group_id == group_id
    ).all()

    return [GroupMemberResponse.model_validate(member) for member in members]


@router.post("/{group_id}/join", status_code=status.HTTP_200_OK)
def join_group(
    group_id: int,
    invite_code: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Join a group"""
    user_id = current_user.id
    
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
def leave_group(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Leave a group"""
    user_id = current_user.id
    
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
