import logging
import sys
from config import ConfigSection
from datastore import Character, Corporation, KillMail, Payment, PaymentDetail, Control
from datetime import datetime, timedelta
import eveapi

_config = ConfigSection('paymentconsolidator')
_log = logging.getLogger('sound.srp.be.paymentconsolidator')

def process(kill, payment):
    if kill.srp_amount is None:
        return False
    if kill.payments is None:
        kill.payments = []
    check = sum([p.amount for p in kill.payments])
    if check == kill.srp_amount:
        return False
    _log.info('Processing kill %d, payment %d, srp_amount %d, paid_amount %d' %
            (kill.kill_id, payment.payment_id, kill.srp_amount, kill.paid_amount or 0))
    current = kill.srp_amount - check
    detail = None
    for det in kill.payments:
        if det.payment_id == payment.payment_id:
            detail = det
    if current != 0:
        payment.payment_amount += current
        if detail is None:
            detail = PaymentDetail(payment.payment_id, kill.kill_id, current)
            kill.payments.append(detail)
            payment.losses.append(detail)
        else:
            detail.amount += current
            for det in payment.losses:
                if det.kill_id == kill.kill_id:
                    det.amount += current
                    break
        kill.save()
        payment.save()
        return True
    return False

def run():
    if '-k' in sys.argv:
        idx = sys.argv.index('-k')
        kill = KillMail(int(sys.argv[idx+1]))
        process(kill)
        return
    look_back_days = int(_config.get_option('look_back_days'))
    _log.info('Consolidating payments for losses for the past %d days.' % look_back_days)
    outstanding_payments = { p.character_id: p for p in Payment.all_outstanding() }
    start_time = datetime.now() - timedelta(look_back_days)
    control = Control()
    for kill in KillMail.losses_after(start_time):
        cid = kill.victim.character_id
        if cid not in outstanding_payments:
            _log.info('Creating new payment for character %d.' % cid)
            p = Payment(control.next_payment_id)
            p.character_id = cid
            p.character_name = kill.victim.character_name
            p.corp_id = kill.victim.corporation_id
            p.corp_name = kill.victim.corporation_name
            p.payment_amount = 0
            if process(kill, p):
                control.next_payment_id += 1
                outstanding_payments[cid] = p
                control.save()
        else:
            process(kill, outstanding_payments[cid])
    _log.info('Checking for out of alliance / declining SRP.')
    alliance_id = int(_config.get_option('alliance_id'))
    for cid, payment in outstanding_payments.iteritems():
        c = Character(cid)
        eveapi.update_character(c)
        corp = Corporation(c.corp_id)
        ignore = c.alliance_id != alliance_id or c.declined_srp or not corp.srp
        if ignore != payment.ignore:
            payment.ignore = ignore
            payment.save()

if __name__ == '__main__':
    run()
