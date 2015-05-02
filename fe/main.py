import eveapi
import jinja2
import logging
import os
import random
import sys
import urllib
import urllib2
import webapp2
from collections import Mapping, Sequence
from datetime import datetime, timedelta
from decimal import Decimal
from google.appengine.ext import ndb
import simplejson as json
from model import Configuration, Payment, Character, KillMail, LossMailAttributes, Tower, PosOwner, Corporation
from webapp2_extras import routes, sessions

DATE_FORMAT = '%Y-%m-%d %H:%M:%S'
JINJA_ENVIRONMENT = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)),
    extensions=['jinja2.ext.autoescape'])

_log = logging.getLogger('sound.main')

def decimalize(o):
    if isinstance(o, float):
        return Decimal(o).quantize(Decimal('0.01'))
    elif isinstance(o, list):
        return [decimalize(i) for i in o]
    elif isinstance(o, dict):
        return dict((k,decimalize(v)) for k,v in o.iteritems())
    else:
        return o

class JSONEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, ndb.Model):
            return decimalize(o.to_dict())
        elif isinstance(o, datetime):
            return str(o)
        return o

class BaseHandler(webapp2.RequestHandler):

    def dispatch(self):
        self.session_store = sessions.get_store(request=self.request)
        try:
            webapp2.RequestHandler.dispatch(self)
        finally:
            self.session_store.save_sessions(self.response)

    @webapp2.cached_property
    def session(self):
        return self.session_store.get_session()

    @webapp2.cached_property
    def logged_in(self):
        return ('access_token' in self.session) #and
            #datetime.strptime(self.session['access_token_expires'], DATE_FORMAT) > datetime.now())

    @webapp2.cached_property
    def srp_admin(self):
        if 'character_id' not in self.session:
            return False
        cid = int(self.session['character_id'])
        return cid in self.config.srp_admins or cid in self.config.super_admins

    @webapp2.cached_property
    def srp_payer(self):
        if 'character_id' not in self.session:
            return False
        cid = int(self.session['character_id'])
        return (cid in self.config.srp_payers) or (cid in self.config.super_admins)

    @webapp2.cached_property
    def pos_admin(self):
        if 'character_id' not in self.session:
            return False
        cid = int(self.session['character_id'])
        return cid in self.config.pos_admins or cid in self.config.super_admins

    @webapp2.cached_property
    def super_admin(self):
        if 'character_id' not in self.session:
            return False
        return int(self.session['character_id']) in self.config.super_admins

    @webapp2.cached_property
    def config(self):
        return Configuration.get_instance()

class LoginHandler(BaseHandler):
    def get(self):
        if self.logged_in:
            if self.session['alliance_id'] != self.config.alliance_id:
                return self.redirect_to('logout')
            elif 'referer' in self.session:
                return self.redirect(self.session['referer'])
            else:
                return self.redirect_to('srp')
        if 'referer' not in self.session and 'Referer' in self.request.headers:
            self.session['referer'] = self.request.headers['Referer']
        elif 'referer' not in self.session:
            self.session['referer'] = webapp2.uri_for('posmon')
        self.session['state'] = str(random.randint(0, 2000000))
        state = self.session['state']
        url = "https://login.eveonline.com/oauth/authorize/?response_type=code&redirect_uri=%s&client_id=%s&scope=%s&state=%s"
        url = str(url % (self.config.redirect_uri, self.config.client_id, self.config.scopes or '', state))
        _log.info('Redirecting to Eve SSO Login page.')
        return self.redirect(url)

class LogoutHandler(BaseHandler):
    def get(self):
        del self.session['access_token']
        del self.session['access_token_expires']
        del self.session['character_id']
        del self.session['character_name']
        if 'Referer' in self.request.headers:
            return self.redirect(self.request.headers['Referer'])
        return self.redirect_to('srp')

class EveSSOAuthHandler(BaseHandler):
    def get(self):
        code = self.request.get('code')
        state = self.request.get('state')
        if state == self.session['state']:
            _log.info('Exchanging authorization code for token.')
            url = 'https://login.eveonline.com/oauth/token'
            params = {}
            params['grant_type'] = 'authorization_code'
            params['code'] = code
            headers = {}
            headers['Authorization'] = 'Basic %s' % self.config.auth_header
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
            req = urllib2.Request(url, urllib.urlencode(params), headers)
            resp = urllib2.urlopen(req, timeout = 15)
            data = resp.read()
            _log.debug('Token Response: %s' % data)
            data = json.loads(data)
            self.session['access_token'] = data['access_token']
            self.session['access_token_expires'] = (datetime.now() + timedelta(0, data['expires_in'])).strftime(DATE_FORMAT)

            _log.info('Getting logged in character details.')
            character_id, character_name = eveapi.get_character(data['access_token'])
            self.session['character_id'] = character_id
            self.session['character_name'] = character_name
            self.session['alliance_id'] = eveapi.get_alliance(character_id)

            if 'referer' in self.session and self.session['referer'] is not None:
                _log.info('Login successful, returning to referer.')
                ref = str(self.session['referer'])
                del self.session['referer']
                return self.redirect(ref)
            else:
                _log.info('Login successful, returning to home page.')
                return self.redirect_to('srp')
        else:
            _log.warning('State did not match, redirecting back to login.')
            return self.redirect_to('login')

class IGBPaymentsHandler(BaseHandler):
    def get(self):
        if not self.logged_in or not self.srp_payer:
            self.session['referer'] = webapp2.uri_for('igbpayments')
            return self.redirect_to('login')
        payments = Payment.query(Payment.paid == False).fetch()
        total = 0
        data = {}
        data['payments'] = []
        for payment in payments:
            pdata = {}
            pdata['payment_id'] = payment.payment_id
            pdata['character_id'] = payment.character_id
            pdata['character_name'] = payment.character_name
            pdata['payment_amount'] = payment.payment_amount * 1000000
            pdata['corporation_name'] = payment.corp_name
            data['payments'].append(pdata)
            total += payment.payment_amount
        data['total'] = total
        data['base_uri'] = self.config.base_uri
        data['character_id'] = self.session['character_id']
        data['character_name'] = self.session['character_name']
        template = JINJA_ENVIRONMENT.get_template('igbpayments.html')
        self.response.write(template.render(data))

class IGBPayHandler(BaseHandler):
    @ndb.toplevel
    def get(self, payment_id):
        if not self.logged_in or not self.srp_payer:
            self.session['referer'] = webapp2.uri_for('igbpayments')
            return self.redirect_to('login')
        _log.info('Setting payment %d as paid.' % payment_id)
        payment = Payment.get_by_id(int(payment_id))
        payment.paid = True
        payment.paid_by = self.session['character_id']
        payment.paid_by_name = self.session['character_name']
        payment.paid_date = datetime.utcnow()
        payment.modified_time = datetime.utcnow()
        payment.modified_by = self.session['character_id']
        payment.put_async()

        loss_futures = [ (KillMail.query(KillMail.kill_id == loss.kill_id).get_async(), loss.amount)
                for loss in payment.losses ]
        for future, amount in loss_futures:
            loss = future.get_result()
            loss.paid_amount = (loss.paid_amount or 0) + amount
            loss.paid = loss.paid_amount == (loss.srp_amount or 0)
            loss.modified_time = datetime.utcnow()
            loss.modified_by = self.session['character_id']
            loss.put_async()

        self.redirect_to('igbpayments')

class JsonHandler(BaseHandler):
    def write_json(self, data):
        self.response.headers['Access-Control-Allow-Origin'] = '*'
        self.response.headers['Content-Type'] = 'application/json'
        jdata = JSONEncoder(use_decimal=True).encode(data)
        self.response.write(jdata)

    def write_page(self, query, mapper = None):
        pageSize = 20
        page = int((self.request.get('page') or 1))
        offset = (page - 1) * pageSize
        if mapper is None:
            data = query.fetch(offset=offset, limit=pageSize)
        else:
            data = query.map(mapper, offset=offset, limit=pageSize)
        self.write_json(data)

    def read_json(self):
        return json.loads(self.request.body, use_decimal=True)

class ConfigHandler(JsonHandler):
    def get(self):
        data = {}
        data['base_uri'] = self.config.base_uri
        data['alliance_id'] = self.config.alliance_id
        data['logged_in'] = self.logged_in
        if self.logged_in:
            _log.debug('Logged in as %s.' % self.session['character_name'])
            data['srp_admin'] = self.srp_admin
            data['srp_payer'] = self.srp_payer
            data['pos_admin'] = self.pos_admin
            data['super_admin'] = self.super_admin
            data['character_id'] = self.session['character_id']
            data['character_name'] = self.session['character_name']
        else:
            _log.debug('Not logged in.')
            data['pos_admin'] = False
            data['srp_admin'] = False
            data['srp_payer'] = False
            data['super_admin'] = False
        self.write_json(data)

class KillsHandler(JsonHandler):
    def get(self):
        killmails = KillMail.query()
        if 'victim' in self.request.GET:
            cid = int(self.request.get('victim'))
            killmails = killmails.filter(KillMail.victim_id == cid)
        if 'srpable' in self.request.GET:
            killmails = killmails.filter(KillMail.srpable == True)
            killmails = killmails.filter(KillMail.paid == False)
            killmails = killmails.order(KillMail.kill_time, KillMail.kill_id)
        else:
            killmails = killmails.order(-KillMail.kill_time, -KillMail.kill_id)
        def mapper(kill):
            finalBlow = None
            try:
                finalBlow = kill.final_blow
            except:
                _log.debug(sys.exc_info()[0])
            return {
                'kill_id': kill.kill_id,
                'kill_time': kill.kill_time,
                'loss_mail': kill.loss_mail,
                'solar_system_name': kill.solar_system_name,
                'region_name': kill.region_name,
                'loss_type': kill.loss_type,
                'suggested_loss_type': kill.suggested_loss_type,
                'srp_amount': kill.srp_amount,
                'default_payment': kill.default_payment,
                'victim': {
                    'character_id': kill.victim.character_id,
                    'character_name': kill.victim.character_name,
                    'corporation_id': kill.victim.corporation_id,
                    'corporation_name': kill.victim.corporation_name,
                    'alliance_id': kill.victim.alliance_id,
                    'alliance_name': kill.victim.alliance_name,
                    'ship_type_id': kill.victim.ship_type_id,
                    'ship_name': kill.victim.ship_name,
                    'ship_class': kill.victim.ship_class
                },
                'final_blow': {
                    'character_id': finalBlow.character_id,
                    'character_name': finalBlow.character_name,
                    'corporation_id': finalBlow.corporation_id,
                    'corporation_name': finalBlow.corporation_name,
                    'alliance_id': finalBlow.alliance_id,
                    'alliance_name': finalBlow.alliance_name
                } if finalBlow is not None else None,
                'num_attackers': len(kill.attackers),
                'total_value': kill.total_value
            }
        self.write_page(killmails, mapper)

    def post(self):
        if not self.logged_in:
            self.session['referer'] = webapp2.uri_for('srp')
            return self.redirect_to('login')
        if not self.srp_admin:
            return self.redirect_to('srp')
        data = self.read_json()
        kill_id = int(data['kill_id'])
        # TODO: Figure out where the [None] is coming from this time.
        km = KillMail.get_by_id(kill_id)
        km.payments = [p for p in km.payments if p is not None]
        km.loss_type = data['loss_type']
        km.srp_amount = int(data['srp_amount'])
        km.modified_time = datetime.utcnow()
        km.modified_by = self.session['character_id']
        km.put()

class KillHandler(JsonHandler):
    def get(self, kill_id):
        _log.debug('Get kill %s' % kill_id)
        lmaf = None
        if 'loss_attributes' in self.request.GET:
            lmaf = LossMailAttributes.get_by_id_async(int(kill_id))
        killmail = KillMail.get_by_id(int(kill_id))
        if killmail is None:
            self.abort(404)
        elif lmaf is not None:
            data = decimalize(killmail.to_dict())
            data['loss_attributes'] = lmaf.get_result().to_dict()
            self.write_json(data)
        else:
            self.write_json(killmail)

class CharactersHandler(JsonHandler):
    def get(self):
        allianceId = self.config.alliance_id
        characters = Character.query(Character.alliance_id == allianceId).order(Character.character_name)
        self.write_page(characters)

class CharacterHandler(JsonHandler):
    def get(self, character_id):
        _log.debug('Get character %s' % character_id)
        character = Character.get_by_id(int(character_id))
        if character is None:
            self.abort(404)
        else:
            self.write_json(character)

class PaymentsHandler(JsonHandler):
    def get(self):
        payments = Payment.query()
        if 'paid' in self.request.GET:
            paid = self.request.get('paid') in [ 'true', '1' ]
            payments = payments.filter(Payment.paid == paid)
        if 'cid' in self.request.GET:
            cid = int(self.request.get('cid'))
            payments = payments.filter(Payment.character_id == cid)
        payments = payments.order(-Payment.payment_id)
        self.write_page(payments)

class PaymentHandler(JsonHandler):
    def get(self, payment_id):
        _log.debug('Get payment %s' % payment_id)
        payment = Payment.get_by_id(int(payment_id))
        if payment is None:
            self.abort(404)
        else:
            self.write_json(payment)

class SearchHandler(JsonHandler):
    def get(self, search_text):
        futures = []
        num = None
        if search_text.isdigit():
            num = int(search_text)
            _log.debug('Search by ids: %d' % num)
            futures.append(KillMail.get_by_id_async(num))
            futures.append(Character.get_by_id_async(num))
            futures.append(Payment.get_by_id_async(num))
            futures.append(Tower.get_by_id_async(num))
        if search_text.startswith('K') and search_text[1:].isdigit():
            _log.debug('Search kill by id: %s' % search_text[1:])
            futures.append(KillMail.get_by_id_async(int(search_text[1:])))
        if search_text.startswith('C') and search_text[1:].isdigit():
            _log.debug('Search character by id: %s' % search_text[1:])
            futures.append(Character.get_by_id_async(int(search_text[1:])))
        if search_text.startswith('P') and search_text[1:].isdigit():
            _log.debug('Search payment by id: %s' % search_text[1:])
            futures.append(Payment.get_by_id_async(int(search_text[1:])))
        if search_text.startswith('T') and search_text[1:].isdigit():
            _log.debug('Search tower by id: %s' % search_text[1:])
            futures.append(Tower.get_by_id_async(Tower.pos_id == int(search_text[1:])))
        results = []
        for name, id in characters:
            if search_text in name:
                _log.debug('Found matching character: %s' % name)
                futures.append(Character.get_by_id_async(id))
        for future in futures:
            try:
                result = future.get_result()
                if type(result) is KillMail:
                    results.append({
                        'type': 'kill',
                        'id': result.kill_id,
                        'name': "Kill %d: %s's %s" % (result.kill_id, result.victim.character_name, result.victim.ship_name),
                        'image': 'https://image.eveonline.com/Type/%d_32.png' % result.victim.ship_type_id,
                        'value': result
                    })
                elif type(result) is Character:
                    results.append({
                        'type': 'character',
                        'id': result.character_id,
                        'name': result.character_name,
                        'image': 'https://image.eveonline.com/Character/%d_32.jpg' % result.character_id,
                        'value': result
                    })
                elif type(result) is Payment:
                    results.append({
                        'type': 'payment',
                        'id': result.payment_id,
                        'name': 'Payment %d: To %s' % (result.payment_id, result.character_name),
                        'image': 'https://image.eveonline.com/Character/%d_32.jpg' % result.character_id,
                        'value': result
                    })
                if type(result) is Tower:
                    results.append({
                        'type': 'tower',
                        'id': result.pos_id,
                        'name': "Tower %s at %s P%d M%d" % (result.pos_name, result.system_name, result.planet, result.moon),
                        'image': 'https://image.eveonline.com/Type/%d_32.png' % result.pos_type_id,
                        'value': result
                    })
                elif result is not None:
                    _log.debug('Unknown result type: %s' % type(result))
            except:
                _log.debug('Error.')
        _log.debug('Search for %s found %d results.' % (search_text, len(results)))
        self.write_json(sorted(results))

class TowersHandler(JsonHandler):
    def get(self):
        if not self.logged_in:
            self.session['referer'] = webapp2.uri_for('posmon')
            return self.redirect_to('login')
        if self.session['alliance_id'] != self.config.alliance_id:
            _log.debug('Alliance: %s != %s' % (self.session['alliance_id'], self.config.alliance_id))
            self.session['referer'] = webapp2.uri_for('posmon')
            return self.redirect_to('logout')
        corps = Corporation.query().fetch_async()
        towers = Tower.query(Tower.deleted == False).fetch()
        corps = corps.get_result()
        if 'corp' in self.request.GET:
            corp = self.request.get('corp')
            corpIds = [t.corp_id for t in corps if str(t.corp_id) == corp or t.corp_name == corp or t.corp_ticker == corp]
            towers = filter(lambda t: t.corp_id in corpIds, towers)
        corps = { c.corp_id: c for c in corps }
        if 'system' in self.request.GET:
            system = self.request.get('system')
            towers = filter(lambda t: str(t.system_id) == system or t.system_name == system, towers)
        if 'owner' in self.request.GET:
            def roman(n):
                if n == 0:
                    return ''
                if n >= 10:
                    return 'X' + roman(n-10)
                if n == 9 or n == 4:
                    return 'I' + roman(n+1)
                if n == 5:
                    return 'V'
                return roman(n-1) + 'I'
            owner = self.request.get('owner')
            owned = set(PosOwner.query(PosOwner.owner == owner).map(lambda o: o.location))
            towers = filter(lambda t: ('%s %s-%d' % (t.system_name, roman(t.planet), t.moon)) in owned, towers)
        self.write_json(towers)

class TowerHandler(JsonHandler):
    def get(self, tower_id):
        if not self.logged_in:
            self.session['referer'] = webapp2.uri_for('posmon')
            return self.redirect_to('login')
        if self.session['alliance_id'] != self.config.alliance_id:
            _log.debug('Alliance: %s != %s' % (self.session['alliance_id'], self.config.alliance_id))
            self.session['referer'] = webapp2.uri_for('posmon')
            return self.redirect_to('logout')
        _log.debug('Get tower %s' % tower_id)
        tower = Tower.get_by_id(int(tower_id))
        if tower is None:
            self.abort(404)
        else:
            self.write_json(tower)

class PosmonHandler(BaseHandler):
    def get(self):
        if not self.logged_in:
            return self.redirect_to('login')
        if self.session['alliance_id'] != self.config.alliance_id:
            _log.debug('Alliance: %s != %s' % (self.session['alliance_id'], self.config.alliance_id))
            return self.redirect_to('logout')
        template = open(os.path.join(os.path.dirname(__file__), 'posmon.html'))
        self.response.write(template.read())

class SrpHandler(BaseHandler):
    def get(self):
        template = open(os.path.join(os.path.dirname(__file__), 'srp.html'))
        self.response.write(template.read())

config = {}
config['webapp2_extras.sessions'] = {
    'secret_key': 'test_key',
}

app = webapp2.WSGIApplication([

    # Auth Handlers
    webapp2.Route('/login', handler=LoginHandler, name='login'),
    webapp2.Route('/logout', handler=LogoutHandler, name='logout'),
    webapp2.Route('/eveauth', handler=EveSSOAuthHandler, name='eveauth'),

    # Public json handlers
    routes.PathPrefixRoute('/json', [
        webapp2.Route('/config', handler=ConfigHandler, name='jsonConfig'),
        webapp2.Route('/kills', handler=KillsHandler, name='jsonKills', methods=['GET','POST']),
        webapp2.Route('/kills/<kill_id>', handler=KillHandler, name='jsonKill'),
        webapp2.Route('/characters', handler=CharactersHandler, name='jsonCharacters'),
        webapp2.Route('/characters/<character_id>', handler=CharacterHandler, name='jsonCharacter'),
        webapp2.Route('/payments', handler=PaymentsHandler, name='jsonPayments'),
        webapp2.Route('/payments/<payment_id>', handler=PaymentHandler, name='jsonPayment'),
        webapp2.Route('/towers', handler=TowersHandler, name='towers'),
        webapp2.Route('/towers/<tower_id>', handler=TowerHandler, name='tower'),
        webapp2.Route('/search/<search_text>', handler=SearchHandler, name='jsonSearch'),
    ]),

    routes.PathPrefixRoute('/ofsoundsrp', [
        # Handlers for pages that need to work in the in game browser
        routes.PathPrefixRoute('/igb', [
            webapp2.Route('/payments/pay/<payment_id>', handler=IGBPayHandler, name='igbpay'),
            webapp2.Route('/payments', handler=IGBPaymentsHandler, name='igbpayments'),
        ]),
        webapp2.Route('/', handler=SrpHandler, name='srp'),
        webapp2.Route('', handler=webapp2.RedirectHandler, defaults={'_uri': '/ofsoundsrp/'}),
    ]),
    webapp2.Route('/ofsoundposes/', handler=PosmonHandler, name='posmon'),
    webapp2.Route('/ofsoundposes', handler=webapp2.RedirectHandler, defaults={'_uri': '/ofsoundposes/'}),
    webapp2.Route('/posmon/', handler=webapp2.RedirectHandler, defaults={'_uri': '/ofsoundposes/#/posmon'}),
    webapp2.Route('/posmon', handler=webapp2.RedirectHandler, defaults={'_uri': '/ofsoundposes/#/posmon'}),
], config=config, debug=True)

characters = []
Character.query().map(lambda c: characters.append((c.character_name, c.character_id)))

