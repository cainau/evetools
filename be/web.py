import logging
import urllib2
import zlib
from config import ConfigSection

_config = ConfigSection('web')
_log = logging.getLogger('sound.srp.be.web')

def fetch_url(path):
    _log.debug('Fetching url: ' + path)
    resp = None
    try:
        req = urllib2.Request(path)
        req.add_header('Accept-Encoding', 'gzip')
        req.add_header('User-agent', _config.get_option('user_agent'))
        resp = urllib2.urlopen(req)
    except urllib2.HTTPError as e:
        _log.error('HTTPError(%d): %s' % (e.code, e.reason))
        raise e
    except urllib2.URLError as e:
        _log.error('URLError: %s' % e.reason)
        raise e

    try:
        content = resp.read()
        if resp.info().get('Content-Encoding') == 'gzip':
            _log.debug('Decompressing response.')
            content = zlib.decompress(content, 32 + zlib.MAX_WBITS)
        return content
    finally:
        resp.close()

