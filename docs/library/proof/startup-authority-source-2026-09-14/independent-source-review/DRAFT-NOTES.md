The initial adapter was read at SHA-256 6082c916bb486b1fdbab441e98a2a191d144fb82fa206ae3298a38e96b2d68f8. The later e92ee8711e618bc477f4527bad47febae2c941e183926b56dc2aebce56959166 draft adds the root-requested exact OwnedSession check before consumption. Neither source was executed by this reviewer.

One ordering finding was sent to root: manager.read_lease invokes the trusted binding callback before returning. The draft enters the returned lease before rechecking the selected configuration. A changed release/profile from that callback therefore reaches reservation and read-guard work before refusal. A selection check immediately before lease entry is the proposed narrow correction. This is a prospective source finding, not a measured failure.

The actual permit contract stores the permit identity object in record.permit; the new comparison is correct. The actual durable factory installs the OwnedSession before delegate.create_suspended, with the reservation still RESERVED and no worker/resume attempt. The proposed consumption predicate matches that stage. The shared lock order is manager then reservation. Current validation performs state/identity checks without journal or worker calls.

The current unused-reservation predicate is not independent native handle, physical-directory, or authenticated child evidence. The worker seam remains explicitly closed. No additional reachable gate-loss finding was established under the existing trusted private service contract.

The first remaining-contract read (473a47, exit 1) failed in this reviewer's PowerShell range formatting after reading the reservation gate source. The corrected explicit first/last read (6a90d6, exit 0) supplied the missing durable startup and current adapter ranges. This was a passive reader failure; no subject code ran or changed.

Final review awaits the author's frozen source and map. Root owns the full proposed test and first-error review.
