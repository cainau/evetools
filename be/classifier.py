import sys
import logging
from datetime import datetime, timedelta
from config import ConfigSection
from datastore import KillMail, LossMailAttributes
from staticdata import InvType, InvGroup

_config = ConfigSection('classifier')
_log = logging.getLogger('sound.srp.be.classifier')

exploration_ships = [
    InvType.by_name('Heron').typeID,
    InvType.by_name('Imicus').typeID,
    InvType.by_name('Magnate').typeID,
    InvType.by_name('Probe').typeID,
    InvType.by_name('Astero').typeID
    ] + [t.typeID for t in InvGroup.by_name('Covert Ops').types]

bait_ships = [
    InvType.by_name('Procurer').typeID,
    InvType.by_name('Sigil').typeID,
    InvType.by_name('Badger').typeID,
    InvType.by_name('Wreathe').typeID,
    InvType.by_name('Nereus').typeID
    ]

industry_ship_groups = [
    InvGroup.by_name('Mining Frigate'),
    InvGroup.by_name('Mining Barge'),
    InvGroup.by_name('Expedition Frigate'),
    InvGroup.by_name('Exhumer'),
    InvGroup.by_name('Industrial'),
    InvGroup.by_name('Blockade Runner'),
    InvGroup.by_name('Deep Space Transport')
    ]

common_ratting_ships = [
    InvType.by_name('Ishtar'),
    InvType.by_name('Vexor Navy Issue'),
    InvType.by_name('Vexor'),
    InvType.by_name('Oracle'),
    InvType.by_name('Dominix'),
    InvType.by_name('Raven'),
    InvType.by_name('Typhoon'),
    InvType.by_name('Armageddon'),
    InvType.by_name('Tengu'),
    InvType.by_name('Loki')
    ]

def process(kill):
    loss = LossMailAttributes(kill.kill_id)
    if loss.ship_type_id is None:
        return
    if loss.ship_type_id in exploration_ships and loss.exploration_mods:
        kill.suggested_loss_type = 'PVE'
    elif loss.npcs_on_lossmail and not loss.players_on_lossmail:
        kill.suggested_loss_type = 'PVE'
    elif loss.empty_low_slots or loss.empty_med_slots or loss.empty_rig_slots:
        kill.suggested_loss_type = 'Fit'
    elif loss.ship_type_id in bait_ships and loss.recent_kills and loss.tackle_mods and loss.recent_friendly_kills_nearby:
        kill.suggested_loss_type = 'Bait'
    elif loss.ship_group_id in industry_ship_groups:
        kill.suggested_loss_type = 'PVE'
    elif loss.ship_group_id == InvGroup.by_name('Frigate') and loss.cyno:
        kill.suggested_loss_type = 'Cyno'
    elif loss.npcs_on_lossmail and loss.local_rep and not loss.tackle_mods and loss.home_region:
        kill.suggested_loss_type = 'PVE'
    elif loss.tackle_mods and loss.recent_kills and not loss.recent_friendly_kills_nearby and not loss.recent_friendly_losses_nearby:
        kill.suggested_loss_type = 'Solo'
    elif loss.ship_type_id in common_ratting_ships and loss.npcs_on_lossmail and not loss.tackle_mods and loss.home_region:
        kill.suggested_loss_type = 'PVE'
    elif loss.recent_friendly_kills_nearby or loss.recent_friendly_losses_nearby:
        kill.suggested_loss_type = 'Fleet'
    else:
        kill.suggested_loss_type = 'Solo'
    _log.info('Classifying loss %s on %s as %s' % (kill, kill.kill_time, kill.suggested_loss_type))
    kill.save()

def run():
    if '-k' in sys.argv:
        idx = sys.argv.index('-k')
        kill = KillMail(int(sys.argv[idx+1]))
        process(kill)
        return
    look_back_days = int(_config.get_option('look_back_days'))
    _log.info('Classifying killmails for the past %d days.' % look_back_days)
    start_time = datetime.now() - timedelta(look_back_days)
    for kill in KillMail.losses_after(start_time):
        process(kill)

if __name__ == '__main__':
    run()
