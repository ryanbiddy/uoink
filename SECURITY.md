# Security Policy

Uoink is a local-first tool: extraction and your files stay on your machine,
and there is no Uoink cloud library or account system.

Uoink sends no usage data by default. If you turn on "Share anonymous usage counts", it sends daily counts to usage.uoink.app: calls by tool name, known MCP clients, stdio or HTTP calls, captures by source and result, and library searches. Reports include a random install ID, app version, operating system and major version, processor type, install type and hours counted. They never include content, URLs, titles, paths, search text, usernames, IP addresses or account details.
See [`docs/security.md`](docs/security.md) for the full threat model and the
details of what the helper does and does not do.

## Reporting a vulnerability

If you find a vulnerability, please **report it to hi@uoink.video** or open a
private [GitHub Security Advisory](https://github.com/ryanbiddy/uoink/security/advisories).

Please do not open a public issue with reproduction details until a fix has
shipped. We'll acknowledge your report and keep you posted on the fix.
