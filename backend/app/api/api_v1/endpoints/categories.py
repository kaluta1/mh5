import re
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.db.session import get_db
from app.models.category import Category
from app.models.user import User
from app.schemas.category import Category as CategorySchema
from app.schemas.category import CategoryCreate, CategoryUpdate
from app.core.cache import cache_service

router = APIRouter()
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _normalized_category_data(category_in, *, partial: bool = False) -> dict:
    data = category_in.model_dump(exclude_unset=partial)
    if "name" in data and data["name"] is not None:
        data["name"] = data["name"].strip()
        if not data["name"]:
            raise HTTPException(status_code=422, detail="Category name cannot be empty")
    if "slug" in data and data["slug"] is not None:
        data["slug"] = data["slug"].strip().lower()
        if not _SLUG_RE.fullmatch(data["slug"]):
            raise HTTPException(
                status_code=422,
                detail="Category slug must contain lowercase letters, numbers, and single hyphens",
            )
    if "image_url" in data and data["image_url"] is not None:
        value = data["image_url"].strip()
        if value and not (value.startswith("https://") or value.startswith("/")):
            raise HTTPException(
                status_code=422,
                detail="Category image URL must be HTTPS or an application-relative path",
            )
        data["image_url"] = value or None
    return data


def _find_normalized_conflict(
    db: Session, *, name: str, slug: str, exclude_id: int | None = None
):
    query = db.query(Category).filter(
        (func.lower(func.trim(Category.name)) == name.strip().lower())
        | (func.lower(func.trim(Category.slug)) == slug.strip().lower())
    )
    if exclude_id is not None:
        query = query.filter(Category.id != exclude_id)
    return query.order_by(Category.id.asc()).first()


@router.get("", response_model=List[CategorySchema])
@router.get("/", response_model=List[CategorySchema])
def get_categories(
    *,
    db: Session = Depends(get_db),
    active_only: bool = Query(True, description="Return only active categories"),
) -> List[CategorySchema]:
    cache_key = f"cache:categories:active:{int(active_only)}"
    cached = cache_service.get(cache_key)
    if cached is not None:
        return [CategorySchema.model_validate(row) for row in cached]
    query = db.query(Category)
    if active_only:
        query = query.filter(Category.is_active == True)
    rows = query.order_by(Category.name.asc(), Category.id.asc()).all()
    cache_service.set(
        cache_key,
        [CategorySchema.model_validate(row).model_dump(mode="json") for row in rows],
        ttl=300,
    )
    return rows


@router.get("/{identifier}", response_model=CategorySchema)
def get_category(
    identifier: str,
    *,
    db: Session = Depends(get_db),
    active_only: bool = Query(True),
) -> CategorySchema:
    """Resolve a category deterministically by numeric ID or canonical slug."""
    query = db.query(Category)
    if identifier.isdigit():
        query = query.filter(Category.id == int(identifier))
    else:
        query = query.filter(func.lower(Category.slug) == identifier.strip().lower())
    if active_only:
        query = query.filter(Category.is_active == True)
    category = query.order_by(Category.id.asc()).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    return category


@router.post("", response_model=CategorySchema, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=CategorySchema, status_code=status.HTTP_201_CREATED)
def create_category(
    *, db: Session = Depends(get_db), category_in: CategoryCreate,
    current_user: User = Depends(get_current_active_user),
) -> CategorySchema:
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    data = _normalized_category_data(category_in)
    if _find_normalized_conflict(db, name=data["name"], slug=data["slug"]):
        raise HTTPException(status_code=409, detail="Category name or slug already exists")
    category = Category(**data)
    db.add(category)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Category name or slug already exists")
    db.refresh(category)
    cache_service.delete_pattern("cache:categories:*")
    return category


@router.put("/{category_id}", response_model=CategorySchema)
def update_category(
    *, db: Session = Depends(get_db), category_id: int, category_in: CategoryUpdate,
    current_user: User = Depends(get_current_active_user),
) -> CategorySchema:
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    update_data = _normalized_category_data(category_in, partial=True)
    if "name" in update_data or "slug" in update_data:
        if _find_normalized_conflict(
            db, name=update_data.get("name", category.name),
            slug=update_data.get("slug", category.slug), exclude_id=category_id,
        ):
            raise HTTPException(status_code=409, detail="Category name or slug already exists")
    for field, value in update_data.items():
        setattr(category, field, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Category name or slug already exists")
    db.refresh(category)
    cache_service.delete_pattern("cache:categories:*")
    return category


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(
    *, db: Session = Depends(get_db), category_id: int,
    current_user: User = Depends(get_current_active_user),
) -> None:
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    from app.models.contest import Contest
    contests_count = db.query(Contest).filter(Contest.category_id == category_id).count()
    if contests_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete this category because {contests_count} contest(s) use it. Deactivate it instead.",
        )
    db.delete(category)
    db.commit()
    cache_service.delete_pattern("cache:categories:*")
