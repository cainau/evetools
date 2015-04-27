import logging
from beaker.cache import CacheManager
from beaker.util import parse_cache_config_options
from config import ConfigSection
from sqlalchemy import *
from sqlalchemy.orm import create_session
from sqlalchemy.ext.declarative import declarative_base

_config = ConfigSection('staticdata')
_log = logging.getLogger('sound.srp.be.staticdata')

Base = declarative_base()
engine = create_engine(_config.get_option('connection_string'))
metadata = MetaData(bind = engine)
session = create_session(bind = engine)
cache = CacheManager(**parse_cache_config_options(
    { 'cache.type': _config.get_option('cache_type') }))

class InvType(Base):
    __table__ = Table('invTypes', metadata, autoload=True)

    @staticmethod
    @cache.cache('InvType.by_id')
    def by_id(type_id):
        _log.debug('Get InvType by id: %d' % type_id)
        return session.query(InvType).filter_by(typeID = type_id).first()

    @staticmethod
    @cache.cache('InvType.by_name')
    def by_name(type_name):
        _log.debug('Get InvType by name: %s' % type_name)
        return session.query(InvType).filter_by(typeName = type_name).first()

    @staticmethod
    @cache.cache('InvType.by_group_id')
    def by_group_id(group_id):
        _log.debug('Get InvTypes by group: %d' % group_id)
        return session.query(InvType).filter_by(groupID = group_id)

    def __repr__(self):
        return 'InvType.by_id(%d)' % self.typeID

    def __str__(self):
        return self.typeName

    @property
    def group(self):
        _log.debug('Get InvGroup for InvType %s' % self)
        return InvGroup.by_id(self.groupID)

    @property
    def category(self):
        _log.debug('Get InvCategory for InvType %s' % self)
        return self.group.category

    @property
    def market_group(self):
        _log.debug('Get InvMarketGroup for InvType %s' % self)
        if self.marketGroupID is None:
            _log.debug('No market group for InvType %s' % self)
            return None
        return InvMarketGroup.by_id(self.marketGroupID)

class InvGroup(Base):
    __table__ = Table('invGroups', metadata, autoload=True)

    @staticmethod
    @cache.cache('InvGroup.by_id')
    def by_id(group_id):
        _log.debug('Get InvGroup by id: %d' % group_id)
        return session.query(InvGroup).filter_by(groupID = group_id).first()

    @staticmethod
    @cache.cache('InvGroup.by_name')
    def by_name(group_name):
        _log.debug('Get InvGroup by name: %s' % group_name)
        return session.query(InvGroup).filter_by(groupName = group_name).first()

    @staticmethod
    @cache.cache('InvGroup.by_category_id')
    def by_category_id(category_id):
        _log.debug('Get InvGroups by category: %d' % category_id)
        return session.query(InvGroup).filter_by(categoryID = category_id)

    def __repr__(self):
        return 'InvGroup.by_id(%d)' % self.groupID

    def __str__(self):
        return self.groupName

    @property
    def category(self):
        _log.debug('Get InvCategory for InvGroup %s' % self)
        return InvCategory.by_id(self.categoryID)

    @property
    def types(self):
        _log.debug('Get child InvTypes for InvGroup %s' % self)
        return InvType.by_group_id(self.groupID)

class InvCategory(Base):
    __table__ = Table('invCategories', metadata, autoload=True)

    @staticmethod
    @cache.cache('InvCategory.by_id')
    def by_id(category_id):
        _log.debug('Get InvCategory by id: %d' % category_id)
        return session.query(InvCategory).filter_by(categoryID = category_id).first()

    @staticmethod
    @cache.cache('InvCategory.by_name')
    def by_name(category_name):
        _log.debug('Get InvCategory by name: %s' % category_name)
        return session.query(InvCategory).filter_by(categoryName = category_name).first()

    def __repr__(self):
        return 'InvCategory.by_id(%d)' % self.categoryID

    def __str__(self):
        return self.categoryName

    @property
    def groups(self):
        _log.debug('Get child InvGroups for InvCategory %s' % self)
        return InvGroup.by_category_id(self.categoryID)

class InvFlag(Base):
    __table__ = Table('invFlags', metadata, autoload=True)

    @staticmethod
    @cache.cache('InvFlag.by_id')
    def by_id(flag_id):
        _log.debug('Get InvFlag by id: %d' % flag_id)
        return session.query(InvFlag).filter_by(flagID = flag_id).first()

    @staticmethod
    @cache.cache('InvFlag.by_name')
    def by_name(flag_name):
        _log.debug('Get InvFlag by name: %s' % flag_name)
        return session.query(InvFlag).filter_by(flagName = flag_name).first()

    def __repr__(self):
        return 'InvFlag.by_id(%d)' % self.flagID

    def __str__(self):
        return self.flagName

class InvMarketGroup(Base):
    __table__ = Table('invMarketGroups', metadata, autoload=True)

    @staticmethod
    @cache.cache('InvMarketGroup.by_id')
    def by_id(market_group_id):
        _log.debug('Get InvMarketGroup by id: %d' % market_group_id)
        return session.query(InvMarketGroup).filter_by(marketGroupID = market_group_id).first()

    @staticmethod
    @cache.cache('InvMarketGroup.by_name')
    def by_name(market_group_name):
        _log.debug('Get InvMarketGroup by name: %s' % market_group_name)
        return session.query(InvMarketGroup).filter_by(marketGroupName = market_group_name).first()

    def __repr__(self):
        return 'InvMarketGroup.by_id(%d)' % self.marketGroupID

    def __str__(self):
        return self.marketGroupName

    @property
    def parent(self):
        _log.debug('Get parent InvMarketGroup for InvMarketGroup %s' % self)
        if self.parentGroupID:
            return InvMarketGroup.by_id(self.parentGroupID)

class InvTypeReaction(Base):
    __table__ = Table('invTypeReactions', metadata, autoload=True)

    @staticmethod
    @cache.cache('InvTypeReaction.by_reaction_id')
    def by_reaction_id(reaction_id):
        _log.debug('Get InvTypeReactions by reaction type: %d' % reaction_id)
        return session.query(InvTypeReaction).filter_by(reactionTypeID = reaction_id)

    @property
    def reaction_type(self):
        _log.debug('Get reaction InvType for InvTypeReaction %d' % self.reactionTypeID)
        if self.reactionTypeID:
            return InvType.by_id(self.reactionTypeID)

    @property
    def reactant_type(self):
        _log.debug('Get reactant InvType %d for InvTypeReaction %d' % (self.typeID, self.reactionTypeID))
        if self.typeID:
            return InvType.by_id(self.typeID)

class InvControlTowerResource(Base):
    __table__ = Table('invControlTowerResources', metadata, autoload=True)

    @staticmethod
    @cache.cache('InvControlTowerResource.by_tower_type_id')
    def by_tower_type_id(tower_id):
        _log.debug('Get InvControlTowerResource by tower type: %d' % tower_id)
        return session.query(InvControlTowerResource).filter_by(controlTowerTypeID = tower_id, minSecurityLevel = None)

    @property
    def tower_type(self):
        _log.debug('Get tower InvType for InvControlTowerResource %d' % self.controlTowerTypeID)
        if self.controlTowerTypeID:
            return InvType.by_id(self.controlTowerTypeID)

    @property
    def resource_type(self):
        _log.debug('Get resource InvType %d for InvControlTowerResource %d' % (self.resourceTypeID, self.controlTowerTypeID))
        if self.resourceTypeID:
            return InvType.by_id(self.resourceTypeID)

class MapRegion(Base):
    __table__ = Table('mapRegions', metadata, autoload=True)

    @staticmethod
    @cache.cache('MapRegion.by_id')
    def by_id(region_id):
        _log.debug('Get MapRegion by id: %d' % region_id)
        return session.query(MapRegion).filter_by(regionID = region_id).first()

    @staticmethod
    @cache.cache('MapRegion.by_name')
    def by_name(region_name):
        _log.debug('Get MapRegion by name: %s' % region_name)
        return session.query(MapRegion).filter_by(regionName = region_name).first()

    def __repr__(self):
        return 'MapRegion.by_id(%d)' % self.regionID

    def __str__(self):
        return self.regionName

class MapConstellation(Base):
    __table__ = Table('mapConstellations', metadata, autoload=True)

    @staticmethod
    @cache.cache('MapConstellation.by_id')
    def by_id(constellation_id):
        _log.debug('Get MapConstellation by id: %d' % constellation_id)
        return session.query(MapConstellation).filter_by(constellationID = constellation_id).first()

    @staticmethod
    @cache.cache('MapConstellation.by_name')
    def by_name(constellation_name):
        _log.debug('Get MapConstellation by name: %s' % constellation_name)
        return session.query(MapConstellation).filter_by(constellationName = constellation_name).first()

    def __repr__(self):
        return 'MapConstellation.by_id(%d)' % self.constellationID

    def __str__(self):
        return self.constellationName

    @property
    def region(self):
        _log.debug('Get MapRegion for MapConstellation %s' % self)
        return MapRegion.by_id(self.regionID)

class MapSolarSystem(Base):
    __table__ = Table('mapSolarSystems', metadata, autoload=True)

    @staticmethod
    @cache.cache('MapSolarSystem.by_id')
    def by_id(system_id):
        _log.debug('Get MapSolarSystem by id: %d' % system_id)
        return session.query(MapSolarSystem).filter_by(solarSystemID = system_id).first()

    @staticmethod
    @cache.cache('MapSolarSystem.by_name')
    def by_name(system_name):
        _log.debug('Get MapSolarSystem by name: %s' % system_name)
        return session.query(MapSolarSystem).filter_by(solarSystemName = system_name).first()

    def __repr__(self):
        return 'MapSolarSystem.by_id(%d)' % self.solarSystemID

    def __str__(self):
        return self.solarSystemName

    @property
    def constellation(self):
        _log.debug('Get MapConstellation for MapSolarSystem %s' % self)
        return MapConstellation.by_id(self.constellationID)

    @property
    def region(self):
        _log.debug('Get MapRegion for MapSolarSystem %s' % self)
        return MapRegion.by_id(self.regionID)

    @property
    def neighbours(self):
        _log.debug('Get neighbouring systems for MapSolarSystem %s' % self)
        return [MapSolarSystem.by_id(jump.toSolarSystemID) for jump in MapSolarSystemJumps.by_id(self.solarSystemID)]

class MapSolarSystemJumps(Base):
    __table__ = Table('mapSolarSystemJumps', metadata, autoload=True)

    @staticmethod
    @cache.cache('MapSolarSystemJumps.by_id')
    def by_id(system_id):
        _log.debug('Get MapSolarSystemJumps by solar system id: %d' % system_id)
        return session.query(MapSolarSystemJumps).filter_by(fromSolarSystemID = system_id)

class MapDenormalize(Base):
    __table__ = Table('mapDenormalize', metadata, autoload=True)

    @staticmethod
    @cache.cache('MapDenormalize.by_id')
    def by_id(item_id):
        _log.debug('Get MapDenormalize by id: %d' % item_id)
        return session.query(MapDenormalize).filter_by(itemID = item_id).first()

    @property
    def type(self):
        _log.debug('Get InvType for MapDenormalize %d' % self.itemID)
        if self.typeID:
            return InvType.by_id(self.typeID)

    @property
    def group(self):
        _log.debug('Get InvGroup for MapDenormalize %d' % self.itemID)
        if self.groupID:
            return InvGroup.by_id(self.groupID)

    @property
    def solar_system(self):
        _log.debug('Get MapSolarSystem for MapDenormalize %d' % self.itemID)
        if self.solarSystemID:
            return MapSolarSystem.by_id(self.solarSystemID)

    @property
    def constellation(self):
        _log.debug('Get MapConstellation for MapDenormalize %d' % self.itemID)
        if self.constellationID:
            return MapConstellation.by_id(self.constellationID)

    @property
    def region(self):
        _log.debug('Get MapRegion for MapDenormalize %d' % self.itemID)
        if self.regionID:
            return MapRegion.by_id(self.regionID)

    @property
    def orbital_parent(self):
        _log.debug('Get parent MapDenormalize for MapDenormalize %d' % self.itemID)
        if self.orbitID:
            return MapDenormalize.by_id(self.orbitID)

class DgmAttributeTypes(Base):
    __table__ = Table('dgmAttributeTypes', metadata, autoload=True)

    @staticmethod
    @cache.cache('DgmAttributeTypes.by_id')
    def by_id(attribute_id):
        _log.debug('Get DgmAttributeTypes by id: %d' % attribute_id)
        return session.query(DgmAttributeTypes).filter_by(attributeID = attribute_id).first()

    @staticmethod
    @cache.cache('DgmAttributeTypes.by_name')
    def by_name(attribute_name):
        _log.debug('Get DgmAttributeTypes by name: %s' % attribute_name)
        return session.query(DgmAttributeTypes).filter_by(attributeName = attribute_name).first()

    def __repr__(self):
        return 'DgmAttributeTypes.by_id(%d)' % self.attributeID

    def __str__(self):
        return self.attributeName

    def for_type_id(self, type_id):
        return DgmTypeAttributes.by_ids(type_id, self.attributeID)

    def for_type_name(self, type_name):
        return self.for_type_id(InvType.by_name(type_name).typeID)

class DgmTypeAttributes(Base):
    __table__ = Table('dgmTypeAttributes', metadata, autoload=True)

    @staticmethod
    @cache.cache('DgmTypeAttributes.by_ids')
    def by_ids(type_id, attribute_id):
        _log.debug('Get DgmTypeAttributes by ids: %d, %d' % (type_id, attribute_id))
        result = session.query(DgmTypeAttributes).filter_by(
                typeID = type_id, attributeID = attribute_id).first()
        if result:
            return result.valueFloat or result.valueInt
        return None

class DgmEffects(Base):
    __table__ = Table('dgmEffects', metadata, autoload=True)

    @staticmethod
    @cache.cache('DgmEffects.by_id')
    def by_id(effect_id):
        _log.debug('Get DgmEffects by id: %d' % effect_id)
        return session.query(DgmEffects).filter_by(effectID = effect_id).first()

    @staticmethod
    @cache.cache('DgmEffects.by_name')
    def by_name(effect_name):
        _log.debug('Get DgmEffects by name: %s' % effect_name)
        return session.query(DgmEffects).filter_by(effectName = effect_name).first()

    def __repr__(self):
        return 'DgmEffects.by_id(%d)' % self.effectID

    def __str__(self):
        return self.effectName

    def for_type_id(self, type_id):
        return DgmTypeEffects.by_ids(type_id, self.effectID)

    def for_type_name(self, type_name):
        return self.for_type_id(InvType.by_name(type_name).typeID)

class DgmTypeEffects(Base):
    __table__ = Table('dgmTypeEffects', metadata, autoload=True)

    @staticmethod
    @cache.cache('DgmTypeEffects.by_ids')
    def by_ids(type_id, effect_id):
        _log.debug('Get DgmTypeEffects by ids: %d, %d' % (type_id, effect_id))
        result = session.query(DgmTypeEffects).filter_by(
                typeID = type_id, effectID = effect_id).first()
        if result:
            return result.isDefault
        return None

