import ConfigParser
import logging

_config_parser = ConfigParser.SafeConfigParser()
_config_parser.read('eve.ini')

class ConfigSection:
    def __init__(self, section):
        self.section = section

    def options(self):
        return _config_parser.options(self.section)

    def get_option(self, option):
        if self.has_option(option):
            return _config_parser.get(self.section, option)
        else:
            return None

    def has_option(self, option):
        return _config_parser.has_option(self.section, option)

def parse_log_level(level_name):
    levels = {
        'debug': logging.DEBUG,
        'info': logging.INFO,
        'warning': logging.WARNING,
        'error': logging.ERROR,
        'critical': logging.CRITICAL
    }
    default_level = logging.WARNING
    return levels.get(level_name.lower()) or default_level

_config = ConfigSection('common')

log_level = parse_log_level(_config.get_option('log_level'))
log_format = _config.get_option('log_format')
if log_format is None or log_format == '':
    log_format = '%(levelname)s (%(asctime)s): %(message)s'

logging.basicConfig(format=log_format, level=log_level)

