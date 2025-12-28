from datetime import datetime
from typing import TYPE_CHECKING, Optional
from sqlalchemy import String, Boolean, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base

if TYPE_CHECKING:
    from app.models.contest import Contest


class Category(Base):
    __tablename__ = "categories"
    
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relations
    contests: Mapped[list["Contest"]] = relationship("Contest", back_populates="category")
    
    def __repr__(self) -> str:
        return f"<Category {self.id}: {self.name}>"

