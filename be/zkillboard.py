import itertools
import json
import logging
import market
import sha
import valuer
import web
from config import ConfigSection
from datastore import KillMail, Victim, Attacker, Item, GroupedItems, ShipClass, Character
from datetime import datetime, timedelta
from staticdata import MapSolarSystem, InvType, InvFlag

_config = ConfigSection('zkillboard')
_log = logging.getLogger('sound.srp.be.zkillboard')
alliance_id = int(_config.get_option('alliance_id'))

def get_kill(kill_id):
    _log.info('Getting killmail by id: %d.' % kill_id)
    url = 'https://zkillboard.com/api/killID/%d/' % kill_id
    content = web.fetch_url(url)
    kills = json.loads(content)
    return kills[0] if kills and len(kills) > 0 else None

def get_crest_hash(kill_id):
    _log.info('Getting killmail by id: %d.' % kill_id)
    url = 'https://zkillboard.com/api/killID/%d/no-items/' % kill_id
    content = web.fetch_url(url)
    kills = json.loads(content)
    km = kills[0] if kills and len(kills) > 0 else None
    victimID = str(int(km['victim']['characterID']) or 'None')
    attackerID = 'None'
    for a in km['attackers']:
        if str(a['finalBlow']) == '1':
            attackerID = str(int(a['characterID']) or 'None')
            break
    shipID = str(km['victim']['shipTypeID'] or 'None')
    dttm = datetime.strptime(km['killTime'], '%Y-%m-%d %H:%M:%S')
    dttm = str(long((dttm - datetime.utcfromtimestamp(0)).total_seconds() * 10000000 + 116444736000000000L))
    _log.info('Generating crest hash for kill %d from %s-%s-%s-%s' % (kill_id, victimID, attackerID, shipID, dttm))
    return sha.new(victimID + attackerID + shipID + dttm).hexdigest()

def get_kills(start_time):
    _log.info('Getting all killmails from start time: %s.' % start_time)
    url_format = 'https://zkillboard.com/api/allianceID/%d/startTime/%s/orderDirection/asc/api-only/page/%d/'
    all_kills = []
    for page in range(10):
        url = url_format % (alliance_id, start_time, page+1)
        content = web.fetch_url(url)
        kills = json.loads(content)
        all_kills = itertools.chain(all_kills, [kill for kill in kills if kill is not None])
        if len(kills) < 200:
            break
    bad = [kill for kill in all_kills if 'killID' not in kill]
    _log.debug('Some kills did not have kill ids: %s' % bad)
    all_kills = [kill for kill in all_kills if 'killID' in kill]
    return list(all_kills)

def get_new_kills(all_kills):
    _log.info('Filtering out kills that are already in the datastore.')
    ids = set([int(kill['killID']) for kill in all_kills if 'killID' in kill])
    old_ids = set([k.kill_id for k in KillMail.load_multi(ids)])
    new_ids = ids.difference(old_ids)
    return filter((lambda k: int(k['killID']) in new_ids), all_kills)

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
    km.kill_id = int(kill['killID'])
    _log.debug('Converting killmail %d.' % km.kill_id)
    km.kill_time = datetime.strptime(kill['killTime'], '%Y-%m-%d %H:%M:%S')
    km.solar_system_id = int(kill['solarSystemID'])
    solar_system = MapSolarSystem.by_id(km.solar_system_id)
    km.solar_system_name = solar_system.solarSystemName
    km.region_name = solar_system.region.regionName
    km.victim = convert_victim(kill['victim'])
    km.victim_id = km.victim.character_id or km.victim.corporation_id
    km.attackers = map(convert_attacker, kill['attackers'])
    km.final_blow = filter(lambda a: a.final_blow, km.attackers)
    if type(km.final_blow) == list and len(km.final_blow) >= 1:
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
    km.srpable = km.loss_mail and km.victim.ship_class not in [ 'Capsule', 'Rookie Ship', 'Shuttle', 'Other' ]
    km.get_crest_hash()
    valuer.set_prices(km)
    return km

def convert_victim(victim):
    v = Victim()
    v.character_id = int(victim['characterID'])
    _log.debug('Converting victim %d.' % v.character_id)
    v.character_name = victim['characterName']
    v.corporation_id = int(victim['corporationID'])
    v.corporation_name = victim['corporationName']
    v.alliance_id = int(victim['allianceID'])
    v.alliance_name = victim['allianceName']
    v.faction_id = int(victim['factionID'])
    v.faction_name = victim['factionName']
    v.damage_taken = int(victim['damageTaken'])
    v.ship_type_id = int(victim['shipTypeID'])
    ship = InvType.by_id(v.ship_type_id)
    if ship:
        v.ship_name = ship.typeName
        v.ship_class = get_ship_class(ship)
    else:
        v.ship_name = 'Unknown'
        v.ship_class = 'Unknown'
    return v

def convert_attacker(attacker):
    a = Attacker()
    a.character_id = int(attacker['characterID'])
    _log.debug('Converting attacker %d.' % a.character_id)
    a.character_name = attacker['characterName']
    a.corporation_id = int(attacker['corporationID'])
    a.corporation_name = attacker['corporationName']
    a.alliance_id = int(attacker['allianceID'])
    a.alliance_name = attacker['allianceName']
    a.faction_id = int(attacker['factionID'])
    a.faction_name = attacker['factionName']
    a.damage_done = int(attacker['damageDone'])
    a.final_blow = attacker['finalBlow'] == '1' or attacker['finalBlow'] == 1
    a.security_status = float(attacker['securityStatus'])
    a.ship_type_id = int(attacker['shipTypeID'])
    a.ship_name = InvType.by_id(a.ship_type_id).typeName
    a.weapon_type_id = int(attacker['weaponTypeID'])
    a.weapon_name = InvType.by_id(a.weapon_type_id).typeName
    return a

def convert_item(item):
    i = Item()
    i.type_id = int(item['typeID'])
    _log.debug('Converting item %d.' % i.type_id)
    i.flag_id = int(item['flag'])
    i.qty_dropped = int(item['qtyDropped'])
    i.qty_destroyed = int(item['qtyDestroyed'])
    i.singleton = item['singleton'] != '0'
    i.bpc = item['singleton'] == '2'
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
    start_time = (datetime.now() - timedelta(look_back_days)).strftime('%Y%m%d%H%M%S')
    kills = get_kills(start_time)
    kills = get_new_kills(kills)
    kills = map(convert_killmail, kills)
    _log.info('Importing %d kills.' % len(kills))
    chars = set()
    for kill in kills:
        kill.save()
        if kill.victim.character_id and kill.victim.character_id not in chars:
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

if __name__ == '__main__':
    import_kills()

