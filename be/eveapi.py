import logging
from config import ConfigSection
from evelink.account import Account
from evelink.api import API
from evelink.cache.sqlite import SqliteCache
from evelink.char import Char
from evelink.eve import EVE

_config = ConfigSection('eveapi')
_log = logging.getLogger('sound.srp.be.eveapi')

def get_key_config(key_name):
    key_config = ConfigSection('apikey:%s' % key_name)
    key_id = int(key_config.get_option('key_id'))
    v_code = key_config.get_option('v_code')
    entity_id = key_config.get_option('id')
    if entity_id is not None:
        entity_id = int(entity_id)
    return key_id, v_code, entity_id

def get_api_key(key):
    if isinstance(key, API):
        return key
    key_id, v_code, entity_id = get_key_config(key)
    return API(api_key=(key_id, v_code), cache=SqliteCache(_config.get_option('cache_location')))

def get_characters(key):
    key = get_api_key(key)
    acc = Account(key)
    return acc.characters().result

def update_character(character):
    eve = EVE()
    affiliations = eve.affiliations_for_character(character.character_id).result
    updated = False
    if character.corp_id != affiliations['corp']['id']:
        character.corp_id = affiliations['corp']['id']
        character.corp_name = affiliations['corp']['name']
        updated = True
    if 'alliance' not in affiliations:
        updated = character.alliance_id != 0
        character.alliance_id = 0
        character.alliance_name = ''
    elif ((not character.alliance_id and 'alliance' in affiliations) or
        character.alliance_id != affiliations['alliance']['id']):
        character.alliance_id = affiliations['alliance']['id']
        character.alliance_name = affiliations['alliance']['name']
        updated = True
    if updated:
        character.save()

