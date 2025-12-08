"""Pydantic schemas for Role and Permission management."""
from typing import Optional, List
from pydantic import BaseModel


# Permission schemas
class PermissionBase(BaseModel):
    name: str
    description: Optional[str] = None
    category: Optional[str] = None


class PermissionCreate(PermissionBase):
    pass


class PermissionUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None


class Permission(PermissionBase):
    id: int

    class Config:
        from_attributes = True


# Role schemas
class RoleBase(BaseModel):
    name: str
    description: Optional[str] = None


class RoleCreate(RoleBase):
    inherit_from_id: Optional[int] = None
    permission_ids: Optional[List[int]] = None


class RoleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    inherit_from_id: Optional[int] = None


class RolePermissionsUpdate(BaseModel):
    """Schema for updating role permissions."""
    permission_ids: List[int]


class Role(RoleBase):
    id: int
    is_system: bool
    inherit_from_id: Optional[int] = None
    permissions: List[Permission] = []

    class Config:
        from_attributes = True


class RoleWithAllPermissions(Role):
    """Role with all permissions including inherited ones."""
    all_permissions: List[str] = []


# User role assignment
class UserRoleAssignment(BaseModel):
    user_id: int
    role_id: int


class UserRoleResponse(BaseModel):
    user_id: int
    username: Optional[str]
    email: str
    role: Optional[Role]

    class Config:
        from_attributes = True
