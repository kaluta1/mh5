from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api import deps
from app.crud import crud_geography
from app.schemas.geography import (
    Continent, ContinentCreate, ContinentUpdate, ContinentWithRegions,
    Region, RegionCreate, RegionUpdate, RegionWithCountries,
    Country, CountryCreate, CountryUpdate, CountryWithCities,
    City, CityCreate, CityUpdate,
    GeographyHierarchy
)

router = APIRouter()

# ============ Endpoints géographie ============

# Continents
@router.get("/continents", response_model=List[Continent])
def get_continents(
    db: Session = Depends(deps.get_db),
    skip: int = 0,
    limit: int = 10
):
    """
    Récupérer tous les continents.
    """
    continents = crud_geography.continent.get_multi(db, skip=skip, limit=limit)
    return continents


@router.get("/continents/{continent_id}", response_model=Continent)
def get_continent(
    continent_id: int,
    db: Session = Depends(deps.get_db)
):
    """
    Récupérer un continent par ID.
    """
    continent = crud_geography.continent.get(db=db, id=continent_id)
    if not continent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Continent non trouvé"
        )
    return continent


@router.post("/continents", response_model=Continent, status_code=status.HTTP_201_CREATED)
def create_continent(
    *,
    db: Session = Depends(deps.get_db),
    continent_in: ContinentCreate,
    current_user = Depends(deps.get_current_active_user)
):
    """
    Créer un nouveau continent.
    """
    continent = crud_geography.continent.create(db=db, obj_in=continent_in)
    return continent


# Régions
@router.get("/continents/{continent_id}/regions", response_model=List[Region])
def get_regions_by_continent(
    continent_id: int,
    db: Session = Depends(deps.get_db)
):
    """
    Récupérer toutes les régions d'un continent.
    """
    regions = crud_geography.region.get_by_continent(
        db=db, continent_id=continent_id
    )
    return regions


@router.get("/regions/{region_id}", response_model=Region)
def get_region(
    region_id: int,
    db: Session = Depends(deps.get_db)
):
    """
    Récupérer une région par ID.
    """
    region = crud_geography.region.get(db=db, id=region_id)
    if not region:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Région non trouvée"
        )
    return region


@router.post("/regions", response_model=Region, status_code=status.HTTP_201_CREATED)
def create_region(
    *,
    db: Session = Depends(deps.get_db),
    region_in: RegionCreate,
    current_user = Depends(deps.get_current_active_user)
):
    """
    Créer une nouvelle région.
    """
    region = crud_geography.region.create(db=db, obj_in=region_in)
    return region


# Pays
@router.get("/regions/{region_id}/countries", response_model=List[Country])
def get_countries_by_region(
    region_id: int,
    db: Session = Depends(deps.get_db)
):
    """
    Récupérer tous les pays d'une région.
    """
    countries = crud_geography.country.get_by_region(
        db=db, region_id=region_id
    )
    return countries


@router.get("/countries/{country_id}", response_model=Country)
def get_country(
    country_id: int,
    db: Session = Depends(deps.get_db)
):
    """
    Récupérer un pays par ID.
    """
    country = crud_geography.country.get(db=db, id=country_id)
    if not country:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pays non trouvé"
        )
    return country


@router.get("/countries/code/{country_code}", response_model=Country)
def get_country_by_code(
    country_code: str,
    db: Session = Depends(deps.get_db)
):
    """
    Récupérer un pays par code ISO.
    """
    country = crud_geography.country.get_by_code(db=db, code=country_code)
    if not country:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pays non trouvé"
        )
    return country


@router.post("/countries", response_model=Country, status_code=status.HTTP_201_CREATED)
def create_country(
    *,
    db: Session = Depends(deps.get_db),
    country_in: CountryCreate,
    current_user = Depends(deps.get_current_active_user)
):
    """
    Créer un nouveau pays.
    """
    country = crud_geography.country.create(db=db, obj_in=country_in)
    return country


# Villes
@router.get("/countries/{country_id}/cities", response_model=List[City])
def get_cities_by_country(
    country_id: int,
    db: Session = Depends(deps.get_db)
):
    """
    Récupérer toutes les villes d'un pays.
    """
    cities = crud_geography.city.get_by_country(
        db=db, country_id=country_id
    )
    return cities


@router.get("/cities/{city_id}", response_model=City)
def get_city(
    city_id: int,
    db: Session = Depends(deps.get_db)
):
    """
    Récupérer une ville par ID.
    """
    city = crud_geography.city.get(db=db, id=city_id)
    if not city:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ville non trouvée"
        )
    return city


@router.post("/cities", response_model=City, status_code=status.HTTP_201_CREATED)
def create_city(
    *,
    db: Session = Depends(deps.get_db),
    city_in: CityCreate,
    current_user = Depends(deps.get_current_active_user)
):
    """
    Créer une nouvelle ville.
    """
    city = crud_geography.city.create(db=db, obj_in=city_in)
    return city


@router.get("/search")
def search_locations(
    q: str,
    db: Session = Depends(deps.get_db),
    location_type: Optional[str] = None,
    limit: int = 20
):
    """
    Recherche globale dans toutes les entités géographiques.
    """
    results = crud_geography.search_locations(
        db=db, query=q, location_type=location_type, limit=limit
    )
    return results


@router.get("/hierarchy")
def get_geography_hierarchy(
    db: Session = Depends(deps.get_db),
    city_id: Optional[int] = None,
    country_id: Optional[int] = None,
    region_id: Optional[int] = None,
    continent_id: Optional[int] = None
):
    """
    Récupérer la hiérarchie géographique complète.
    """
    hierarchy = crud_geography.get_geography_hierarchy(
        db=db,
        city_id=city_id,
        country_id=country_id,
        region_id=region_id,
        continent_id=continent_id
    )
    if not hierarchy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hiérarchie géographique non trouvée"
        )
    return hierarchy


@router.post("/initialize", status_code=status.HTTP_201_CREATED)
def initialize_geography_data(
    db: Session = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_user)
):
    """
    Initialiser les données géographiques de base.
    """
    result = crud_geography.initialize_geography_data(db=db)
    return result


@router.get("/continents/with-regions", response_model=List[ContinentWithRegions])
def get_continents_with_regions(
    db: Session = Depends(deps.get_db)
):
    """
    Récupérer tous les continents avec leurs régions.
    """
    continents = crud_geography.continent.get_all_with_regions(db=db)
    return continents
