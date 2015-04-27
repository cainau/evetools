import sys
import inspect
import logging
from datetime import datetime, timedelta
from config import ConfigSection
from datastore import KillMail, LossMailAttributes, Location
from staticdata import InvType, InvGroup, InvCategory, InvFlag, DgmAttributeTypes, DgmEffects, MapSolarSystem

_config = ConfigSection('analyzers')
_log = logging.getLogger('sound.srp.be.analyzers')

class EmptySlotsAnalyzer(object):

    lowSlotsAttribute = DgmAttributeTypes.by_name('lowSlots')
    medSlotsAttribute = DgmAttributeTypes.by_name('medSlots')
    highSlotsAttribute = DgmAttributeTypes.by_name('hiSlots')
    rigSlotsAttribute = DgmAttributeTypes.by_name('rigSlots')
    turretsAttribute = DgmAttributeTypes.by_name('turretSlotsLeft')
    launchersAttribute = DgmAttributeTypes.by_name('launcherSlotsLeft')
    turretsEffect = DgmEffects.by_name('turretFitted')
    launchersEffect = DgmEffects.by_name('launcherFitted')
    shipCalibrationAttribute = DgmAttributeTypes.by_name('upgradeCapacity')
    rigCalibrationAttribute = DgmAttributeTypes.by_name('upgradeCost')

    def process(self, kill, loss):
        _log.debug('Analyzing empty slots for kill: %d' % kill.kill_id)
        lowSlots = EmptySlotsAnalyzer.lowSlotsAttribute.for_type_id(kill.victim.ship_type_id)
        medSlots = EmptySlotsAnalyzer.medSlotsAttribute.for_type_id(kill.victim.ship_type_id)
        highSlots = EmptySlotsAnalyzer.highSlotsAttribute.for_type_id(kill.victim.ship_type_id)
        rigSlots = EmptySlotsAnalyzer.rigSlotsAttribute.for_type_id(kill.victim.ship_type_id)
        turretSlots = EmptySlotsAnalyzer.turretsAttribute.for_type_id(kill.victim.ship_type_id)
        launcherSlots = EmptySlotsAnalyzer.launchersAttribute.for_type_id(kill.victim.ship_type_id)
        shipCalibration = EmptySlotsAnalyzer.shipCalibrationAttribute.for_type_id(kill.victim.ship_type_id)

        lowSlotFlags = [InvFlag.by_name('LoSlot%d' % i).flagID for i in range(8)]
        medSlotFlags = [InvFlag.by_name('MedSlot%d' % i).flagID for i in range(8)]
        highSlotFlags = [InvFlag.by_name('HiSlot%d' % i).flagID for i in range(8)]
        rigSlotFlags = [InvFlag.by_name('RigSlot%d' % i).flagID for i in range(8)]

        lowSlotItems = [i for i in kill.items if i.flag_id in lowSlotFlags]
        medSlotItems = [i for i in kill.items if i.flag_id in medSlotFlags]
        highSlotItems = [i for i in kill.items if i.flag_id in highSlotFlags]
        rigSlotItems = [i for i in kill.items if i.flag_id in rigSlotFlags]

        turrets = [i for i in highSlotItems
                if EmptySlotsAnalyzer.turretsEffect.for_type_id(i.type_id) is not None]
        launchers = [i for i in highSlotItems
                if EmptySlotsAnalyzer.launchersEffect.for_type_id(i.type_id) is not None]
        rigsCalibration = sum([EmptySlotsAnalyzer.rigCalibrationAttribute.for_type_id(i.type_id)
                for i in rigSlotItems])

        loss.empty_low_slots = len(lowSlotItems) < lowSlots
        loss.empty_med_slots = len(medSlotItems) < medSlots
        loss.empty_rig_slots = len(rigSlotItems) < rigSlots and rigsCalibration < shipCalibration
        loss.empty_hardpoints = len(turrets) < turretSlots and len(launchers) < launcherSlots

class ModulesAnalyzer(object):

    lowSlotFlags = [InvFlag.by_name('LoSlot%d' % i).flagID for i in range(8)]
    medSlotFlags = [InvFlag.by_name('MedSlot%d' % i).flagID for i in range(8)]
    highSlotFlags = [InvFlag.by_name('HiSlot%d' % i).flagID for i in range(8)]

    webs = InvGroup.by_name('Stasis Web').groupID
    points = InvGroup.by_name('Warp Scrambler').groupID
    dic_bubbles = InvGroup.by_name('Interdiction Sphere Launcher').groupID
    hic_bubbles = InvGroup.by_name('Warp Disrupt Field Generator').groupID
    tackle_groups = set([webs, points, dic_bubbles, hic_bubbles])

    exploration_group = InvGroup.by_name('Data Miners').groupID

    shield_booster = InvGroup.by_name('Shield Booster').groupID
    armour_repairer = InvGroup.by_name('Armor Repair Unit').groupID
    local_rep_groups = set([shield_booster, armour_repairer])

    cyno_group = InvGroup.by_name('Cynosural Field').groupID
    
    def process(self, kill, loss):
        _log.debug('Analyzing modules for kill: %d' % kill.kill_id)

        lowSlotItems = [i for i in kill.items if i.flag_id in ModulesAnalyzer.lowSlotFlags]
        medSlotItems = [i for i in kill.items if i.flag_id in ModulesAnalyzer.medSlotFlags]
        highSlotItems = [i for i in kill.items if i.flag_id in ModulesAnalyzer.highSlotFlags]
        fittedItems = lowSlotItems + medSlotItems + highSlotItems

        groups = set([InvType.by_id(item.type_id).groupID for item in fittedItems])
        loss.tackle_mods = bool(groups.intersection(ModulesAnalyzer.tackle_groups))
        loss.exploration_mods = ModulesAnalyzer.exploration_group in groups
        loss.local_rep = bool(groups.intersection(ModulesAnalyzer.local_rep_groups))
        loss.cyno = ModulesAnalyzer.cyno_group in groups

class AttackersAnalyzer(object):

    npc_category = InvCategory.by_name('Entity').categoryID
    ship_category = InvCategory.by_name('Ship').categoryID

    bomber_group = InvGroup.by_name('Stealth Bomber').groupID

    def process(self, kill, loss):
        _log.debug('Analyzing attackers for kill: %d' % kill.kill_id)
        categories = set([InvType.by_id(attacker.ship_type_id).group.categoryID for attacker in kill.attackers
            if attacker.ship_type_id is not None])
        loss.npcs_on_lossmail = AttackersAnalyzer.npc_category in categories
        loss.players_on_lossmail = AttackersAnalyzer.ship_category in categories
        friendlies = set([InvType.by_id(attacker.ship_type_id).groupID for attacker in kill.attackers
                if attacker.alliance_id == kill.victim.alliance_id])
        loss.friendlies_on_lossmail = len(friendlies) > 0
        loss.friendly_bombers_on_lossmail = AttackersAnalyzer.bomber_group in friendlies

class LocationAnalyzer(object):

    def process(self, kill, loss):
        _log.debug('Analyzing location for kill: %d' % kill.kill_id)
        solar_system = MapSolarSystem.by_id(kill.solar_system_id)
        loss.home_region = (Location(solar_system.solarSystemID).full_reimbursement or
                Location(solar_system.constellationID).full_reimbursement or
                Location(solar_system.regionID).full_reimbursement or False)

class ContextAnalyzer(object):

    def process(self, kill, loss):
        _log.debug('Analyzing context for kill: %d' % kill.kill_id)
        back_minutes = long(_config.get_option('context_minutes_back'))
        forward_minutes = long(_config.get_option('context_minutes_forward'))
        systems = [system.solarSystemID for system in MapSolarSystem.by_id(kill.solar_system_id).neighbours]
        systems.insert(0, kill.solar_system_id)
        related = kill.related_kills(back_minutes, forward_minutes, systems)
        for rkill in related:
            if rkill.kill_id == kill.kill_id:
                continue
            if rkill.loss_mail and rkill.victim.character_id != kill.victim.character_id:
                loss.recent_friendly_losses_nearby = True
            elif rkill.loss_mail:
                continue
            attackers = set([a.character_id for a in rkill.attackers if a.alliance_id == kill.victim.alliance_id])
            if kill.victim.character_id in attackers:
                loss.recent_kills = True
            if attackers != set([kill.victim.character_id]):
                loss.recent_friendly_kills_nearby = True

def get_losses():
    look_back_days = int(_config.get_option('look_back_days'))
    _log.info('Getting losses for the last %d days.' % look_back_days)
    start_time = (datetime.now() - timedelta(look_back_days))
    return KillMail.losses_after(start_time)

def get_analyzers():
    _log.info('Getting analyzers.')
    classes = inspect.getmembers(sys.modules[__name__],
            lambda member: inspect.isclass(member) and member.__module__ == __name__)
    return [cls() for name, cls in classes]

def run():
    force = bool(_config.get_option('force'))
    forward_minutes = long(_config.get_option('context_minutes_forward'))
    analyzers = get_analyzers()
    ship_category = InvCategory.by_name('Ship').categoryID
    skip_groups = [
            InvGroup.by_name('Capsule').groupID,
            InvGroup.by_name('Shuttle').groupID,
            InvGroup.by_name('Rookie Ship').groupID
        ]
    for kill in get_losses():
        ship = InvType.by_id(kill.victim.ship_type_id)
        if ship.groupID in skip_groups:
            _log.info('Skipping %s %d' % (kill.victim.ship_class, kill.kill_id))
            continue
        if ship.group.categoryID != ship_category:
            _log.info('Skipping non-ship %d' % kill.kill_id)
            continue
        loss = LossMailAttributes(kill.kill_id)
        age = (datetime.utcnow() - kill.kill_time).total_seconds()
        if loss.ship_type_id is None:
            loss.ship_type_id = kill.victim.ship_type_id
            loss.ship_group_id = ship.groupID
            loss.character_id = kill.victim.character_id
            loss.region_name = kill.region_name
        elif age > (forward_minutes + 60) * 60 and not force:
            # For now, don't re-analyze losses from more than forward_minutes plus an hour ago
            # that have already been analyzed.
            _log.info('Skipping already analyzed loss %d' % kill.kill_id)
            continue
        _log.info('Analyzing loss %s (%d) from %s.' % (kill, kill.kill_id, kill.kill_time))
        if not kill.items:
            kill.items = []
        for analyzer in analyzers:
            if analyzer.process:
                analyzer.process(kill, loss)
        loss.save()

if __name__ == '__main__':
    run()

