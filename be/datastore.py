import googledatastore
import logging
import calendar
import sha
from googledatastore.helper import *
from datetime import datetime
from config import ConfigSection

_config = ConfigSection('datastore')
_log = logging.getLogger('sound.be.datastore')
googledatastore.set_options(dataset = _config.get_option('dataset'))

def _date_to_timestamp(date):
    return long(calendar.timegm(date.utctimetuple()) * 1000000L) + date.microsecond

class _BaseEntity(object):
    """ Base class for all entities.

    Handles the conversion between the simple model objects defined in this module and google
    cloud datastore entity objects.
    """

    def _sub_entities(self):
        """ Get a dictionary of sub entities of the current entity.

        The keys of the dictionary are the field names in the current entity.
        The values are the model class used by that field.
        By default this is an empty dictionary unless overridden in a subclass.
        """

        return dict()

    def _get_entity(self):
        """ Get the cloud datastore representation of this entity. """

        _log.debug('%s._get_entity()', type(self).__name__)
        self.__fix_strings()
        entity = googledatastore.Entity()
        attrs = self.__dict__
        simple_attrs = dict()
        complex_attrs = dict()
        def process_entity(e):
            if isinstance(e, _BaseEntity):
                return e._get_entity()
            elif isinstance(e, list):
                return [process_entity(s) for s in e if s is not None]
            else:
                return e
        for key, val in attrs.iteritems():
            if isinstance(val, _BaseEntity):
                complex_attrs[key] = val._get_entity()
            elif isinstance(val, list):
                complex_attrs[key] = [process_entity(e) for e in val if e is not None]
            elif val is not None:
                simple_attrs[key] = val
        add_properties(entity, simple_attrs, indexed = True)
        add_properties(entity, complex_attrs, indexed = False)
        return entity

    def _set_entity(self, entity):
        """ Update this entity with values from the cloud datastore representation. """

        _log.debug('%s._set_entity()', type(self).__name__)
        attrs = get_property_dict(entity)
        def process_entity(entity, cls):
            if isinstance(entity, list):
                return [process_entity(e, cls) for e in entity]
            else:
                e = cls()
                e._set_entity(entity)
                return e
        attrs = { key: get_value(val) for (key, val) in attrs.iteritems() }
        for name, cls in self._sub_entities().iteritems():
            if name in attrs and attrs[name]:
                attrs[name] = process_entity(attrs[name], cls)
        for key, val in attrs.iteritems():
            setattr(self, key, val)

    def __fix_strings(self):
        for key in self.__dict__.keys():
            val = getattr(self, key)
            if type(val) is str:
                setattr(self, key, unicode(val))

class RootEntity(_BaseEntity):
    """ Base class for entities that will be stored in cloud datastore as their own kind. """

    def _get_entity(self):
        """ Override base class implementation to also set the key value. """

        entity = _BaseEntity._get_entity(self)
        entity.key.CopyFrom(self.__get_key())
        return entity

    def _get_id(self):
        """ Should be overridden by all sub-classes to get the entities id. """
        pass

    def load(self):
        """ Loads an entity from the datastore. """

        _log.debug('Loading %s entity with id %s.', type(self).__name__, self._get_id())
        resp = self.__lookup()
        if resp.found:
            self._set_entity(resp.found[0].entity)
            return True
        return False

    def save(self):
        """ Saves an entity to the datastore. """

        _log.debug('Saving %s entity with id %s.', type(self).__name__, self._get_id())
        req = googledatastore.BeginTransactionRequest()
        resp = googledatastore.begin_transaction(req)
        tx = resp.transaction
        self.modified_time = datetime.utcnow()
        resp = self.__lookup(tx)
        if not resp.found:
            self.created_time = self.modified_time
        self.__upsert(tx)

    def __get_key(self):
        key = googledatastore.Key()
        path = key.path_element.add()
        path.kind = type(self).__name__
        id = self._get_id()
        if isinstance(id, basestring):
            path.name = id
        else:
            path.id = id
        return key

    def __lookup(self, transaction = None):
        _log.debug('%s.__lookup()', type(self).__name__)
        req = googledatastore.LookupRequest()
        req.key.extend([self.__get_key()])
        if transaction:
            req.read_options.transaction = transaction
        return googledatastore.lookup(req)

    def __upsert(self, transaction = None):
        _log.debug('%s.__upsert()', type(self).__name__)
        req = googledatastore.CommitRequest()
        if transaction:
            req.transaction = transaction
        else:
            req.mode = googledatastore.CommitRequest.NON_TRANSACTIONAL
        entity = self._get_entity()
        req.mutation.upsert.extend([entity])
        googledatastore.commit(req)

    @classmethod
    def load_multi(cls, ids):
        """ Loads multiple entities from the datastore in batches. """

        _log.debug('Looking up %s entities with ids: %s.' % (cls.__name__, ids))
        def get_key(id):
            key = googledatastore.Key()
            path = key.path_element.add()
            path.kind = cls.__name__
            if isinstance(id, basestring):
                path.name = id
            else:
                path.id = id
            return key
        def get_entity(result):
            entity = cls()
            entity._set_entity(result.entity)
            return entity
        l = []
        for id in ids:
            l.append(id)
            if len(l) >= 10:
                _log.debug('Fetching %s' % l)
                req = googledatastore.LookupRequest()
                req.key.extend(map(get_key, l))
                resp = googledatastore.lookup(req)
                for res in resp.found:
                    yield get_entity(res)
                l = []
        if len(l) > 0:
            _log.debug('Fetching %s' % l)
            req = googledatastore.LookupRequest()
            req.key.extend(map(get_key, l))
            resp = googledatastore.lookup(req)
            for res in resp.found:
                yield get_entity(res)

    @staticmethod
    def bulk_save(entities):
        """ Saves multiple entities to the datastore in batches. """

        batch_size = 5
        time = datetime.utcnow()
        def save_batch(entities):
            req = googledatastore.BeginTransactionRequest()
            resp = googledatastore.begin_transaction(req)
            transaction = resp.transaction
            # Bulk lookup
            req = googledatastore.LookupRequest()
            req.key.extend([entity.__get_key() for entity in entities])
            req.read_options.transaction = transaction
            resp = googledatastore.lookup(req)
            # Update created / modified times.
            missing = set()
            for result in resp.missing:
                key = result.entity.key.path_element[0]
                missing.add(key.id or key.name)
            for entity in entities:
                entity.modified_time = time
                if entity._get_id() in missing:
                    entity.created_time = time
            # Bulk upsert
            req = googledatastore.CommitRequest()
            req.transaction = transaction
            req.mutation.upsert.extend([entity._get_entity() for entity in entities])
            googledatastore.commit(req)
        for chunk in range(0, len(entities), batch_size):
            save_batch(entities[chunk:chunk+batch_size])

    @staticmethod
    def bulk_delete(entities):
        batch_size = 5
        def delete_batch(batch):
            req = googledatastore.CommitRequest()
            req.mode = googledatastore.CommitRequest.NON_TRANSACTIONAL
            req.mutation.delete.extend([entity.__get_key() for entity in batch])
            googledatastore.commit(req)
        for chunk in range(0, len(entities), batch_size):
            delete_batch(entities[chunk:chunk+batch_size])

    @classmethod
    def query(cls, req):
        _log.debug('%s.query(%s)', cls.__name__, req.gql_query.query_string)

        cursor_arg = req.gql_query.name_arg.add()
        cursor_arg.name = 'startCursor'

        cursor = None
        while True:
            if cursor is None:
                cursor_arg.value.integer_value = 0
            else:
                cursor_arg.ClearField('value')
                cursor_arg.cursor = cursor

            resp = googledatastore.run_query(req)
            for result in resp.batch.entity_result:
                entity = cls()
                entity._set_entity(result.entity)
                yield entity
            if resp.batch.more_results == googledatastore.QueryResultBatch.NO_MORE_RESULTS:
                break
            if len(resp.batch.entity_result) == 0:
                break
            cursor = resp.batch.end_cursor

    @classmethod
    def all(cls):
        """ Loads all entities of this type from the datastore. """

        _log.debug('%s.all()', cls.__name__)

        req = googledatastore.RunQueryRequest()
        query = req.gql_query
        query.query_string = 'SELECT * FROM %s LIMIT 50 OFFSET @startCursor ' % cls.__name__
        query.allow_literal = True

        return cls.query(req)

    @classmethod
    def wipeout(cls):
        """ Deletes all entities of this type from the datastore. """

        _log.debug('%s.wipeout()', cls.__name__)
        batch_size = 500
        cursor = None
        while True:
            req = googledatastore.RunQueryRequest()
            query = req.gql_query
            query.query_string = 'SELECT __key__ FROM %s LIMIT %d OFFSET @startCursor ' % (
                    cls.__name__, batch_size)
            query.allow_literal = True

            cursor_arg = query.name_arg.add()
            cursor_arg.name = 'startCursor'
            if cursor is None:
                cursor_arg.value.integer_value = 0
            else:
                cursor_arg.cursor = cursor

            resp = googledatastore.run_query(req)

            req = googledatastore.CommitRequest()
            req.mode = googledatastore.CommitRequest.NON_TRANSACTIONAL
            req.mutation.delete.extend([result.entity.key for result in resp.batch.entity_result])
            googledatastore.commit(req)
            if resp.batch.more_results == googledatastore.QueryResultBatch.NO_MORE_RESULTS:
                break
            if len(resp.batch.entity_result) == 0:
                break
            cursor = resp.batch.end_cursor

class SubEntity(_BaseEntity):
    """ Base class for entities that are only stored as part of another entity. """
    pass

class Victim(SubEntity):

    def __init__(self):
        self.character_id = None
        self.character_name = None
        self.corporation_id = None
        self.corporation_name = None
        self.alliance_id = None
        self.alliance_name = None
        self.faction_id = None
        self.faction_name = None
        self.damage_taken = None
        self.ship_type_id = None
        self.ship_name = None
        self.ship_class = None

    def __str__(self):
        name = self.character_name
        if name is None or len(name) == 0:
            name = self.corporation_name
        return "%s's %s" % (name, self.ship_name)

class Attacker(SubEntity):

    def __init__(self):
        self.character_id = None
        self.character_name = None
        self.corporation_id = None
        self.corporation_name = None
        self.alliance_id = None
        self.alliance_name = None
        self.faction_id = None
        self.faction_name = None
        self.damage_done = None
        self.final_blow = None
        self.security_status = None
        self.ship_type_id = None
        self.ship_name = None
        self.weapon_type_id = None
        self.weapon_name = None

    def __str__(self):
        name = self.character_name
        if name is None or len(name) == 0:
            name = self.corporation_name
        des = "%s's %s: %d" % (name, self.ship_name, self.damage_done)
        if self.final_blow:
            des += ' (final blow)'
        return des

class Item(SubEntity):

    def __init__(self):
        self.type_id = None
        self.flag_id = None
        self.qty_dropped = None
        self.qty_destroyed = None
        self.singleton = None
        self.type_name = None
        self.group_name = None
        self.category_name = None
        self.flag_name = None
        self.bpc = None
        self.value = None

    def __str__(self):
        des = '%s in %s: ' % (self.type_name, self.flag_name)
        if self.qty_dropped > 0:
            return des + '%d dropped' % self.qty_dropped
        else:
            return des + '%d destroyed' % self.qty_destroyed

class GroupedItems(SubEntity):
    def __init__(self, items = None):
        self.highs = []
        self.mids = []
        self.lows = []
        self.rigs = []
        self.subsystems = []
        self.drone_bay = []
        self.cargo = []
        self.fleet_hangar = []
        self.specialized_hangar = []
        self.implants = []
        if items is not None:
            self.add_all(items)

    def _sub_entities(self):
        return { key: Item for key in ['highs', 'mids', 'lows', 'rigs', 'subsystems',
            'drone_bay', 'cargo', 'fleet_hangar', 'specialized_hangar', 'implants'] }

    def add_all(self, items):
        if items is None:
            return
        def slotcmp(a, b):
            t = cmp(a.flag_name, b.flag_name)
            if t != 0:
                return t
            if a.category_name == 'Charge' and b.category_name != 'Charge':
                return 1
            if a.category_name != 'Charge' and b.category_name == 'Charge':
                return -1
            return 0

        def slot(items, slotType):
            res = filter((lambda i: i.flag_name.startswith(slotType)), items)
            if len(res) == 0:
                return None
            return sorted(res, slotcmp)

        self.highs = slot(items, 'HiSlot')
        self.mids = slot(items, 'MedSlot')
        self.lows = slot(items, 'LoSlot')
        self.rigs = slot(items, 'RigSlot')
        self.subsystems = slot(items, 'SubSystem')
        self.drone_bay = slot(items, 'DroneBay')
        self.cargo = slot(items, 'Cargo')
        self.fleet_hangar = slot(items, 'FleetHangar')
        self.specialized_hangar = slot(items, 'Specialized')
        self.implants = slot(items, 'Implant')

class KillMail(RootEntity):

    def __init__(self, kill_id = None):
        self.kill_id = kill_id
        self.kill_time = None
        self.solar_system_id = None
        self.solar_system_name = None
        self.region_name = None
        self.victim_id = None
        self.victim = None
        self.attackers = []
        self.final_blow = None
        self.items = []
        self.grouped_items = None
        self.loss_mail = None
        self.default_payment = None
        self.suggested_loss_type = None
        self.loss_type = None
        self.srp_amount = None
        self.paid_amount = None
        self.outstanding_amount = None
        self.crest_hash = None
        self.payments = []
        self.hull_value = None
        self.dropped_value = None
        self.destroyed_value = None
        self.total_value = None
        if kill_id is not None:
            self.load()

    def _get_id(self):
        self.outstanding_amount = (self.srp_amount or 0) - (self.paid_amount or 0)
        return self.kill_id

    def _sub_entities(self):
        return {
            'victim': Victim,
            'attackers': Attacker,
            'final_blow': Attacker,
            'items': Item,
            'payments': PaymentDetail,
            'grouped_items': GroupedItems
        }

    def __repr__(self):
        return 'KillMail(%d)' % self.kill_id

    def __str__(self):
        return 'KillMail %d: %s' % (self.kill_id, self.victim)

    def get_crest_hash(self):
        if self.crest_hash is not None:
            return self.crest_hash
        fb = None
        for a in self.attackers:
            if a.final_blow or (fb is None and len(self.attackers) == 1):
                fb = str(a.character_id or 'None')
        if fb is None:
            if len(self.attackers) > 0:
                fb = str(self.attackers[0].character_id or 'None')
        h = sha.new()
        h.update(str(self.victim.character_id or 'None'))
        h.update(fb)
        h.update(str(self.victim.ship_type_id or 'None'))
        h.update(str(long((self.kill_time - datetime.utcfromtimestamp(0)).total_seconds() * 10000000 + 116444736000000000L)))
        self.crest_hash = h.hexdigest()
        return self.crest_hash

    @property
    def crest_url(self):
        h = self.get_crest_hash()
        if h is None:
            return None
        return 'http://public-crest.eveonline.com/killmails/%d/%s/' % (self.kill_id, h)

    @classmethod
    def all_after(cls, kill_id):
        _log.debug('KillMail.all_after(%d)', kill_id)

        req = googledatastore.RunQueryRequest()
        query = req.gql_query

        if type(kill_id) is int:
            query.query_string = ('SELECT * FROM KillMail ' +
                    'WHERE kill_id > @killId ' +
                    'ORDER BY kill_id ' +
                    'LIMIT 50 OFFSET @startCursor ')
            query.allow_literal = True

            kill_id_arg = query.name_arg.add()
            kill_id_arg.name = 'killId'
            kill_id_arg.value.integer_value = kill_id
        else:
            query.query_string = ('SELECT * FROM KillMail ' +
                    'WHERE kill_time > @killTime ' +
                    'ORDER BY kill_time ' +
                    'LIMIT 50 OFFSET @startCursor ')
            query.allow_literal = True

            ts = _date_to_timestamp(kill_id)
            kill_time_arg = query.name_arg.add()
            kill_time_arg.name = 'killTime'
            kill_time_arg.value.timestamp_microseconds_value = ts

        return cls.query(req)

    @classmethod
    def losses_after(cls, date):
        _log.debug('KillMail.losses_after(%s)', date)

        ts = _date_to_timestamp(date)

        req = googledatastore.RunQueryRequest()
        query = req.gql_query
        query.query_string = ('SELECT * FROM KillMail ' +
            'WHERE loss_mail = TRUE ' +
            'AND kill_time > @date ' +
            'ORDER BY kill_time, kill_id ' +
            'LIMIT 50 OFFSET @startCursor ')
        query.allow_literal = True

        date_arg = query.name_arg.add()
        date_arg.name = 'date'
        date_arg.value.timestamp_microseconds_value = ts

        return cls.query(req)

    def related_kills(self, back_minutes = 60, forward_minutes = 15, system_ids = None):
        micros_per_minute = 60 * 1000000L
        ts = _date_to_timestamp(self.kill_time)
        start = ts - back_minutes * micros_per_minute
        end = ts + forward_minutes * micros_per_minute
        if system_ids is None:
            system_ids = [self.solar_system_id]

        for system in system_ids:
            req = googledatastore.RunQueryRequest()
            query = req.gql_query
            query.query_string = ('SELECT * FROM KillMail ' +
                    'WHERE solar_system_id = @system ' +
                    'AND kill_time >= @startTime ' +
                    'AND kill_time < @endTime ' +
                    'ORDER BY kill_time, kill_id ')

            system_arg = query.name_arg.add()
            system_arg.name = 'system'
            system_arg.value.integer_value = system

            start_time_arg = query.name_arg.add()
            start_time_arg.name = 'startTime'
            start_time_arg.value.timestamp_microseconds_value = start

            end_time_arg = query.name_arg.add()
            end_time_arg.name = 'endTime'
            end_time_arg.value.timestamp_microseconds_value = end

            resp = googledatastore.run_query(req)
            for result in resp.batch.entity_result:
                entity = KillMail()
                entity._set_entity(result.entity)
                yield entity

class LossMailAttributes(RootEntity):

    def __init__(self, loss_id = None):
        self.kill_id = loss_id
        self.character_id = None
        self.ship_type_id = None
        self.ship_group_id = None
        self.region_name = None
        self.empty_low_slots = None
        self.empty_med_slots = None
        self.empty_rig_slots = None
        self.empty_hardpoints = None
        self.exploration_mods = None
        self.tackle_mods = None
        self.local_rep = None
        self.npcs_on_lossmail = None
        self.players_on_lossmail = None
        self.friendlies_on_lossmail = None
        self.friendly_bombers_on_lossmail = None
        self.recent_kills = False
        self.recent_friendly_kills_nearby = False
        self.recent_friendly_losses_nearby = False
        self.home_region = None
        self.cyno = None
        if loss_id is not None:
            self.load()

    def _get_id(self):
        return self.kill_id

    def __repr__(self):
        return 'LossMailAttributes(%d)' % self.kill_id

    def __str__(self):
        return 'LossMailAttributes %d' % self.kill_id

    @classmethod
    def by_ship_type(cls, ship_type_id):
        _log.debug('LossMailAttributes.by_ship_type(%d)', ship_type_id)
        cursor = None
        while True:
            req = googledatastore.RunQueryRequest()
            query = req.gql_query
            query.query_string = ('SELECT * FROM LossMailAttributes ' +
                    'WHERE ship_type_id = @shipTypeId ' +
                    'LIMIT 50 OFFSET @startCursor ')
            query.allow_literal = True

            ship_type_arg = query.name_arg.add()
            ship_type_arg.name = 'shipTypeId'
            ship_type_arg.value.integer_value = ship_type_id

            cursor_arg = query.name_arg.add()
            cursor_arg.name = 'startCursor'
            if cursor is None:
                cursor_arg.value.integer_value = 0
            else:
                cursor_arg.cursor = cursor

            resp = googledatastore.run_query(req)
            for result in resp.batch.entity_result:
                entity = cls()
                entity._set_entity(result.entity)
                yield entity
            if resp.batch.more_results == googledatastore.QueryResultBatch.NO_MORE_RESULTS:
                break
            if len(resp.batch.entity_result) == 0:
                break
            cursor = resp.batch.end_cursor

class ShipClass(RootEntity):

    def __init__(self, ship_class = None):
        self.ship_class = ship_class
        self.fixed_reimbursement = None
        self.market_reimbursement_multiplier = None
        if ship_class is not None:
            self.load()

    def _get_id(self):
        return self.ship_class

    def __repr__(self):
        return "ShipClass('%s')" % self.ship_class

    def __str__(self):
        return 'ShipClass %s' % self.ship_class

class Character(RootEntity):

    def __init__(self, character_id = None):
        self.character_id = character_id
        self.character_name = None
        self.corp_id = None
        self.corp_name = None
        self.alliance_id = None
        self.alliance_name = None
        self.declined_srp = None
        self.payments_made = None
        self.payments_owed = None
        if character_id is not None:
            self.load()

    def _get_id(self):
        return self.character_id

    def __repr(self):
        return 'Character(%d)' % self.character_id

    def __str__(self):
        return 'Character %s' % self.character_name

class Corporation(RootEntity):
    def __init__(self, corp_id = None):
        self.corp_id = corp_id
        self.corp_name = None
        self.alliance_id = None
        self.alliance_name = None
        self.srp = None
        self.corp_ticker = None
        if corp_id is not None:
            self.load()

    def _get_id(self):
        return self.corp_id

    def __repr__(self):
        return 'Corporation(%d)' % self.corp_id

    def __str__(self):
        return self.corp_name

class Location(RootEntity):

    def __init__(self, location_id = None):
        self.location_id = location_id
        self.location_type = None
        self.location_name = None
        self.full_reimbursement = None
        if location_id is not None:
            self.load()

    def _get_id(self):
        return self.location_id

    def __repr__(self):
        return "Location('%d')" % self.location_id

    def __str__(self):
        return '%s %s' % (self.location_type, self.location_name)

class Payment(RootEntity):

    def __init__(self, payment_id = None):
        self.payment_id = payment_id
        self.character_id = None
        self.character_name = None
        self.corp_id = None
        self.corp_name = None
        self.payment_amount = None
        self.paid = False
        self.paid_date = None
        self.losses = []
        self.paid_by = None
        self.paid_by_name = None
        self.api_verified = False
        self.api_amount = None
        if payment_id is not None:
            self.load()

    def _get_id(self):
        return self.payment_id

    def __repr__(self):
        return 'Payment(%d)' % self.payment_id

    def __str__(self):
        if self.paid:
            return "Paid %d to %d on %s" % (self.payment_amount, self.character_id, self.paid_date)
        else:
            return "Pay %d to %d" % (self.payment_amount, self.character_id)

    def _sub_entities(self):
        return {
            'losses': PaymentDetail
        }

    @classmethod
    def all_outstanding(cls):
        _log.debug('Payment.all_outstanding()')

        cursor = None
        while True:
            req = googledatastore.RunQueryRequest()
            query = req.gql_query
            query.query_string = ('SELECT * FROM Payment ' +
                'WHERE paid = FALSE ' +
                'LIMIT 50 OFFSET @startCursor ')
            query.allow_literal = True

            cursor_arg = query.name_arg.add()
            cursor_arg.name = 'startCursor'
            if cursor is None:
                cursor_arg.value.integer_value = 0
            else:
                cursor_arg.cursor = cursor

            resp = googledatastore.run_query(req)
            for result in resp.batch.entity_result:
                entity = cls()
                entity._set_entity(result.entity)
                yield entity
            if resp.batch.more_results == googledatastore.QueryResultBatch.NO_MORE_RESULTS:
                break
            if len(resp.batch.entity_result) == 0:
                break
            cursor = resp.batch.end_cursor

    @classmethod
    def unverified_payments(cls):
        _log.debug('Payment.unverified_payments()')

        cursor = None
        while True:
            req = googledatastore.RunQueryRequest()
            query = req.gql_query
            query.query_string = ('SELECT * FROM Payment ' +
                    'WHERE paid = TRUE ' +
                    'AND api_verified = FALSE ' +
                    'LIMIT 50 OFFSET @startCursor ')
            query.allow_literal = True

            cursor_arg = query.name_arg.add()
            cursor_arg.name = 'startCursor'
            if cursor is None:
                cursor_arg.value.integer_value = 0
            else:
                cursor_arg.cursor = cursor

            resp = googledatastore.run_query(req)
            for result in resp.batch.entity_result:
                entity = cls()
                entity._set_entity(result.entity)
                yield entity
            if resp.batch.more_results == googledatastore.QueryResultBatch.NO_MORE_RESULTS:
                break
            if len(resp.batch.entity_result) == 0:
                break
            cursor = resp.batch.end_cursor

class PaymentDetail(SubEntity):

    def __init__(self, payment_id = None, kill_id = None, amount = None):
        self.payment_id = payment_id
        self.kill_id = kill_id
        self.amount = amount

    def __repr__(self):
        return 'PaymentDetail(%d, %d, %d)' % (self.payment_id, self.kill_id, self.amount)

class Silo(SubEntity):
    def __init__(self):
        self.silo_id = None
        self.name = None
        self.silo_type_id = None
        self.silo_type_name = None
        self.content_type_id = None
        self.content_type_name = None
        self.input = False
        self.qty = 0
        self.capacity = 0
        self.hourly_usage = 0
        self.content_size = 1

    @property
    def volume(self):
        return self.qty * self.content_size

class Reactant(SubEntity):
    def __init__(self):
        self.reactant_type_id = None
        self.reactant_type_name = None
        self.reaction_qty = 0
        self.connected_to = None
        self.item_size = 1

    def __str__(self):
        return 'Reactant %s: %s' % (self.reactant_type_name, self.reaction_qty)

class Reactor(SubEntity):
    def __init__(self):
        self.reactor_id = None
        self.name = None
        self.reactor_type_id = None
        self.reactor_type_name = None
        self.reaction_type_id = None
        self.reaction_type_name = None
        self.reactants = []

    def _sub_entities(self):
        return { "reactants": Reactant }

class Tower(RootEntity):
    def __init__(self, pos_id = None):
        self.pos_id = pos_id
        self.pos_name = 'Unknown POS'
        self.system_id = None
        self.system_name = 'Unknown System'
        self.planet = None
        self.moon = None
        self.x = None
        self.y = None
        self.z = None
        self.corp_id = None
        self.corp_name = None
        self.corp_ticker = None
        self.pos_type_id = None
        self.pos_type_name = None
        self.fuel_type_id = None
        self.fuel_type_name = None
        self.fuel_hourly_usage = None
        self.fuel_qty = None
        self.stront_hourly_usage = None
        self.stront_qty = None
        self.next_tick = None
        self.status = 'Unknown Status'
        self.harvesters = []
        self.silos = []
        self.reactors = []
        self.owner_type = None
        self.owner_id = None
        self.owner_name = None
        self.fuel_bay_capacity = None
        self.stront_bay_capacity = None
        self.guns = []
        if pos_id is not None:
            self.load()

    def _get_id(self):
        return self.pos_id

    def _sub_entities(self):
        return { 'silos': Silo, 'reactors': Reactor, 'guns': Silo }

    @property
    def location_str(self):
        def roman(n): # Pretty sure no systems in Eve have >= 40 planets...
            if n == 0: return ''
            if n in [ 4, 9 ]: return 'I' + roman(n+1)
            if n >= 10: return 'X' + roman(n-10)
            if n >= 5: return 'V' + roman(n-5)
            return roman(n-1) + 'I'
        return '%s %s-%s' % (self.system_name, roman(self.planet), self.moon)

    def __repr__(self):
        return 'Tower(%d)' % self.pos_id

    def __str__(self):
        return '%s - %s' % (self.location_str, self.pos_name)

    @staticmethod
    def get_by_name(name):
        req = googledatastore.RunQueryRequest()
        req.query.kind.add().name = 'Tower'
        name_filter = req.query.filter.property_filter
        name_filter.property.name = 'pos_name'
        name_filter.operator = googledatastore.PropertyFilter.EQUAL
        name_filter.value.string_value = name
        resp = googledatastore.run_query(req)
        if resp.batch.entity_result:
            tower = Tower()
            tower._set_entity(resp.batch.entity_result[0].entity)
            return tower
        return None

class Control(RootEntity):

    def __init__(self):
        self.next_payment_id = 1
        self.load()

    def _get_id(self):
        return 1

    def __repr__(self):
        return 'Control()'

    def __str__(self):
        return "next_payment_id: %d" % self.next_payment_id

class Configuration(RootEntity):

    def __init__(self, version = None):
        self.version = version
        self.client_id = None
        self.auth_header = None
        self.base_uri = None
        self.redirect_uri = None
        self.scopes = None
        self.srp_admins = []
        self.srp_payers = []
        self.super_admins = []
        self.alliance_id = None
        self.pos_admins = []
        if version is not None:
            self.load()

    def _get_id(self):
        return self.version

    def __repr__(self):
        return 'Configuration(%s)' % self.version

    def __str__(self):
        return str(self.__dict__)

