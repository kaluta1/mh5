"""API endpoints for Role and Permission management.

Protected permissions (Finance & Payments, administrator management, manual
payments) and the roles that carry them are NOT managed here: they are granted
to a named administrator on purpose (app/scripts/grant_payment_permissions.py).
The Super Admin role is not managed here either: a Super Admin grants or
revokes it (PUT /admin/users/{id}/super-admin).
Nor can this API turn an account that is not an administrator into one; that
is the administrator endpoint, which asks for an explicit permission and the
current password. Whoever may manage roles in general cannot use this API to
give themselves, or anybody else, one of those.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.deps import require_permission, get_current_active_user
from app.crud import role as crud_role, permission as crud_permission
from app.crud.crud_user import user as crud_user
from app.schemas.role import (
    Role, RoleCreate, RoleUpdate, RolePermissionsUpdate, RoleWithAllPermissions,
    Permission, PermissionCreate, PermissionUpdate,
    UserRoleAssignment, UserRoleResponse
)
from app.models.user import Permission as PermissionModel, User
from app.services import admin_security, super_admin

router = APIRouter()

_PROTECTED_NAMES = admin_security.PROTECTED_PERMISSIONS


def _refuse_protected(what: str):
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={
        "code": "PROTECTED_PERMISSION",
        "message": f"{what} is not managed through the role management API."})


def _protect_permission_name(name: Optional[str]) -> None:
    if name and name.strip() in _PROTECTED_NAMES:
        _refuse_protected(f"The permission '{name.strip()}'")


def _protect_permission_ids(db: Session, permission_ids) -> None:
    for permission_id in permission_ids or []:
        perm = crud_permission.get(db, permission_id)
        if perm is not None:
            _protect_permission_name(perm.name)


def _protect_role(role_obj) -> None:
    if role_obj is not None and admin_security.role_has_protected_permission(role_obj):
        _refuse_protected(f"The role '{role_obj.name}'")


def _protect_role_name(name: Optional[str]) -> None:
    if name and name.strip().lower() == super_admin.SUPER_ADMIN_ROLE_NAME:
        _refuse_protected(f"The role name '{super_admin.SUPER_ADMIN_ROLE_NAME}'")


def _all_permission_names(db: Session) -> List[str]:
    """A Super Admin holds every permission there is."""
    return sorted(name for (name,) in db.query(PermissionModel.name).all())


# ============== PERMISSIONS ==============

@router.get("/permissions", response_model=List[Permission])
def get_permissions(
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    category: Optional[str] = Query(None, description="Filter by category (user, moderator, admin)"),
    current_user: User = Depends(require_permission("manage_permissions"))
):
    """Get all permissions. Requires 'manage_permissions' permission."""
    return crud_permission.get_multi(db, skip=skip, limit=limit, category=category)


@router.post("/permissions", response_model=Permission, status_code=status.HTTP_201_CREATED)
def create_permission(
    permission_in: PermissionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manage_permissions"))
):
    """Create a new permission. Requires 'manage_permissions' permission."""
    _protect_permission_name(permission_in.name)
    existing = crud_permission.get_by_name(db, name=permission_in.name)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Permission '{permission_in.name}' already exists"
        )
    return crud_permission.create(
        db, 
        name=permission_in.name, 
        description=permission_in.description,
        category=permission_in.category
    )


@router.put("/permissions/{permission_id}", response_model=Permission)
def update_permission(
    permission_id: int,
    permission_in: PermissionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manage_permissions"))
):
    """Update a permission. Requires 'manage_permissions' permission."""
    perm = crud_permission.get(db, permission_id)
    if not perm:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Permission not found"
        )
    _protect_permission_name(perm.name)
    _protect_permission_name(permission_in.name)
    return crud_permission.update(
        db, 
        db_obj=perm,
        name=permission_in.name,
        description=permission_in.description,
        category=permission_in.category
    )


@router.delete("/permissions/{permission_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_permission(
    permission_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manage_permissions"))
):
    """Delete a permission. Requires 'manage_permissions' permission."""
    perm = crud_permission.get(db, permission_id)
    if not perm:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Permission not found"
        )
    _protect_permission_name(perm.name)
    crud_permission.delete(db, id=permission_id)
    return None


# ============== ROLES ==============

@router.get("/roles", response_model=List[Role])
def get_roles(
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    current_user: User = Depends(require_permission("manage_roles"))
):
    """Get all roles. Requires 'manage_roles' permission."""
    return crud_role.get_multi(db, skip=skip, limit=limit)


@router.get("/roles/{role_id}", response_model=RoleWithAllPermissions)
def get_role(
    role_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manage_roles"))
):
    """Get a specific role with all permissions. Requires 'manage_roles' permission."""
    role_obj = crud_role.get(db, role_id)
    if not role_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found"
        )
    
    # Build response with all permissions
    return RoleWithAllPermissions(
        id=role_obj.id,
        name=role_obj.name,
        description=role_obj.description,
        is_system=role_obj.is_system,
        inherit_from_id=role_obj.inherit_from_id,
        permissions=role_obj.permissions,
        all_permissions=role_obj.get_all_permissions()
    )


@router.post("/roles", response_model=Role, status_code=status.HTTP_201_CREATED)
def create_role(
    role_in: RoleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manage_roles"))
):
    """Create a new role. Requires 'manage_roles' permission."""
    _protect_role_name(role_in.name)
    if role_in.inherit_from_id is not None:
        _protect_role(crud_role.get(db, role_in.inherit_from_id))
    _protect_permission_ids(db, role_in.permission_ids)
    existing = crud_role.get_by_name(db, name=role_in.name)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Role '{role_in.name}' already exists"
        )
    
    # Create the role
    new_role = crud_role.create(
        db,
        name=role_in.name,
        description=role_in.description,
        inherit_from_id=role_in.inherit_from_id
    )
    
    # Add permissions if provided
    if role_in.permission_ids:
        crud_role.set_permissions(db, role_id=new_role.id, permission_ids=role_in.permission_ids)
        db.refresh(new_role)
    
    return new_role


@router.put("/roles/{role_id}", response_model=Role)
def update_role(
    role_id: int,
    role_in: RoleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manage_roles"))
):
    """Update a role. Requires 'manage_roles' permission."""
    role_obj = crud_role.get(db, role_id)
    if not role_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found"
        )
    _protect_role(role_obj)
    if (role_in.name and role_in.name.strip() == admin_security.ADMIN_ROLE_NAME
            and role_obj.name != admin_security.ADMIN_ROLE_NAME):
        _refuse_protected("The role name 'admin'")              # renaming a role into the administrator role
    _protect_role_name(role_in.name)                            # ... or into the Super Admin role
    if role_in.inherit_from_id is not None:
        _protect_role(crud_role.get(db, role_in.inherit_from_id))

    return crud_role.update(
        db,
        db_obj=role_obj,
        name=role_in.name,
        description=role_in.description,
        inherit_from_id=role_in.inherit_from_id
    )


@router.delete("/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_role(
    role_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manage_roles"))
):
    """Delete a role. System roles cannot be deleted. Requires 'manage_roles' permission."""
    role_obj = crud_role.get(db, role_id)
    if not role_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found"
        )
    _protect_role(role_obj)

    if role_obj.is_system:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="System roles cannot be deleted"
        )
    
    # Check if any users have this role
    if role_obj.users:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete role with {len(role_obj.users)} assigned users"
        )
    
    crud_role.delete(db, id=role_id)
    return None


# ============== ROLE PERMISSIONS ==============

@router.put("/roles/{role_id}/permissions", response_model=Role)
def set_role_permissions(
    role_id: int,
    permissions_in: RolePermissionsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manage_roles"))
):
    """Set permissions for a role (replaces existing). Requires 'manage_roles' permission."""
    role_obj = crud_role.get(db, role_id)
    if not role_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found"
        )
    _protect_role(role_obj)
    _protect_permission_ids(db, permissions_in.permission_ids)

    return crud_role.set_permissions(db, role_id=role_id, permission_ids=permissions_in.permission_ids)


@router.post("/roles/{role_id}/permissions/{permission_id}", response_model=Role)
def add_permission_to_role(
    role_id: int,
    permission_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manage_roles"))
):
    """Add a permission to a role. Requires 'manage_roles' permission."""
    role_obj = crud_role.get(db, role_id)
    if not role_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found"
        )
    
    perm = crud_permission.get(db, permission_id)
    if not perm:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Permission not found"
        )
    _protect_role(role_obj)
    _protect_permission_name(perm.name)

    return crud_role.add_permission(db, role_id=role_id, permission_id=permission_id)


@router.delete("/roles/{role_id}/permissions/{permission_id}", response_model=Role)
def remove_permission_from_role(
    role_id: int,
    permission_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manage_roles"))
):
    """Remove a permission from a role. Requires 'manage_roles' permission."""
    role_obj = crud_role.get(db, role_id)
    if not role_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found"
        )
    _protect_role(role_obj)

    return crud_role.remove_permission(db, role_id=role_id, permission_id=permission_id)


# ============== USER ROLE ASSIGNMENT ==============

@router.post("/users/assign-role", response_model=UserRoleResponse)
def assign_role_to_user(
    assignment: UserRoleAssignment,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manage_users"))
):
    """Assign a role to a user. Requires 'manage_users' permission."""
    user_obj = crud_user.get(db, assignment.user_id)
    if not user_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    role_obj = crud_role.get(db, assignment.role_id)
    if not role_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found"
        )
    
    # Neither giving nor taking away a role that carries a protected permission ...
    _protect_role(role_obj)
    _protect_role(user_obj.role)
    # ... and no new administrator through here: a role that makes its holder an
    # administrator (or opens everything) only goes to somebody who already is one.
    if admin_security.role_is_privileged(role_obj) and not (
            admin_security.is_administrator(user_obj) or admin_security.role_is_privileged(user_obj.role)):
        _refuse_protected("Making an account an administrator")

    # Update user's role
    user_obj.role_id = assignment.role_id
    db.commit()
    db.refresh(user_obj)
    
    return UserRoleResponse(
        user_id=user_obj.id,
        username=user_obj.username,
        email=user_obj.email,
        role=role_obj
    )


@router.get("/users/{user_id}/permissions", response_model=List[str])
def get_user_permissions(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("view_users"))
):
    """Get all permissions for a user (including inherited). Requires 'view_users' permission."""
    user_obj = crud_user.get(db, user_id)
    if not user_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    if super_admin.is_super_admin(user_obj):
        return _all_permission_names(db)
    if not user_obj.role:
        return []
    
    return user_obj.role.get_all_permissions()


@router.get("/me/permissions", response_model=List[str])
def get_my_permissions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get all permissions for the current user."""
    if super_admin.is_super_admin(current_user):
        return _all_permission_names(db)
    if not current_user.role:
        return []
    
    return current_user.role.get_all_permissions()
