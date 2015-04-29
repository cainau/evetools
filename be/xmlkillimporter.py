import crest
import itertools
import logging
import market
import valuer
from config import ConfigSection
from datastore import KillMail, Victim, Attacker, Item, GroupedItems, ShipClass, Character
from datetime import datetime, timedelta
from eveapi import get_api_key
from evelink.corp import Corp
from staticdata import MapSolarSystem, InvType, InvFlag

_config = ConfigSection('xmlkillimporter')
_log = logging.getLogger('sound.srp.be.xmlkillimporter')
alliance_id = int(_config.get_option('alliance_id'))

def get_api_keys():
    return _config.get_option('keys').split(',')

def get_new_kills(all_kills):
    _log.info('Filtering out kills that are already in the datastore.')
    ids = set(all_kills.keys())
    old_ids = set(map((lambda k: k.kill_id), KillMail.load_multi(ids)))
    new_ids = ids.difference(old_ids)
    return [ all_kills[id] for id in new_ids ]

def get_ship_class(ship):
    _log.debug('Getting ship class for %s.' % ship.typeName)
    if ship.category.categoryName != 'Ship':
        return 'Other'
    groupName = ship.group.groupName
    marketGroupName = None if ship.market_group is None else ship.market_group.marketGroupName
    if groupName == 'Combat Battlecruiser' and marketGroupName == 'Navy Faction':
        return 'Navy Battlecruiser'
    if marketGroupName == 'Navy Faction':
        return 'Navy ' + groupName
    if marketGroupName == 'Pirate Faction':
        return 'Pirate ' + groupName
    return groupName

def convert_killmail(kill):
    km = KillMail()
    km.kill_id = kill['id']
    _log.debug('Converting killmail %d.' % km.kill_id)
    km.kill_time = datetime.utcfromtimestamp(kill['time'])
    km.solar_system_id = kill['system_id']
    solar_system = MapSolarSystem.by_id(km.solar_system_id)
    km.solar_system_name = solar_system.solarSystemName
    km.region_name = solar_system.region.regionName
    km.victim = convert_victim(kill['victim'])
    km.victim_id = km.victim.character_id or km.victim.corporation_id
    km.attackers = map(convert_attacker, kill['attackers'].values())
    km.final_blow = filter(lambda a: a.final_blow, km.attackers)
    if km.final_blow is not None and type(km.final_blow) is list and len(km.final_blow) >= 1:
        km.final_blow = km.final_blow[0]
    km.items = map(convert_item, kill['items'])
    km.grouped_items = GroupedItems(km.items)
    km.loss_mail = km.victim.alliance_id == alliance_id
    ship_class = ShipClass(km.victim.ship_class)
    km.default_payment = 0
    if ship_class.fixed_reimbursement > 0:
        km.default_payment = ship_class.fixed_reimbursement
    elif ship_class.market_reimbursement_multiplier > 0:
        price = market.get_default_price(km.victim.ship_type_id)
        km.default_payment = int(round(price * ship_class.market_reimbursement_multiplier, -6) / 1000000)
    km.srpable = km.loss_mail and ship_class not in [ 'Capsule', 'Rookie Ship', 'Shuttle', 'Other' ]
    km.get_crest_hash()
    valuer.set_prices(km)
    return km

def convert_victim(victim):
    v = Victim()
    v.character_id = victim['id']
    _log.debug('Converting victim %d.' % v.character_id)
    v.character_name = victim['name']
    if 'corp' in victim:
        v.corporation_id = victim['corp']['id']
        v.corporation_name = victim['corp']['name']
    if 'alliance' in victim:
        v.alliance_id = victim['alliance']['id']
        v.alliance_name = victim['alliance']['name']
    if 'faction' in victim:
        v.faction_id = victim['faction']['id']
        v.faction_name = victim['faction']['name']
    v.damage_taken = victim['damage']
    v.ship_type_id = victim['ship_type_id']
    ship = InvType.by_id(v.ship_type_id)
    v.ship_name = ship.typeName
    v.ship_class = get_ship_class(ship)
    return v

def convert_attacker(attacker):
    a = Attacker()
    a.character_id = attacker['id']
    _log.debug('Converting attacker %d.' % a.character_id)
    a.character_name = attacker['name']
    if 'corp' in attacker:
        a.corporation_id = attacker['corp']['id']
        a.corporation_name = attacker['corp']['name']
    if 'alliance' in attacker:
        a.alliance_id = attacker['alliance']['id']
        a.alliance_name = attacker['alliance']['name']
    if 'faction' in attacker:
        a.faction_id = attacker['faction']['id']
        a.faction_name = attacker['faction']['name']
    a.damage_done = attacker['damage']
    a.final_blow = attacker['final_blow']
    a.security_status = attacker['sec_status']
    a.ship_type_id = attacker['ship_type_id']
    a.ship_name = InvType.by_id(a.ship_type_id).typeName
    a.weapon_type_id = attacker['weapon_type_id']
    a.weapon_name = InvType.by_id(a.weapon_type_id).typeName
    return a

def convert_item(item):
    i = Item()
    i.type_id = item['id']
    _log.debug('Converting item %d.' % i.type_id)
    i.flag_id = item['flag']
    i.qty_dropped = item['dropped']
    i.qty_destroyed = item['destroyed']
    i.singleton = 'singleton' in item and item['singleton']
    inv = InvType.by_id(i.type_id)
    i.type_name = inv.typeName
    i.group_name = inv.group.groupName
    i.category_name = inv.category.categoryName
    flag = InvFlag.by_id(i.flag_id)
    i.flag_name = flag.flagName if flag is not None else 'Unknown'
    return i

def import_kills():
    look_back_days = int(_config.get_option('look_back_days'))
    _log.info('Importing new killmails for the past %d days.' % look_back_days)
    start_time = datetime.now() - timedelta(look_back_days)
    keys = get_api_keys()
    fixers = []
    chars = set()
    for key in keys:
        _log.info('Getting latest killmails for key %s.' % key)
        key = get_api_key(key)
        corp = Corp(key)
        kills = corp.kills().result
        while kills != None:
            minId = min(kills.keys())
            minDate = datetime.utcfromtimestamp(kills[minId]['time'])
            kills = get_new_kills(kills)
            kills = map(convert_killmail, kills)
            _log.info('Importing %d kills.' % len(kills))
            for kill in kills:
                kill.save()
                if kill.final_blow is None:
                    fixers.append(crest)
                if kill.loss_mail and kill.victim.character_id and kill.victim.character_id not in chars:
                    chars.add(kill.victim.character_id)
                    c = Character(kill.victim.character_id)
                    c.character_name = kill.victim.character_name
                    c.corp_id = kill.victim.corporation_id
                    c.corp_name = kill.victim.corporation_name
                    c.alliance_id = kill.victim.alliance_id
                    c.alliance_name = kill.victim.alliance_name
                    if c.declined_srp is None:
                        c.declined_srp = False
                    c.save()
            if minDate > start_time:
                kills = corp.kills(before_kill = minId).result
            else:
                kills = None
    for km in fixers:
        crest.import_kill(km)

if __name__ == '__main__':
    import_kills()

