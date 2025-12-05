from typing import Optional, List
from sqlalchemy import Column, Integer, String, ForeignKey, Float, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base_class import Base


class Continent(Base):
    __tablename__ = "continents"
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    code: Mapped[Optional[str]] = mapped_column(String(10), unique=True, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Relations
    regions: Mapped[List["Region"]] = relationship("Region", back_populates="continent")


class Region(Base):
    __tablename__ = "regions"
    continent_id: Mapped[int] = mapped_column(Integer, ForeignKey("continents.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Relations
    continent: Mapped["Continent"] = relationship("Continent", back_populates="regions")
    countries: Mapped[List["Country"]] = relationship("Country", back_populates="region")


class Country(Base):
    __tablename__ = "countries"
    region_id: Mapped[int] = mapped_column(Integer, ForeignKey("regions.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[Optional[str]] = mapped_column(String(3), unique=True, nullable=True)  # ISO country code
    flag_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Relations
    region: Mapped["Region"] = relationship("Region", back_populates="countries")
    cities: Mapped[List["City"]] = relationship("City", back_populates="country")


class City(Base):
    __tablename__ = "cities"
    country_id: Mapped[int] = mapped_column(Integer, ForeignKey("countries.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    population: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Relations
    country: Mapped["Country"] = relationship("Country", back_populates="cities")
