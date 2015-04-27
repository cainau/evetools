import logging
import web
import xml.etree.ElementTree as ET
from beaker.cache import CacheManager
from beaker.util import parse_cache_config_options
from config import ConfigSection
from staticdata import MapSolarSystem, MapRegion, InvType

_config = ConfigSection('market')
_log = logging.getLogger('sound.srp.be.market')

jita_id = MapSolarSystem.by_name('Jita').solarSystemID
forge_id = MapRegion.by_name('The Forge').regionID
cache = CacheManager(**parse_cache_config_options(
    { 'cache.type': _config.get_option('cache_type') }))

@cache.cache('get_jita_price')
def get_jita_price(type_id):
    _log.debug('Getting Jita sell price for type %d.' % type_id)
    url = 'http://api.eve-central.com/api/quicklook?typeid=%d&usesystem=%d' % (type_id, jita_id)
    response = web.fetch_url(url)
    root = ET.fromstring(response)
    sell_orders = root.find('quicklook').find('sell_orders')
    price = None
    for order in sell_orders.findall('order'):
        p = float(order.find('price').text)
        if price is None or p < price:
            price = p
    if price is None:
        _log.info('No Jita price found for type %d.' % type_id)
    else:
        _log.debug('Jita price found for type %d: %f.' % (type_id, price))
    return price

@cache.cache('get_forge_price')
def get_forge_price(type_id):
    _log.debug('Getting The Forge sell price for type %d.' % type_id)
    url = 'http://api.eve-central.com/api/quicklook?typeid=%d&regionlimit=%d' % (type_id, forge_id)
    response = web.fetch_url(url)
    root = ET.fromstring(response)
    sell_orders = root.find('quicklook').find('sell_orders')
    price = None
    for order in sell_orders.findall('order'):
        p = float(order.find('price').text)
        if price is None or p < price:
            price = p
    if price is None:
        item = InvType.by_id(type_id)
        _log.warning('No Forge price found for %s (type %d).' % (item.typeName, type_id))
    else:
        _log.debug('Forge price found for type %d: %f.' % (type_id, price))
    return price

@cache.cache('get_base_price')
def get_base_price(type_id):
    _log.debug('Getting the base price for type %d. ' % type_id)
    item = InvType.by_id(type_id)
    return float(item.basePrice)

def get_default_price(type_id):
    return get_jita_price(type_id) or get_forge_price(type_id) or get_base_price(type_id)

