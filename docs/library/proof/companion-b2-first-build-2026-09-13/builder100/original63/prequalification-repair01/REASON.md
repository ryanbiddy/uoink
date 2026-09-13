# Bounded reads before qualification — 2026-09-13

Root reviewed the initial utility before any test execution and identified a
resource gap: stat checks followed by read_bytes do not bound allocation if an
input grows or is replaced between those operations. The same issue affected
recipe inputs. This is a prequalification source-review correction, not a
failed measurement. Initial utility and test bytes are preserved here.

Replace reads with one explicit cap-plus-one read from a regular-file handle,
checking pathname/handle identities and size/mtime before and after where
available. Pin exact recipe sizes as well as hashes, cap the utility's own
provenance read, and bound the written-wheel comparison. Add a synthetic growing
stream case that asserts the requested read size and refusal before an unbounded
read, plus size and identity-change negatives.

These checks reduce resource and accidental concurrent-change risks. They are
not atomic Windows path protection against a hostile process with the same
user rights. Preparation still requires quiescent local paths. The ZIP parser's
member-count checks occur after ZipFile reads the bounded central directory;
do not claim preallocation count enforcement. Production input passes the exact
bounded wheel-size/hash gate before ZIP parsing.
