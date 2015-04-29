import logging
from datetime import datetime, timedelta
from google.appengine.api.modules import get_current_version_name
from google.appengine.ext import ndb

_log = logging.getLogger('sound.model')

class LocalStructuredProperty(ndb.LocalStructuredProperty):
    def _get_for_dict(self, entity):
        value = self._get_value(entity)
        if value is None:
            return None
        elif self._repeated:
            # For some reason, value can be [None] when it should just be [].
            # I've added the ' if is not None' part to the following line to
            # avoid errors trying to call _to_dict() on None.
            # Base implementation is at:
            # https://code.google.com/p/googleappengine/source/browse/trunk/python/google/appengine/ext/ndb/model.py#2162
            # TODO: Either investigate the root cause of the [None] or submit this workaround upstream.
            return [v._to_dict() for v in value if v is not None]
        else:
            return value._to_dict()

class Configuration(ndb.Model):
    _CACHE_TIME = timedelta(minutes = 5)
    _VERSION = get_current_version_name()
    _INSTANCE = None
    _INSTANCE_AGE = None

    client_id = ndb.StringProperty()
    auth_header = ndb.StringProperty()
    base_uri = ndb.StringProperty()
    redirect_uri = ndb.StringProperty()
    scopes = ndb.StringProperty()
    srp_admins = ndb.IntegerProperty(repeated = True)
    srp_payers = ndb.IntegerProperty(repeated = True)
    super_admins = ndb.IntegerProperty(repeated = True)
    pos_admins = ndb.IntegerProperty(repeated = True)
    alliance_id = ndb.IntegerProperty()

    @classmethod
    def get_instance(cls):
        now = datetime.now()
        if not cls._INSTANCE or cls._INSTANCE_AGE + cls._CACHE_TIME < now or cls._INSTANCE.client_id is None:
            _log.info('Loading configuration from datastore.')
            cls._INSTANCE = cls.get_or_insert(cls._VERSION)
            cls._INSTANCE_AGE = now
        return cls._INSTANCE

class Corporation(ndb.Model):
    corp_id = ndb.IntegerProperty()
    corp_name = ndb.StringProperty()
    alliance_id = ndb.IntegerProperty()
    alliance_name = ndb.StringProperty()
    srp = ndb.BooleanProperty()
    corp_ticker = ndb.StringProperty()

class Character(ndb.Model):
    character_id = ndb.IntegerProperty()
    character_name = ndb.StringProperty()
    corp_id = ndb.IntegerProperty()
    corp_name = ndb.StringProperty()
    alliance_id = ndb.IntegerProperty()
    alliance_name = ndb.StringProperty()
    declined_srp = ndb.BooleanProperty()
    payments_made = ndb.IntegerProperty()
    payments_owed = ndb.IntegerProperty()

class Victim(ndb.Model):
    character_id = ndb.IntegerProperty()
    character_name = ndb.StringProperty()
    corporation_id = ndb.IntegerProperty()
    corporation_name = ndb.StringProperty()
    alliance_id = ndb.IntegerProperty()
    alliance_name = ndb.StringProperty()
    faction_id = ndb.IntegerProperty()
    faction_name = ndb.StringProperty()
    damage_taken = ndb.IntegerProperty()
    ship_type_id = ndb.IntegerProperty()
    ship_name = ndb.StringProperty()
    ship_class = ndb.StringProperty()

class Attacker(ndb.Model):
    character_id = ndb.IntegerProperty()
    character_name = ndb.StringProperty()
    corporation_id = ndb.IntegerProperty()
    corporation_name = ndb.StringProperty()
    alliance_id = ndb.IntegerProperty()
    alliance_name = ndb.StringProperty()
    faction_id = ndb.IntegerProperty()
    faction_name = ndb.StringProperty()
    damage_done = ndb.IntegerProperty()
    final_blow = ndb.BooleanProperty()
    security_status = ndb.FloatProperty()
    ship_type_id = ndb.IntegerProperty()
    weapon_type_id = ndb.IntegerProperty()
    ship_name = ndb.StringProperty()
    weapon_name = ndb.StringProperty()

class Item(ndb.Model):
    type_id = ndb.IntegerProperty()
    flag_id = ndb.IntegerProperty()
    qty_dropped = ndb.IntegerProperty()
    qty_destroyed = ndb.IntegerProperty()
    singleton = ndb.BooleanProperty()
    type_name = ndb.StringProperty()
    group_name = ndb.StringProperty()
    category_name = ndb.StringProperty()
    flag_name = ndb.StringProperty()
    bpc = ndb.BooleanProperty()
    value = ndb.FloatProperty()

class GroupedItems(ndb.Model):
    highs = LocalStructuredProperty(Item, repeated = True)
    mids = LocalStructuredProperty(Item, repeated = True)
    lows = LocalStructuredProperty(Item, repeated = True)
    rigs = LocalStructuredProperty(Item, repeated = True)
    subsystems = LocalStructuredProperty(Item, repeated = True)
    drone_bay = LocalStructuredProperty(Item, repeated = True)
    cargo = LocalStructuredProperty(Item, repeated = True)
    fleet_hangar = LocalStructuredProperty(Item, repeated = True)
    specialized_hangar = LocalStructuredProperty(Item, repeated = True)
    implants = LocalStructuredProperty(Item, repeated = True)

class PaymentDetail(ndb.Model):
    payment_id = ndb.IntegerProperty()
    kill_id = ndb.IntegerProperty()
    amount = ndb.IntegerProperty()

class KillMail(ndb.Model):
    kill_id = ndb.IntegerProperty()
    kill_time = ndb.DateTimeProperty()
    solar_system_id = ndb.IntegerProperty()
    solar_system_name = ndb.StringProperty()
    region_name = ndb.StringProperty()
    victim = LocalStructuredProperty(Victim)
    victim_id = ndb.IntegerProperty()
    attackers = LocalStructuredProperty(Attacker, repeated = True)
    final_blow = LocalStructuredProperty(Attacker)
    items = LocalStructuredProperty(Item, repeated = True)
    grouped_items = LocalStructuredProperty(GroupedItems)
    loss_mail = ndb.BooleanProperty()
    default_payment = ndb.IntegerProperty()
    suggested_loss_type = ndb.StringProperty()
    loss_type = ndb.StringProperty()
    srp_amount = ndb.IntegerProperty()
    paid_amount = ndb.IntegerProperty()
    payments = LocalStructuredProperty(PaymentDetail, repeated = True)
    crest_hash = ndb.StringProperty()
    outstanding_amount = ndb.ComputedProperty(lambda self: (self.srp_amount or 0) - (self.paid_amount or 0))
    hull_value = ndb.FloatProperty()
    dropped_value = ndb.FloatProperty()
    destroyed_value = ndb.FloatProperty()
    total_value = ndb.FloatProperty()

class Payment(ndb.Model):
    payment_id = ndb.IntegerProperty()
    character_id = ndb.IntegerProperty()
    character_name = ndb.StringProperty()
    corp_id = ndb.IntegerProperty()
    corp_name = ndb.StringProperty()
    payment_amount = ndb.IntegerProperty()
    paid = ndb.BooleanProperty()
    paid_date = ndb.DateTimeProperty()
    losses = LocalStructuredProperty(PaymentDetail, repeated = True)
    paid_by = ndb.IntegerProperty()
    paid_by_name = ndb.StringProperty()
    api_verified = ndb.BooleanProperty()
    api_amount = ndb.IntegerProperty()

class Silo(ndb.Model):
    silo_id = ndb.IntegerProperty()
    name = ndb.StringProperty()
    silo_type_id = ndb.IntegerProperty()
    silo_type_name = ndb.StringProperty()
    content_type_id = ndb.IntegerProperty()
    content_type_name = ndb.StringProperty()
    input = ndb.BooleanProperty()
    qty = ndb.IntegerProperty()
    capacity = ndb.IntegerProperty()
    hourly_usage = ndb.IntegerProperty()
    content_size = ndb.FloatProperty()

class Reactant(ndb.Model):
    reactant_type_id = ndb.IntegerProperty()
    reactant_type_name = ndb.StringProperty()
    reaction_qty = ndb.IntegerProperty()
    connected_to = ndb.IntegerProperty()
    item_size = ndb.FloatProperty()

class Reactor(ndb.Model):
    reactor_id = ndb.IntegerProperty()
    name = ndb.StringProperty()
    reactor_type_id = ndb.IntegerProperty()
    reactor_type_name = ndb.StringProperty()
    reaction_type_id = ndb.IntegerProperty()
    reaction_type_name = ndb.StringProperty()
    reactants = LocalStructuredProperty(Reactant, repeated = True)

class Tower(ndb.Model):
    pos_id = ndb.IntegerProperty()
    pos_name = ndb.StringProperty()
    system_id = ndb.IntegerProperty()
    system_name = ndb.StringProperty()
    planet = ndb.IntegerProperty()
    moon = ndb.IntegerProperty()
    x = ndb.FloatProperty()
    y = ndb.FloatProperty()
    z = ndb.FloatProperty()
    corp_id = ndb.IntegerProperty()
    corp_name = ndb.StringProperty()
    corp_ticker = ndb.StringProperty()
    pos_type_id = ndb.IntegerProperty()
    pos_type_name = ndb.StringProperty()
    fuel_type_id = ndb.IntegerProperty()
    fuel_type_name = ndb.StringProperty()
    fuel_hourly_usage = ndb.IntegerProperty()
    fuel_qty = ndb.IntegerProperty()
    stront_hourly_usage = ndb.IntegerProperty()
    stront_qty = ndb.IntegerProperty()
    next_tick = ndb.DateTimeProperty()
    status = ndb.StringProperty()
    harvesters = ndb.IntegerProperty(repeated = True)
    silos = LocalStructuredProperty(Silo, repeated = True)
    reactors = LocalStructuredProperty(Reactor, repeated = True)
    owner_type = ndb.StringProperty()
    owner_id = ndb.IntegerProperty()
    owner_name = ndb.StringProperty()
    fuel_bay_capacity = ndb.IntegerProperty()
    stront_bay_capacity = ndb.IntegerProperty()
    guns = LocalStructuredProperty(Silo, repeated = True)

class PosOwner(ndb.Model):
    location = ndb.StringProperty()
    owner = ndb.StringProperty()
