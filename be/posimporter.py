from evelink.account import Account
from evelink.api import API, APIError
from evelink.cache.sqlite import SqliteCache
from evelink.corp import Corp
from evelink.map import Map

from collections import defaultdict, namedtuple
from datetime import datetime, timedelta
import logging
import sys

from config import ConfigSection
from datastore import Corporation, Tower, Reactor, Reactant, Silo
from eveapi import get_api_key, get_key_config
from staticdata import InvType, InvGroup, InvTypeReaction, InvControlTowerResource, DgmAttributeTypes, DgmTypeAttributes, MapDenormalize

one_hour = timedelta(hours = 1)
_config = ConfigSection('posimporter')
_log = logging.getLogger('sound.posmon.be.main')

def find(predicate, collection):
    if not collection: return None, None
    for idx, elem in enumerate(collection):
        if predicate(elem): return idx, elem
    return None, None

def get_api_keys():
    api_keys = dict()
    for key in _config.get_option('keys').split(','):
        api_keys[key] = get_api_key(key)
    return api_keys

def get_corp_details(key_name):
    _, _, corp_id = get_key_config(key_name)
    corp = Corporation(corp_id)
    _log.info('Getting corp details: %s - %s' % (corp_id, corp.corp_name))
    return corp.alliance_id, corp_id, corp.corp_name, corp.corp_ticker

def get_sov_systems(alliance_id):
    _log.debug('Getting sov systems')
    sov = Map().sov_by_system().result[0]
    return dict(filter(lambda (_,v): v['alliance_id'] == alliance_id, sov.iteritems()))

def build_tower(starbase, detail, location_info, fuel_info, corp_id, corp_name, corp_ticker, sov):
    _log.info('Building tower: %d - %s at %s for %s' % (starbase['id'], location_info['name'], starbase['moon_id'], corp_name))
    moon_info = MapDenormalize.by_id(starbase['moon_id'])
    system_info = moon_info.solar_system
    tower = Tower(pos_id = starbase['id'])
    tower.pos_type_id = starbase['type_id']
    posType = InvType.by_id(tower.pos_type_id)
    tower.pos_type_name = posType.typeName
    tower.pos_name = location_info['name']
    tower.system_id = moon_info.solarSystemID
    tower.system_name = system_info.solarSystemName
    tower.constellation_id = system_info.constellationID
    tower.constellation_name = system_info.constellation.constellationName
    tower.region_id = system_info.regionID
    tower.region_name = system_info.regionName
    tower.planet = moon_info.celestialIndex
    tower.moon = moon_info.orbitIndex
    tower.x = location_info['x']
    tower.y = location_info['y']
    tower.z = location_info['z']
    tower.corp_id = corp_id
    tower.corp_name = corp_name
    tower.corp_ticker = corp_ticker
    tower.next_tick = datetime.utcfromtimestamp(detail['state_ts'])
    tower.status = starbase['state']
    tower.fuel_bay_capacity = int(posType.capacity)
    tower.stront_bay_capacity = int(tower.fuel_bay_capacity / 2.8)
    tower.deleted = False

    sov_bonus = 0.75 if sov.has_key(tower.system_id) else 1.0
    for fuel in fuel_info:
        if fuel.purpose == 4:
            tower.stront_hourly_usage = int(round(fuel.quantity * sov_bonus))
        else:
            tower.fuel_type_id = fuel.resourceTypeID
            tower.fuel_type_name = InvType.by_id(tower.fuel_type_id).typeName
            tower.fuel_hourly_usage = int(round(fuel.quantity * sov_bonus))
    tower.fuel_qty = int(detail['fuel'][tower.fuel_type_id]) if tower.fuel_type_id in detail['fuel'] else 0
    tower.stront_qty = int(detail['fuel'][16275]) if 16275 in detail['fuel'] else 0

    start_time = tower.next_tick
    while tower.next_tick < datetime.utcnow():
        tower.next_tick += one_hour
        advance_fuel_one_tick(tower)

    return tower

def get_locations(corp, ids):
    if not ids:
        return
    try:
        r = corp.locations(ids).result
        return r
    except APIError as e:
        if e.code == '135':
            if len(ids) == 1:
                logging.info('Strange location: %r' % ids[0])
                return {}
            else:
                mid = len(ids) // 2
                d = get_locations(corp, ids[:mid])
                d.update(get_locations(corp, ids[mid:]))
                return d
        else:
                raise

def get_pos_modules(corp, assets):
    _log.debug('Getting POS modules')
    silos = map(lambda silo: silo.typeID, InvGroup.by_id(404).types.all() + InvGroup.by_id(707).types.all())
    guns = map(lambda module: module.typeID, InvGroup.by_id(417).types.all() + InvGroup.by_id(426).types.all() + InvGroup.by_id(430).types.all() + InvGroup.by_id(449).types.all())
    reactors = map(lambda reactor: reactor.typeID, InvGroup.by_id(438).types)
    harvesters = map(lambda harvester: harvester.typeID, InvGroup.by_id(416).types)
    modules = {}
    for location in assets:
        for asset in assets[location]['contents']:
            module_type = asset['item_type_id']
            if module_type in silos or module_type in reactors or module_type in harvesters or module_type in guns:
                modules[asset['id']] = asset
    module_ids = modules.keys()
    assets = defaultdict(list)
    Location = namedtuple('Location', [ 'x', 'y', 'z' ])
    Module = namedtuple('Module', [ 'type', 'module', 'name', 'location' ])
    for chunk in range(0, len(module_ids), 100):
        module_locations = get_locations(corp, module_ids[chunk:chunk+100])
        for id in module_ids[chunk:chunk+100]:
            if id not in module_locations:
                continue
            module = modules[id]
            module_type = ('silo' if module['item_type_id'] in silos
                    else 'reactor' if module['item_type_id'] in reactors
                    else 'harvester' if module['item_type_id'] in harvesters
                    else 'gun' if module['item_type_id'] in guns
                    else 'unknown')
            location_info = module_locations[id]
            locxyz = Location(location_info['x'], location_info['y'], location_info['z'])
            assets[module['location_id']].append(
                    Module(module_type, module, location_info['name'], locxyz))
    return assets

def add_modules_to_tower(tower, modules, timestamp):
    _log.debug('Adding POS modules to tower: %s' % tower.pos_name)
    def belongs_to_tower(module):
        return (abs(module.location.x - tower.x) < 100000
                and abs(module.location.y - tower.y) < 100000
                and abs(module.location.z - tower.z) < 100000)
    tower_modules = filter(belongs_to_tower, modules)
    reactors = filter(lambda module: module.type == 'reactor', tower_modules)
    silos = filter(lambda module: module.type == 'silo', tower_modules)
    tower.harvesters = [module.module['id'] for module in tower_modules
            if module.type == 'harvester']
    guns = filter(lambda module: module.type == 'gun', tower_modules)
    if tower.reactors == None:
        tower.reactors = []
    if tower.silos == None:
        tower.silos = []
    if tower.guns == None:
        tower.guns = []
    update_reactors(tower.reactors, reactors)
    update_silos(tower.silos, silos, tower.pos_type_id)
    update_guns(tower.guns, guns)
    link_reactors_with_silos(tower)
    if tower.status == 'online':
        while timestamp < (tower.next_tick - one_hour):
            timestamp += one_hour
            advance_silos_one_tick(tower)

def update_reactors(datastore, api):
    _log.debug('Updating reactors')
    updated = set()
    for reactor in api:
        reaction_type = None
        if 'contents' in reactor.module and len(reactor.module['contents']) > 0:
            reaction_type = reactor.module['contents'][0]['item_type_id']
        if not reaction_type:
            continue
        index, existing = find(lambda r: r.reactor_id == reactor.module['id'], datastore)
        new = Reactor()
        new.reactor_id = reactor.module['id']
        new.reactor_name = reactor.name
        new.reactor_type_id = reactor.module['item_type_id']
        new.reactor_type_name = InvType.by_id(new.reactor_type_id).typeName
        new.reaction_type_id = reaction_type
        new.reaction_type_name = InvType.by_id(reaction_type).typeName
        new.reactants = []
        for row in InvTypeReaction.by_reaction_id(reaction_type):
            item = InvType.by_id(row.typeID)
            reactant = Reactant()
            reactant.reactant_type_id = row.typeID
            reactant.reactant_type_name = item.typeName
            reactant.reaction_qty = int(row.quantity * (-1 if row.input else 1))
            reactant.item_size = float(item.volume)
            new.reactants.append(reactant)
        updated.add(new.reactor_id)
        if not existing:
            datastore.append(new)
        elif existing.reaction_type_id != reaction_type:
            datastore[index] = new
    for reactor in datastore:
        if reactor.reactor_id not in updated:
            datastore.remove(reactor)

def update_silos(datastore, api, pos_type):
    _log.debug('Updating silos')
    updated = set()
    silo_bonus_attribute = DgmAttributeTypes.by_name('controlTowerSiloCapacityBonus')
    silo_bonus = silo_bonus_attribute.for_type_id(pos_type) or 0
    for silo in api:
        content_type = None
        quantity = 0
        if 'contents' in silo.module and len(silo.module['contents']) > 0:
            content_type = silo.module['contents'][0]['item_type_id']
            quantity = silo.module['contents'][0]['quantity']
        _log.debug('%s, %s, %s', silo.name, content_type, quantity)
        index, existing = find(lambda s: s.silo_id == silo.module['id'], datastore)
        siloItem = InvType.by_id(silo.module['item_type_id'])
        contentItem = InvType.by_id(content_type) if content_type is not None else None
        new = Silo()
        new.silo_id = silo.module['id']
        new.name = silo.name
        new.silo_type_id = silo.module['item_type_id']
        new.silo_type_name = siloItem.typeName
        new.content_type_id = content_type
        if contentItem is not None:
            new.content_type_name = contentItem.typeName
            new.content_size = float(contentItem.volume)
        else:
            new.content_size = 1
        new.input = False
        new.qty = quantity
        new.capacity = int(siloItem.capacity * (1 + silo_bonus / 100))
        new.hourly_usage = 0
        updated.add(new.silo_id)
        if not existing:
            datastore.append(new)
        elif content_type and existing.content_type_id != content_type:
            datastore[index] = new
        else:
            datastore[index].qty = new.qty
    for silo in datastore:
        if silo.silo_id not in updated:
            datastore.remove(silo)

def update_guns(datastore, api):
    _log.debug('Updating guns')
    updated = set()
    for gun in api:
        ammo_type = None
        quantity = 0
        if 'contents' in gun.module and len(gun.module['contents']) > 0:
            ammo_type = gun.module['contents'][0]['item_type_id']
            quantity = gun.module['contents'][0]['quantity']
        _log.debug('%s, %s, %s', gun.name, ammo_type, quantity)
        index, existing = find(lambda g: g.silo_id == gun.module['id'], datastore)
        gunItem = InvType.by_id(gun.module['item_type_id'])
        ammoItem = InvType.by_id(ammo_type) if ammo_type is not None else None
        new = Silo()
        new.silo_id = gun.module['id']
        new.name = gun.name
        new.silo_type_id = gun.module['item_type_id']
        new.silo_type_name = gunItem.typeName
        new.content_type_id = ammo_type
        if ammoItem is not None:
            new.content_type_name = ammoItem.typeName
            new.content_size = float(ammoItem.volume)
        else:
            new.content_size = 1
        new.input = True
        new.qty = quantity
        new.capacity = int(gunItem.capacity)
        new.hourly_usage = 0
        updated.add(new.silo_id)
        if not existing:
            datastore.append(new)
        elif ammo_type and existing.content_type_id != ammo_type:
            datastore[index] = new
        else:
            datastore[index].qty = new.qty
    for gun in datastore:
        if gun.silo_id not in updated:
            datastore.remove(gun)

def advance_fuel_one_tick(tower):
    if tower.status == 'reinforced' and tower.stront_qty < tower.stront_hourly_usage:
        tower.status = 'online'
    elif tower.status == 'reinforced':
        tower.stront_qty -= tower.stront_hourly_usage
    elif tower.status == 'online' and tower.fuel_qty < tower.fuel_hourly_usage:
        tower.status = 'anchored'
    elif tower.status == 'online':
        tower.fuel_qty -= tower.fuel_hourly_usage

def advance_silos_one_tick(tower):
    for silo in tower.silos or []:
        if silo.input and silo.qty < silo.hourly_usage:
            return
    for silo in tower.silos or []:
        silo.qty += silo.hourly_usage
        if silo.volume > silo.capacity:
            silo.qty = int(silo.capacity / silo.content_size)
        elif silo.qty < 0:
            silo.qty -= silo.hourly_usage

def link_reactors_with_silos(tower):
    _log.debug('Linking reactors with silos')
    silos = dict((silo.silo_id, silo) for silo in tower.silos)
    harvesters = set(tower.harvesters)
    # Check existing links, remove links that no longer make sense and ignore
    # silos that already have valid links.
    for reactor in tower.reactors:
        for reactant in reactor.reactants:
            if reactant.connected_to:
                if reactant.connected_to in harvesters:
                    harvesters.remove(reactant.connected_to)
                elif reactant.connected_to not in silos:
                    reactant.connected_to = 0
                elif (silos[reactant.connected_to].content_type_id
                        != reactant.reactant_type_id):
                    reactant.connected_to = 0
                else:
                    silos.pop(reactant.connected_to)
    # Find new links for remaining silos.
    def find_match(silo, reactors):
        for reactor in reactors:
            for reactant in reactor.reactants:
                if (reactant.reactant_type_id == silo.content_type_id
                        and not reactant.connected_to):
                    reactant.connected_to = silo.silo_id
                    silo.input = reactant.reaction_qty < 0
                    silo.hourly_usage = reactant.reaction_qty
                    return True
        return False
    matches = []
    for silo in silos.values():
        if find_match(silo, tower.reactors):
            matches.append(silo.silo_id)
    for silo in matches:
        silos.pop(silo)
    for reactor in tower.reactors:
        for reactant in reactor.reactants:
            if reactant.connected_to == 0 and len(harvesters) > 0:
                reactant.connected_to = harvesters.pop()
    _log.debug('%d silos and %d harvesters left.' % (len(silos), len(harvesters)))
    for silo in silos.values():
        if silo.content_type_id:
            group = InvType.by_id(silo.content_type_id).groupID
            silo.input = False
            if group == 427 and len(harvesters) > 0:
                silo.hourly_usage = 100
                harvesters.pop()
            else:
                silo.hourly_usage = 0

def process(key_name, api_key):
    _log.info('Importing towers for %s' % key_name)
    corp = Corp(api_key)
    alliance_id, corp_id, corp_name, corp_ticker = get_corp_details(key_name)
    sov = get_sov_systems(alliance_id)

    starbases = corp.starbases().result.values()
    starbase_locations = get_locations(corp, map(lambda t: t['id'], starbases))
    towers = defaultdict(list)
    _log.info('Building towers')
    for starbase in starbases:
        try:
            detail = corp.starbase_details(starbase_id = starbase['id']).result
            location_info = starbase_locations[starbase['id']]
            fuel_info = InvControlTowerResource.by_tower_type_id(starbase['type_id'])
            if starbase['moon_id'] == 0:
                _log.debug('Skipping unanchored tower %s.' % location_info['name'])
            else:
                tower = build_tower(starbase, detail, location_info, fuel_info, corp_id, corp_name, corp_ticker, sov)
                towers[tower.system_id].append(tower)
        except APIError as e:
            _log.error("Error processing starbase: %s\n%s" % (starbase['id'], e))

    _log.info('Adding modules')
    _log.debug('Reading corp assets')
    assets = corp.assets()
    assets_timestamp = datetime.utcfromtimestamp(assets.timestamp)
    pos_modules = get_pos_modules(corp, assets.result)
    all_towers = []
    for location in towers:
        modules = pos_modules[location]
        for tower in towers[location]:
            add_modules_to_tower(tower, modules, assets_timestamp)
            all_towers.append(tower)
    _log.info('Writing to datastore')
    Tower.bulk_save(all_towers)
    return set(map(lambda t: t.pos_id, all_towers))

def full_import(keys):
    _log.info('Performing full import at %s' % datetime.utcnow())
    current_ids = set()
    for key_name, key in keys.iteritems():
        current_ids.update(process(key_name, key))
    old_towers = []
    for t in Tower.all():
        if t.pos_id not in current_ids:
            t.deleted = True
            old_towers.append(t)
    _log.info('Removing %d old towers' % len(old_towers))
    Tower.bulk_save(old_towers)

def quick_update():
    _log.info('Performing quick update at %s' % datetime.utcnow())
    timestamp = datetime.utcnow()
    updates = []
    for tower in Tower.all():
        changed = False
        while tower.next_tick < timestamp:
            tower.next_tick += one_hour
            advance_fuel_one_tick(tower)
            advance_silos_one_tick(tower)
            changed = True
        if changed:
            _log.debug("Tower %s updated." % tower.pos_name)
            updates.append(tower)
    Tower.bulk_save(updates)

def print_tower():
    idx = sys.argv.index('print')
    if idx:
        tower = None
        if unicode(sys.argv[idx+1]).isnumeric():
            tower = Tower(long(sys.argv[idx+1]))
        else:
            tower = Tower.lookup_by_name(sys.argv[idx+1])
        if 'raw' in sys.argv:
            resp = tower._lookup()
            print resp.found[0].entity
        else:
            tower.load()
            print tower

if __name__ == "__main__":
    if 'print' in sys.argv:
        print_tower()
    elif 'update' in sys.argv:
        quick_update()
    elif 'import' in sys.argv or datetime.utcnow().minute in [0, 30]:
        keys = get_api_keys()
        full_import(keys)
    else:
        quick_update()

