import json
import logging
import market
import valuer
import web
from config import ConfigSection
from datastore import KillMail, Victim, Attacker, Item, GroupedItems, ShipClass
from datetime import datetime
from staticdata import InvType, InvFlag, MapSolarSystem

_config = ConfigSection('crest')
_log = logging.getLogger('sound.srp.be.crest')
alliance_id = int(_config.get_option('alliance_id'))

def get_killmail(kill):
    url = None
    if type(kill) is str:
        url = kill
    elif type(kill) is KillMail:
        url = kill.crest_url
    elif type(kill) is int:
        kill = KillMail(kill)
        url = kill.crest_url
    if url is None:
        return None
    data = web.fetch_url(url)
    return json.loads(data)

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

def convert_victim(victim):
    v = Victim()
    victimStr = None
    if 'character' in victim:
        v.character_id = victim['character']['id']
        v.character_name = victim['character']['name']
        victimStr = 'character %d' % v.character_id
    if 'corporation' in victim:
        v.corporation_id = victim['corporation']['id']
        v.corporation_name = victim['corporation']['name']
        if victimStr is None:
            victimStr = 'corporation %d' % v.corporation_id
    if 'alliance' in victim:
        v.alliance_id = victim['alliance']['id']
        v.alliance_name = victim['alliance']['name']
    if 'faction' in victim:
        v.faction_id = victim['faction']['id']
        v.faction_name = victim['faction']['name']
    _log.debug('Converting victim: %s' % victimStr)
    v.damage_taken = victim['damageTaken']
    v.ship_type_id = victim['shipType']['id']
    v.ship_name = victim['shipType']['name']
    ship = InvType.by_id(v.ship_type_id)
    v.ship_class = get_ship_class(ship)
    return v

def convert_attacker(attacker):
    a = Attacker()
    attackerStr = None
    if 'character' in attacker:
        a.character_id = attacker['character']['id']
        a.character_name = attacker['character']['name']
        attackerStr = 'character %d' % a.character_id
    if 'corporation' in attacker:
        a.corporation_id = attacker['corporation']['id']
        a.corporation_name = attacker['corporation']['name']
        if attackerStr is None:
            attackerStr = 'corporation %d' % a.corporation_id
    if 'alliance' in attacker:
        a.alliance_id = attacker['alliance']['id']
        a.alliance_name = attacker['alliance']['name']
        if attackerStr is None:
            attackerStr = 'alliance %d' % a.alliance_id
    if 'faction' in attacker:
        a.faction_id = attacker['faction']['id']
        a.faction_name = attacker['faction']['name']
        if attackerStr is None:
            attackerStr = 'faction %d' % a.faction_id
    _log.debug('Converting attacker %s.' % attackerStr)
    a.damage_done = attacker['damageDone']
    a.final_blow = attacker['finalBlow']
    a.security_status = attacker['securityStatus']
    a.ship_type_id = attacker['shipType']['id']
    a.ship_name = attacker['shipType']['name']
    a.weapon_type_id = attacker['weaponType']['id'] if 'weaponType' in attacker else None
    a.weapon_name = attacker['weaponType']['name'] if 'weaponType' in attacker else 'Unknown'
    return a

def convert_item(item):
    i = Item()
    i.type_id = item['itemType']['id']
    _log.debug('Converting item %d.' % i.type_id)
    i.flag_id = item['flag']
    if 'quantityDropped' in item:
        i.qty_dropped = item['quantityDropped']
        i.qty_destroyed = 0
    else:
        i.qty_destroyed = item['quantityDestroyed']
        i.qty_dropped = 0
    i.singleton = 'singleton' in item and str(item['singleton']) != '0'
    i.bpc = 'singleton' in item and str(item['singleton']) == '2'
    i.type_name = item['itemType']['name']
    inv = InvType.by_id(i.type_id)
    i.group_name = inv.group.groupName
    i.category_name = inv.category.categoryName
    flag = InvFlag.by_id(i.flag_id)
    i.flag_name = flag.flagName if flag is not None else 'Unknown'
    return i

def import_kill(kill):
    kill = get_killmail(kill)
    km = KillMail(kill['killID'])
    _log.debug('Converting killmail %d.' % km.kill_id)
    km.kill_time = datetime.strptime(kill['killTime'], '%Y.%m.%d %H:%M:%S')
    km.solar_system_id = kill['solarSystem']['id']
    km.solar_system_name = kill['solarSystem']['name']
    solar_system = MapSolarSystem.by_id(km.solar_system_id)
    km.region_name = solar_system.region.regionName
    km.victim = convert_victim(kill['victim'])
    km.victim_id = km.victim.character_id or km.victim.corporation_id
    km.attackers = map(convert_attacker, kill['attackers'])
    km.final_blow = filter(lambda a: a.final_blow, km.attackers)
    if type(km.final_blow) == list and len(km.final_blow) >= 1:
        km.final_blow = km.final_blow[0]
    if 'items' in kill:
        km.items = map(convert_item, kill['items'])
    elif 'items' in kill['victim']:
        km.items = map(convert_item, kill['victim']['items'])
    km.grouped_items = GroupedItems(km.items)
    km.loss_mail = km.victim.alliance_id == alliance_id
    ship_class = ShipClass(km.victim.ship_class)
    if km.default_payment is None:
        km.default_payment = 0
        if ship_class.fixed_reimbursement > 0:
            km.default_payment = ship_class.fixed_reimbursement
        elif ship_class.market_reimbursement_multiplier > 0:
            price = market.get_default_price(km.victim.ship_type_id)
            km.default_payment = int(round(price * ship_class.market_reimbursement_multiplier, -6) / 1000000)
    km.srpable = km.loss_mail and km.victim.ship_class not in [ 'Capsule', 'Rookie Ship', 'Shuttle', 'Other' ]
    km.get_crest_hash()
    valuer.set_prices(km)
    km.save()
    return km

