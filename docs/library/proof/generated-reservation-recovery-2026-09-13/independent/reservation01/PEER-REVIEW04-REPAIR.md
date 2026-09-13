# Duplicate lease finalization correction

Independent source review found that the base lease's harmless second exit
caused the durable wrapper to retry completion. A successful first completion
had already removed the live reservation, so this retry incorrectly quarantined
the released lifecycle record. The unexecuted draft is retained under
`before-peer-review04/`.

Durable exit will be one-shot under the manager lock. A repeated exit returns
without repeating guard release, journal writes, or finalization. A failed first
completion remains failed and held; a second exit cannot act as reconciliation.
Two generated controls cover successful and failed-clear repeated exit. Existing
37 case bodies remain unchanged, with the planned method count now 39. No
qualification has executed.
