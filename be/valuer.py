from datastore import KillMail
from market import get_default_price

def set_prices(kill):
    kill.hull_value = get_default_price(kill.victim.ship_type_id)
    kill.dropped_value = 0
    kill.destroyed_value = 0
    for item in (kill.items or []):
        value = get_default_price(item.type_id)
        if item.bpc:
            value = round(value / 100, 2)
        if item.qty_dropped:
            item.value = item.qty_dropped * value
            kill.dropped_value += item.value
        if item.qty_destroyed:
            item.value = item.qty_destroyed * value
            kill.destroyed_value += item.value
    kill.total_value = kill.hull_value + kill.dropped_value + kill.destroyed_value

