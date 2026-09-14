# windows-reservation01: failed fixture contract review

The first observation remains FAILED: 63 passed, 2 failed, 0 skipped over 65
ordered cases. Of 33 nested subtests, 6 failed. Native, qualification and actual
outer exits were 1. All ten guard fields, membership and input bindings were
valid; stderr was empty and no boundary denials were recorded. The case interval
was 0.09428690001368523 s; launcher 0.6907775 s; actual outer 1.1805151 s.
The raw root tool object is WINDOWS-RESERVATION01-ACTUAL.json, chunk5275b2.
No rerun, source change or assertion change has been made.

The two new tests selected the wrong exception class:

- test_started_or_reserved_native_state_cannot_claim_no_worker_cleanup expected
  AssertionError for all six faults. The source refused with KernelUnconfirmed;
  five faults used current_no_worker_reservation_before_guard_retirement, and
  the owner fault used dummy_release_requires_observed_native_exit.
- test_old_completion_cannot_clear_fresh_lease_record expected AssertionError
  matching current_retired_lifetime_required. The source raised KernelUnconfirmed
  with that exact message.

This is a mismatch in newly written synthetic expectations. The preserved
original and current generated_worker_flow._assert, lines28–30, both explicitly
raise KernelUnconfirmed. The unchanged win32_worker_connection defines that as
a RuntimeError subclass at line14, not an AssertionError subclass. The failure
therefore does not establish a change in production exception behavior. Changing
the product to raise AssertionError would conflict with the existing contract
and is not proposed.

The controls intend to verify refusal and retained gate/guards, plus absence of
new cleanup credit. Their post-refusal assertions remain meaningful. However,
those assertions after the mismatched assertRaises context did not complete in
these failing branches. The failed run cannot be relabeled as having verified
all cleanup assertions. A corrected, separately admitted observation is needed.

Requested narrow fixture disposition, not applied: import the existing exact
KernelUnconfirmed source class and change only the two new assertRaises class
arguments from AssertionError to KernelUnconfirmed. Keep the old-completion regex,
all six fault inputs, every retention/cleanup assertion, all 42 baseline bodies,
and all product/port bytes unchanged. Keep count65 and preserve this failed run.
Any later attempt needs a fresh brief, pins, label and root review before execution.

Blocker for root/Ryan: root explicitly froze these assertions after the failure.
The requested correction concerns two new synthetic tests and is outside Ryan's
five specifically named September9 fixture corrections. Root should record the
narrow fixture ruling under Blockers for Ryan if the standing acceptance rule
requires owner authorization here. This review does not supply that authorization.
Independent repetition is held until the contract disposition is recorded.