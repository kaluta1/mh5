from typing import Optional, List
from pydantic import BaseModel, ConfigDict
from datetime import datetime


# Continent schemas
class ContinentBase(BaseModel):
    name: str
    code: Optional[str] = None


class ContinentCreate(BaseModel):
    name: str
    code: Optional[str] = None


class ContinentUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None


class Continent(ContinentBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    created_at: Optional[datetime] = None


# Region schemas
class RegionBase(BaseModel):
    continent_id: int
    name: str
    code: Optional[str] = None


class RegionCreate(BaseModel):
    continent_id: int
    name: str
    code: Optional[str] = None


class RegionUpdate(BaseModel):
    continent_id: Optional[int] = None
    name: Optional[str] = None
    code: Optional[str] = None


class Region(RegionBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    created_at: Optional[datetime] = None
    continent: Optional[Continent] = None


# Country schemas
class CountryBase(BaseModel):
    region_id: int
    name: str
    code: Optional[str] = None


class CountryCreate(BaseModel):
    region_id: int
    name: str
    code: Optional[str] = None


class CountryUpdate(BaseModel):
    region_id: Optional[int] = None
    name: Optional[str] = None
    code: Optional[str] = None


class Country(CountryBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    created_at: Optional[datetime] = None
    region: Optional[Region] = None


# City schemas
class CityBase(BaseModel):
    country_id: int
    name: str
    state_province: Optional[str] = None


class CityCreate(CityBase):
    pass


class CityUpdate(BaseModel):
    country_id: Optional[int] = None
    name: Optional[str] = None
    state_province: Optional[str] = None


class City(CityBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    created_at: Optional[datetime] = None
    country: Optional[Country] = None


# Response schemas with nested data
class ContinentWithRegions(Continent):
    regions: List[Region] = []


class RegionWithCountries(Region):
    countries: List[Country] = []


class CountryWithCities(Country):
    cities: List[City] = []


class GeographyHierarchy(BaseModel):
    """Schema pour afficher la hiérarchie géographique complète"""
    continent: Continent
    region: Optional[Region] = None
    country: Optional[Country] = None
    city: Optional[City] = None
