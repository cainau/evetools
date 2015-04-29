import logging
from config import ConfigSection
from evelink.account import Account
from evelink.api import API
from evelink.cache.sqlite import SqliteCache
from evelink.char import Char

_config = ConfigSection('eveapi')
_log = logging.getLogger('sound.srp.be.eveapi')

def get_key_config(key_name):
    key_config = ConfigSection('apikey:%s' % key_name)
    key_id = int(key_config.get_option('key_id'))
    v_code = key_config.get_option('v_code')
    return key_id, v_code

def get_api_key(key):
    if isinstance(key, API):
        return key
    key_id, v_code = get_key_config(key)
    return API(api_key=(key_id, v_code), cache=SqliteCache(_config.get_option('cache_location')))

def get_characters(key):
    key = get_api_key(key)
    acc = Account(key)
    return acc.characters().result

