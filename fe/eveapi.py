import json
import logging
import urllib2
from evelink.eve import EVE

_log = logging.getLogger('sound.eveapi')

def get_character(access_token):
    url = 'https://login.eveonline.com/oauth/verify'
    headers = {}
    headers['Authorization'] = 'Bearer %s' % access_token
    req = urllib2.Request(url, None, headers)
    resp = urllib2.urlopen(req)
    data = resp.read()
    _log.debug('OAuth verify Response: %s' % data)
    data = json.loads(data)
    character_id = data['CharacterID']
    character_name = data['CharacterName']
    return (character_id, character_name)

def get_alliance(character_id):
    _log.debug('Get alliance for character %d' % character_id)
    res = EVE().affiliations_for_characters([character_id]).result
    character = res[character_id]
    return int(character['alliance']['id']) if 'alliance' in character else 0
    
