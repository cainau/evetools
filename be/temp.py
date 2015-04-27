from datastore import *

kms = KillMail.all_after(45547000)
tosave = []
for km in kms:
  if km.final_blow is None:
      print km
      km.final_blow = filter(lambda a: a.final_blow, km.attackers)
      tosave.append(km)
      if len(tosave) >= 5:
          KillMail.bulk_save(tosave)
          tosave = []
if len(tosave) > 0:
    KillMail.bulk_save(tosave)

