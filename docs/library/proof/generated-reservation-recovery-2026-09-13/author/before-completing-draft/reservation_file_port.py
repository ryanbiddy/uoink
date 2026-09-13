"""Bounded journal I/O over an injected retained stream; no path is opened here."""
from threading import RLock

MAX_JOURNAL = 4 * 1024 * 1024


class PersistenceUnconfirmed(RuntimeError):
    pass


class RetainedJournal:
    """Trusted generated bootstrap supplies the stream and exact identity probe.

    stream must provide seek/read/write/flush. sync(stream) must perform the
    actual durability operation and return exactly True only on confirmation.
    identity(stream) must return the bound immutable file identity. These are
    injected trusted services, not runtime permission or a production gate.
    A real implementation must bind its native handles and cancellation rules.
    """

    def __init__(self, stream, identity, expected_identity, sync):
        self._stream, self._identity, self._sync = stream, identity, sync
        self._expected = expected_identity
        self._lock = RLock()
        self._poisoned = False

    def _check(self):
        if self._poisoned or self._identity(self._stream) != self._expected:
            raise PersistenceUnconfirmed("retained_journal_identity_unconfirmed")

    def read_all(self):
        with self._lock:
            self._check()
            self._stream.seek(0)
            chunks, total = [], 0
            while True:
                chunk = self._stream.read(min(65536, MAX_JOURNAL + 1 - total))
                if type(chunk) is not bytes:
                    raise PersistenceUnconfirmed("journal_read_result")
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
                if total > MAX_JOURNAL:
                    raise PersistenceUnconfirmed("journal_size_bound")
            self._check()
            return b"".join(chunks)

    def append_confirmed(self, expected_before, frame):
        if type(expected_before) is not bytes or type(frame) is not bytes or not frame:
            raise PersistenceUnconfirmed("journal_append_arguments")
        if len(expected_before) + len(frame) > MAX_JOURNAL:
            raise PersistenceUnconfirmed("journal_size_bound")
        with self._lock:
            try:
                self._check()
                if self.read_all() != expected_before:
                    raise PersistenceUnconfirmed("journal_changed_before_append")
                self._stream.seek(len(expected_before))
                offset = 0
                while offset < len(frame):
                    written = self._stream.write(frame[offset:])
                    if type(written) is not int or not 0 < written <= len(frame) - offset:
                        raise PersistenceUnconfirmed("journal_short_write_unconfirmed")
                    offset += written
                self._stream.flush()
                if self._sync(self._stream) is not True:
                    raise PersistenceUnconfirmed("journal_sync_unconfirmed")
                self._check()
                if self.read_all() != expected_before + frame:
                    raise PersistenceUnconfirmed("journal_readback_differs")
                return expected_before + frame
            except BaseException:
                # Never truncate or fabricate a rollback: complete bytes may
                # remain visible after a failed flush or interrupted readback.
                self._poisoned = True
                raise


def real_journal_port(*args, **kwargs):
    raise PersistenceUnconfirmed("real_file_exclusion_and_durability_are_not_admitted")
