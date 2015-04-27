import logging
from config import ConfigSection
from datastore import Payment
from datetime import datetime, timedelta
from evelink.api import API, APIError
from evelink.cache.shelf import ShelveCache
from evelink.corp import Corp
from eveapi import get_api_key

_config = ConfigSection('paymentverifier')
_log = logging.getLogger('sound.srp.be.paymentverifier')

def get_wallets():
    for wallet in _config.get_option('wallets').split(','):
        parts = wallet.split('-')
        ticker = parts[0]
        division = int(parts[1])
        yield (ticker, division)

def get_journal_entries():
    lookBackDays = int(_config.get_option('look_back_days'))
    startTime = datetime.now() - timedelta(lookBackDays)
    for ticker, division in get_wallets():
        key = get_api_key(ticker)
        corpApi = Corp(key)
        finished = False
        journal = corpApi.wallet_journal(account = division).result
        while not finished:
            for entry in journal:
                time = datetime.utcfromtimestamp(entry['timestamp'])
                if time > startTime:
                    yield entry
                else:
                    finished = True
            if not finished:
                journal = corpApi.wallet_journal(account = division, before_id = journal[0]['id']).result

def verify_payments():
    for journalEntry in get_journal_entries():
        reason = journalEntry['reason']
        if reason.startswith('DESC: '):
            reason = reason[6:].strip()
        if reason.startswith('SRP '):
            reason = reason[4:].strip()
            if reason.startswith('P'):
                reason = reason[1:].strip()
            paymentId = int(reason)
            payment = Payment(paymentId)
            if journalEntry['party_2']['id'] != payment.character_id:
                _log.critical('Payment %d paid to %s when it should have been to %s.' % (
                    paymentId, journalEntry['party_2']['name'], payment.character_name))
                continue
            payment.paid = True
            payment.paid_date = datetime.utcfromtimestamp(journalEntry['timestamp'])
            payment.paid_by = journalEntry['arg']['id']
            payment.paid_by_name = journalEntry['arg']['name']
            payment.api_amount = -journalEntry['amount']
            payment.api_verified = True
            payment.save()
            _log.info('Payment %d (%dM to %s) verified.' % (
                paymentId, payment.payment_amount, payment.character_name))
            if payment.api_amount != payment.payment_amount * 1000000:
                _log.warning('Payment %d API amount %d does not match payment amount %d.' % (
                    paymentId, payment.api_amount, payment.payment_amount))

if __name__ == '__main__':
    verify_payments()

