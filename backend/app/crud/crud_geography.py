from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_

# from app.crud.base import CRUDBase  # Module supprimé - utilisation de classes directes
from app.models.geography import Continent, Region, Country, City
from app.schemas.geography import (
    ContinentCreate, ContinentUpdate,
    RegionCreate, RegionUpdate,
    CountryCreate, CountryUpdate,
    CityCreate, CityUpdate,
    ContinentWithRegions, RegionWithCountries, CountryWithCities,
    GeographyHierarchy
)


class CRUDContinent:
    def get(self, db: Session, id: int) -> Optional[Continent]:
        """Récupérer un continent par son ID"""
        return db.query(Continent).filter(Continent.id == id).first()
    
    def get_multi(self, db: Session, *, skip: int = 0, limit: int = 100) -> List[Continent]:
        """Récupérer plusieurs continents"""
        return db.query(Continent).offset(skip).limit(limit).all()
    
    def create(self, db: Session, *, obj_in: ContinentCreate) -> Continent:
        """Créer un nouveau continent"""
        db_obj = Continent(**obj_in.dict())
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def update(self, db: Session, *, db_obj: Continent, obj_in: ContinentUpdate) -> Continent:
        """Mettre à jour un continent"""
        update_data = obj_in.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def remove(self, db: Session, *, id: int) -> Continent:
        """Supprimer un continent"""
        obj = db.query(Continent).get(id)
        db.delete(obj)
        db.commit()
        return obj

    def get_by_code(self, db: Session, *, code: str) -> Optional[Continent]:
        """Récupérer un continent par son code"""
        return db.query(Continent).filter(Continent.code == code).first()

    def get_with_regions(self, db: Session, continent_id: int) -> Optional[ContinentWithRegions]:
        """Récupérer un continent avec ses régions"""
        continent = db.query(Continent).filter(Continent.id == continent_id).first()
        if not continent:
            return None
        
        regions = db.query(Region).filter(Region.continent_id == continent_id).all()
        
        return ContinentWithRegions(
            id=continent.id,
            name=continent.name,
            code=continent.code,
            created_at=continent.created_at,
            regions=regions
        )

    def get_all_with_regions(self, db: Session) -> List[ContinentWithRegions]:
        """Récupérer tous les continents avec leurs régions"""
        continents = db.query(Continent).all()
        result = []
        
        for continent in continents:
            regions = db.query(Region).filter(Region.continent_id == continent.id).all()
            result.append(ContinentWithRegions(
                id=continent.id,
                name=continent.name,
                code=continent.code,
                created_at=continent.created_at,
                regions=regions
            ))
        
        return result


class CRUDRegion:
    def get(self, db: Session, id: int) -> Optional[Region]:
        """Récupérer une région par son ID"""
        return db.query(Region).filter(Region.id == id).first()
    
    def get_multi(self, db: Session, *, skip: int = 0, limit: int = 100) -> List[Region]:
        """Récupérer plusieurs régions"""
        return db.query(Region).offset(skip).limit(limit).all()
    
    def create(self, db: Session, *, obj_in: RegionCreate) -> Region:
        """Créer une nouvelle région"""
        db_obj = Region(**obj_in.dict())
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def update(self, db: Session, *, db_obj: Region, obj_in: RegionUpdate) -> Region:
        """Mettre à jour une région"""
        update_data = obj_in.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def remove(self, db: Session, *, id: int) -> Region:
        """Supprimer une région"""
        obj = db.query(Region).get(id)
        db.delete(obj)
        db.commit()
        return obj

    def get_by_code(self, db: Session, *, code: str) -> Optional[Region]:
        """Récupérer une région par son code"""
        return db.query(Region).filter(Region.code == code).first()

    def get_by_continent(self, db: Session, *, continent_id: int) -> List[Region]:
        """Récupérer toutes les régions d'un continent"""
        return db.query(Region).filter(Region.continent_id == continent_id).all()

    def get_with_countries(self, db: Session, region_id: int) -> Optional[RegionWithCountries]:
        """Récupérer une région avec ses pays"""
        region = db.query(Region).filter(Region.id == region_id).first()
        if not region:
            return None
        
        countries = db.query(Country).filter(Country.region_id == region_id).all()
        
        return RegionWithCountries(
            id=region.id,
            continent_id=region.continent_id,
            name=region.name,
            code=region.code,
            created_at=region.created_at,
            countries=countries
        )


class CRUDCountry:
    def get(self, db: Session, id: int) -> Optional[Country]:
        """Récupérer un pays par son ID"""
        return db.query(Country).filter(Country.id == id).first()
    
    def get_multi(self, db: Session, *, skip: int = 0, limit: int = 100) -> List[Country]:
        """Récupérer plusieurs pays"""
        return db.query(Country).offset(skip).limit(limit).all()
    
    def create(self, db: Session, *, obj_in: CountryCreate) -> Country:
        """Créer un nouveau pays"""
        db_obj = Country(**obj_in.dict())
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def update(self, db: Session, *, db_obj: Country, obj_in: CountryUpdate) -> Country:
        """Mettre à jour un pays"""
        update_data = obj_in.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def remove(self, db: Session, *, id: int) -> Country:
        """Supprimer un pays"""
        obj = db.query(Country).get(id)
        db.delete(obj)
        db.commit()
        return obj

    def get_by_code(self, db: Session, *, code: str) -> Optional[Country]:
        """Récupérer un pays par son code"""
        return db.query(Country).filter(Country.code == code).first()

    def get_by_region(self, db: Session, *, region_id: int) -> List[Country]:
        """Récupérer tous les pays d'une région"""
        return db.query(Country).filter(Country.region_id == region_id).all()

    def get_with_cities(self, db: Session, country_id: int) -> Optional[CountryWithCities]:
        """Récupérer un pays avec ses villes"""
        country = db.query(Country).filter(Country.id == country_id).first()
        if not country:
            return None
        
        cities = db.query(City).filter(City.country_id == country_id).all()
        
        return CountryWithCities(
            id=country.id,
            region_id=country.region_id,
            name=country.name,
            code=country.code,
            created_at=country.created_at,
            cities=cities
        )

    def search_by_name(self, db: Session, *, name: str) -> List[Country]:
        """Rechercher des pays par nom"""
        return db.query(Country).filter(
            Country.name.ilike(f"%{name}%")
        ).all()


class CRUDCity:
    def get(self, db: Session, id: int) -> Optional[City]:
        """Récupérer une ville par son ID"""
        return db.query(City).filter(City.id == id).first()
    
    def get_multi(self, db: Session, *, skip: int = 0, limit: int = 100) -> List[City]:
        """Récupérer plusieurs villes"""
        return db.query(City).offset(skip).limit(limit).all()
    
    def create(self, db: Session, *, obj_in: CityCreate) -> City:
        """Créer une nouvelle ville"""
        db_obj = City(**obj_in.dict())
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def update(self, db: Session, *, db_obj: City, obj_in: CityUpdate) -> City:
        """Mettre à jour une ville"""
        update_data = obj_in.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def remove(self, db: Session, *, id: int) -> City:
        """Supprimer une ville"""
        obj = db.query(City).get(id)
        db.delete(obj)
        db.commit()
        return obj

    def get_by_country(self, db: Session, *, country_id: int) -> List[City]:
        """Récupérer toutes les villes d'un pays"""
        return db.query(City).filter(City.country_id == country_id).all()

    def get_by_state_province(
        self, 
        db: Session, 
        *, 
        country_id: int, 
        state_province: str
    ) -> List[City]:
        """Récupérer les villes d'une province/état"""
        return db.query(City).filter(
            and_(
                City.country_id == country_id,
                City.state_province == state_province
            )
        ).all()

    def search_by_name(self, db: Session, *, name: str) -> List[City]:
        """Rechercher des villes par nom"""
        return db.query(City).filter(
            City.name.ilike(f"%{name}%")
        ).all()

    def get_major_cities(self, db: Session, *, country_id: int, limit: int = 20) -> List[City]:
        """Récupérer les principales villes d'un pays (par ordre alphabétique)"""
        return db.query(City).filter(
            City.country_id == country_id
        ).order_by(City.name).limit(limit).all()


def get_geography_hierarchy(
    db: Session, 
    *, 
    city_id: Optional[int] = None,
    country_id: Optional[int] = None,
    region_id: Optional[int] = None,
    continent_id: Optional[int] = None
) -> Optional[GeographyHierarchy]:
    """Récupérer la hiérarchie géographique complète"""
    city = None
    country = None
    region = None
    continent = None
    
    if city_id:
        city = db.query(City).filter(City.id == city_id).first()
        if city:
            country_id = city.country_id
    
    if country_id:
        country = db.query(Country).filter(Country.id == country_id).first()
        if country:
            region_id = country.region_id
    
    if region_id:
        region = db.query(Region).filter(Region.id == region_id).first()
        if region:
            continent_id = region.continent_id
    
    if continent_id:
        continent = db.query(Continent).filter(Continent.id == continent_id).first()
    
    if not continent:
        return None
    
    return GeographyHierarchy(
        continent=continent,
        region=region,
        country=country,
        city=city
    )


def search_locations(
    db: Session, 
    *, 
    query: str, 
    location_type: Optional[str] = None,
    limit: int = 20
) -> List[dict]:
    """Recherche globale dans toutes les entités géographiques"""
    results = []
    
    if not location_type or location_type == "continent":
        continents = db.query(Continent).filter(
            Continent.name.ilike(f"%{query}%")
        ).limit(limit).all()
        
        for continent in continents:
            results.append({
                "type": "continent",
                "id": continent.id,
                "name": continent.name,
                "code": continent.code,
                "parent": None
            })
    
    if not location_type or location_type == "region":
        regions = db.query(Region, Continent).join(
            Continent, Region.continent_id == Continent.id
        ).filter(
            Region.name.ilike(f"%{query}%")
        ).limit(limit).all()
        
        for region, continent in regions:
            results.append({
                "type": "region",
                "id": region.id,
                "name": region.name,
                "code": region.code,
                "parent": continent.name
            })
    
    if not location_type or location_type == "country":
        countries = db.query(Country, Region).join(
            Region, Country.region_id == Region.id
        ).filter(
            Country.name.ilike(f"%{query}%")
        ).limit(limit).all()
        
        for country, region in countries:
            results.append({
                "type": "country",
                "id": country.id,
                "name": country.name,
                "code": country.code,
                "parent": region.name
            })
    
    if not location_type or location_type == "city":
        cities = db.query(City, Country).join(
            Country, City.country_id == Country.id
        ).filter(
            City.name.ilike(f"%{query}%")
        ).limit(limit).all()
        
        for city, country in cities:
            results.append({
                "type": "city",
                "id": city.id,
                "name": city.name,
                "state_province": city.state_province,
                "parent": country.name
            })
    
    return results[:limit]


def initialize_geography_data(db: Session):
    """Initialiser les données géographiques de base"""
    # Vérifier si les données existent déjà
    if db.query(Continent).count() > 0:
        return {"message": "Données géographiques déjà initialisées"}
    
    # Continents
    continents_data = [
        {"name": "Afrique", "code": "AF"},
        {"name": "Antarctique", "code": "AN"},
        {"name": "Asie", "code": "AS"},
        {"name": "Europe", "code": "EU"},
        {"name": "Amérique du Nord", "code": "NA"},
        {"name": "Océanie", "code": "OC"},
        {"name": "Amérique du Sud", "code": "SA"}
    ]
    
    continents = {}
    for continent_data in continents_data:
        continent = Continent(**continent_data)
        db.add(continent)
        db.flush()
        continents[continent_data["code"]] = continent
    
    # Régions principales (exemples)
    regions_data = [
        {"continent_code": "NA", "name": "Amérique du Nord", "code": "NAM"},
        {"continent_code": "EU", "name": "Europe de l'Ouest", "code": "WEU"},
        {"continent_code": "EU", "name": "Europe de l'Est", "code": "EEU"},
        {"continent_code": "AS", "name": "Asie de l'Est", "code": "EAS"},
        {"continent_code": "AS", "name": "Asie du Sud-Est", "code": "SEA"},
        {"continent_code": "AF", "name": "Afrique du Nord", "code": "NAF"},
        {"continent_code": "AF", "name": "Afrique Subsaharienne", "code": "SSA"},
        {"continent_code": "SA", "name": "Amérique du Sud", "code": "SAM"},
        {"continent_code": "OC", "name": "Océanie", "code": "OCE"}
    ]
    
    regions = {}
    for region_data in regions_data:
        continent = continents[region_data["continent_code"]]
        region = Region(
            continent_id=continent.id,
            name=region_data["name"],
            code=region_data["code"]
        )
        db.add(region)
        db.flush()
        regions[region_data["code"]] = region
    
    # Pays principaux (exemples)
    countries_data = [
        {"region_code": "NAM", "name": "Canada", "code": "CA"},
        {"region_code": "NAM", "name": "États-Unis", "code": "US"},
        {"region_code": "NAM", "name": "Mexique", "code": "MX"},
        {"region_code": "WEU", "name": "France", "code": "FR"},
        {"region_code": "WEU", "name": "Allemagne", "code": "DE"},
        {"region_code": "WEU", "name": "Royaume-Uni", "code": "GB"},
        {"region_code": "EAS", "name": "Chine", "code": "CN"},
        {"region_code": "EAS", "name": "Japon", "code": "JP"},
        {"region_code": "SEA", "name": "Thaïlande", "code": "TH"},
    ]
    
    countries = {}
    for country_data in countries_data:
        region = regions[country_data["region_code"]]
        country = Country(
            region_id=region.id,
            name=country_data["name"],
            code=country_data["code"]
        )
        db.add(country)
        db.flush()
        countries[country_data["code"]] = country
    
    # Villes principales du Canada (exemple)
    canada_cities = [
        {"name": "Toronto", "state_province": "Ontario"},
        {"name": "Montréal", "state_province": "Québec"},
        {"name": "Vancouver", "state_province": "Colombie-Britannique"},
        {"name": "Calgary", "state_province": "Alberta"},
        {"name": "Ottawa", "state_province": "Ontario"},
        {"name": "Edmonton", "state_province": "Alberta"},
        {"name": "Mississauga", "state_province": "Ontario"},
        {"name": "Winnipeg", "state_province": "Manitoba"},
        {"name": "Québec", "state_province": "Québec"},
        {"name": "Hamilton", "state_province": "Ontario"}
    ]
    
    canada = countries["CA"]
    for city_data in canada_cities:
        city = City(
            country_id=canada.id,
            name=city_data["name"],
            state_province=city_data["state_province"]
        )
        db.add(city)
    
    db.commit()
    return {"message": "Données géographiques initialisées avec succès"}


# Instances CRUD
continent = CRUDContinent()
region = CRUDRegion()
country = CRUDCountry()
city = CRUDCity()
