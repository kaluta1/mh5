from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.db.session import get_db
from app.models.user import User
from app.models.category import Category
from app.schemas.category import CategoryCreate, CategoryUpdate, Category as CategorySchema

router = APIRouter()


@router.get("/", response_model=List[CategorySchema])
def get_categories(
    *,
    db: Session = Depends(get_db),
    active_only: bool = Query(True, description="Filtrer uniquement les catégories actives")
) -> List[CategorySchema]:
    """Récupère toutes les catégories"""
    query = db.query(Category)
    if active_only:
        query = query.filter(Category.is_active == True)
    categories = query.order_by(Category.name).all()
    return categories


@router.post("/", response_model=CategorySchema, status_code=status.HTTP_201_CREATED)
def create_category(
    *,
    db: Session = Depends(get_db),
    category_in: CategoryCreate,
    current_user: User = Depends(get_current_active_user),
) -> CategorySchema:
    """Créer une nouvelle catégorie (admin seulement)"""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission insuffisante pour créer une catégorie"
        )
    
    # Vérifier si une catégorie avec le même nom ou slug existe déjà
    existing = db.query(Category).filter(
        (Category.name == category_in.name) | (Category.slug == category_in.slug)
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Une catégorie avec le nom '{category_in.name}' ou le slug '{category_in.slug}' existe déjà"
        )
    
    category = Category(**category_in.dict())
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


@router.put("/{category_id}", response_model=CategorySchema)
def update_category(
    *,
    db: Session = Depends(get_db),
    category_id: int,
    category_in: CategoryUpdate,
    current_user: User = Depends(get_current_active_user),
) -> CategorySchema:
    """Mettre à jour une catégorie (admin seulement)"""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission insuffisante pour modifier une catégorie"
        )
    
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Catégorie non trouvée"
        )
    
    # Vérifier les conflits de nom/slug si modifiés
    update_data = category_in.dict(exclude_unset=True)
    if "name" in update_data or "slug" in update_data:
        existing = db.query(Category).filter(
            Category.id != category_id,
            ((Category.name == update_data.get("name", category.name)) |
             (Category.slug == update_data.get("slug", category.slug)))
        ).first()
        
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Une autre catégorie avec ce nom ou ce slug existe déjà"
            )
    
    for field, value in update_data.items():
        setattr(category, field, value)
    
    db.commit()
    db.refresh(category)
    return category


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(
    *,
    db: Session = Depends(get_db),
    category_id: int,
    current_user: User = Depends(get_current_active_user),
) -> None:
    """Supprimer une catégorie (admin seulement)"""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission insuffisante pour supprimer une catégorie"
        )
    
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Catégorie non trouvée"
        )
    
    # Vérifier si des contests utilisent cette catégorie
    from app.models.contest import Contest
    contests_count = db.query(Contest).filter(Contest.category_id == category_id).count()
    
    if contests_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Impossible de supprimer cette catégorie car {contests_count} contest(s) l'utilise(nt). Désactivez-la plutôt."
        )
    
    db.delete(category)
    db.commit()

