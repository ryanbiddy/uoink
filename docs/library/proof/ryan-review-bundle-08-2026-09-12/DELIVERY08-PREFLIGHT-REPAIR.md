# Documentary preflight reader correction, 2026-09-12

The first AST preflight for update_release08_documents.py exited 1 before parsing:
Path.read_text() used the Windows cp1252 default and failed on UTF-8 quotation
bytes at position 14232. It did not execute that script, edit release notes or
run a product/client observation. Its terminal traceback remains in the task.

The corrected preflight explicitly reads encoding='utf8' before ast.parse.
Run it once under a fresh preflight02 record. The source is unchanged; there is
no fixture, assertion or outcome change. Retain both exits in the delivery proof.
