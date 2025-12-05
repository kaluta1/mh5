from typing import Any
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.orm import as_declarative, Mapped, mapped_column
from sqlalchemy import Integer, DateTime, func
from datetime import datetime


@as_declarative()
class Base:
    __name__: str
    
    # Génère automatiquement le nom de la table
    @declared_attr
    def __tablename__(cls) -> str:
        return cls.__name__.lower()
    
    # Champs communs à tous les modèles avec les nouvelles annotations Mapped[]
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
