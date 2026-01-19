"""CRUD operations for Role and Permission management."""
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.models.user import Role, Permission, role_permissions


class CRUDPermission:
    """CRUD operations for Permission model."""
    
    def get(self, db: Session, id: int) -> Optional[Permission]:
        return db.query(Permission).filter(Permission.id == id).first()
    
    def get_by_name(self, db: Session, name: str) -> Optional[Permission]:
        return db.query(Permission).filter(Permission.name == name).first()
    
    def get_multi(
        self, db: Session, *, skip: int = 0, limit: int = 10, category: Optional[str] = None
    ) -> List[Permission]:
        query = db.query(Permission)
        if category:
            query = query.filter(Permission.category == category)
        return query.offset(skip).limit(limit).all()
    
    def get_all(self, db: Session) -> List[Permission]:
        return db.query(Permission).all()
    
    def create(
        self, db: Session, *, name: str, description: Optional[str] = None, category: Optional[str] = None
    ) -> Permission:
        db_obj = Permission(name=name, description=description, category=category)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def update(
        self, db: Session, *, db_obj: Permission, name: Optional[str] = None, 
        description: Optional[str] = None, category: Optional[str] = None
    ) -> Permission:
        if name is not None:
            db_obj.name = name
        if description is not None:
            db_obj.description = description
        if category is not None:
            db_obj.category = category
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def delete(self, db: Session, *, id: int) -> Optional[Permission]:
        obj = self.get(db, id)
        if obj:
            db.delete(obj)
            db.commit()
        return obj


class CRUDRole:
    """CRUD operations for Role model."""
    
    def get(self, db: Session, id: int) -> Optional[Role]:
        return db.query(Role).filter(Role.id == id).first()
    
    def get_by_name(self, db: Session, name: str) -> Optional[Role]:
        return db.query(Role).filter(Role.name == name).first()
    
    def get_multi(self, db: Session, *, skip: int = 0, limit: int = 10) -> List[Role]:
        return db.query(Role).offset(skip).limit(limit).all()
    
    def get_all(self, db: Session) -> List[Role]:
        return db.query(Role).all()
    
    def get_system_roles(self, db: Session) -> List[Role]:
        """Get all system roles (non-deletable)."""
        return db.query(Role).filter(Role.is_system == True).all()
    
    def create(
        self, db: Session, *, name: str, description: Optional[str] = None, 
        is_system: bool = False, inherit_from_id: Optional[int] = None
    ) -> Role:
        db_obj = Role(
            name=name, 
            description=description, 
            is_system=is_system,
            inherit_from_id=inherit_from_id
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def update(
        self, db: Session, *, db_obj: Role, name: Optional[str] = None, 
        description: Optional[str] = None, inherit_from_id: Optional[int] = None
    ) -> Role:
        # Don't allow changing name of system roles
        if name is not None and not db_obj.is_system:
            db_obj.name = name
        if description is not None:
            db_obj.description = description
        if inherit_from_id is not None:
            # Prevent circular inheritance
            if inherit_from_id != db_obj.id:
                db_obj.inherit_from_id = inherit_from_id
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def delete(self, db: Session, *, id: int) -> Optional[Role]:
        """Delete a role. System roles cannot be deleted."""
        obj = self.get(db, id)
        if obj and not obj.is_system:
            db.delete(obj)
            db.commit()
            return obj
        return None
    
    def add_permission(self, db: Session, *, role_id: int, permission_id: int) -> Optional[Role]:
        """Add a permission to a role."""
        role = self.get(db, role_id)
        perm = db.query(Permission).filter(Permission.id == permission_id).first()
        
        if role and perm:
            if perm not in role.permissions:
                role.permissions.append(perm)
                db.commit()
                db.refresh(role)
        return role
    
    def add_permission_by_name(self, db: Session, *, role_id: int, permission_name: str) -> Optional[Role]:
        """Add a permission to a role by permission name."""
        role = self.get(db, role_id)
        perm = db.query(Permission).filter(Permission.name == permission_name).first()
        
        if role and perm:
            if perm not in role.permissions:
                role.permissions.append(perm)
                db.commit()
                db.refresh(role)
        return role
    
    def remove_permission(self, db: Session, *, role_id: int, permission_id: int) -> Optional[Role]:
        """Remove a permission from a role."""
        role = self.get(db, role_id)
        perm = db.query(Permission).filter(Permission.id == permission_id).first()
        
        if role and perm:
            if perm in role.permissions:
                role.permissions.remove(perm)
                db.commit()
                db.refresh(role)
        return role
    
    def set_permissions(self, db: Session, *, role_id: int, permission_ids: List[int]) -> Optional[Role]:
        """Set the permissions for a role (replaces existing)."""
        role = self.get(db, role_id)
        if role:
            permissions = db.query(Permission).filter(Permission.id.in_(permission_ids)).all()
            role.permissions = permissions
            db.commit()
            db.refresh(role)
        return role
    
    def get_role_permissions(self, db: Session, role_id: int) -> List[Permission]:
        """Get all permissions for a role (direct only, not inherited)."""
        role = self.get(db, role_id)
        if role:
            return role.permissions
        return []
    
    def get_role_all_permissions(self, db: Session, role_id: int) -> List[str]:
        """Get all permissions for a role including inherited ones."""
        role = self.get(db, role_id)
        if role:
            return role.get_all_permissions()
        return []
    
    def user_has_permission(self, db: Session, user_id: int, permission_name: str) -> bool:
        """Check if a user has a specific permission through their role."""
        from app.models.user import User
        
        user = db.query(User).filter(User.id == user_id).first()
        if not user or not user.role:
            return False
        
        # Admin with 'all' permission can do anything
        if user.role.has_permission('all'):
            return True
        
        return user.role.has_permission(permission_name)
    
    def get_default_user_role(self, db: Session) -> Optional[Role]:
        """Get the default 'user' role."""
        return self.get_by_name(db, 'user')
    
    def get_moderator_role(self, db: Session) -> Optional[Role]:
        """Get the 'moderator' role."""
        return self.get_by_name(db, 'moderator')
    
    def get_admin_role(self, db: Session) -> Optional[Role]:
        """Get the 'admin' role."""
        return self.get_by_name(db, 'admin')


# Singleton instances
permission = CRUDPermission()
role = CRUDRole()
