# Exact redistribution notice proposal

Add the two files in `notices/` to the release's third-party notice directory and list them in its attribution index. Keep their bytes unchanged. This proposal does not modify wheel metadata or approve installation.

| Component | Proposed notice | Evidence and unresolved point |
| --- | --- | --- |
| antlr4-python3-runtime 4.9.3 | `antlr4-python3-runtime-4.9.3-LICENSE.txt` | The official 4.9.3 tag labels the license BSD 3-clause. The complete root license also includes an MIT section explicitly scoped to two JavaScript files; retain the full upstream file without implying those JavaScript files are in this Python wheel. |
| proxy-tools 0.1.0 | `proxy-tools-0.1.0-UPSTREAM-LICENSE.txt` | Official source and license say BSD, while setup.py and wheel/PyPI metadata say MIT. Preserve the actual upstream text and both copyright lines. Do not publish an MIT-only attribution or silently assign an SPDX variant. |

For ANTLR, attribute The ANTLR Project, copyright 2012–2017, and point to the retained upstream license. For proxy-tools, attribute Armin Ronacher, copyright 2013, and Jonathan Tushman, copyright 2014, and point to the retained upstream license. The proxy-tools file has a literal `<COPYRIGHT HOLDER>` placeholder and a malformed trailing sentence. These are upstream bytes, not editorial corrections.

The integrator still needs to decide the release's treatment of the proxy-tools metadata conflict and verify that the final installer actually carries both notices. Adding these files supplies the missing notice text; it does not prove a complete legal review of every packaged file.
