# Supplemental upstream notices

These two cached Python wheels contain no license-text member. The files beside this index preserve the exact upstream text identified through retained wheel-member hashes and official source records. They supplement the metadata inventory in [THIRD-PARTY-NOTICES.md](../THIRD-PARTY-NOTICES.md). No wheel metadata is changed.

**ANTLR Python runtime 4.9.3.** [Complete upstream license](antlr4-python3-runtime-4.9.3-LICENSE.txt), copyright 2012–2017 The ANTLR Project. The official `4.9.3` tag resolves to commit `e4c1a74c66bd5290364ea2b36c97cd724b247357`. Its Python setup declares 4.9.3, and `Recognizer.py` matches the retained wheel member. That source header identifies the BSD 3-clause license. The full upstream file also contains an MIT section explicitly scoped to `codepointat.js` and `fromcodepoint.js`; this is not a claim that those JavaScript files ship in the Python wheel.

- Cached wheel: `antlr4_python3_runtime-4.9.3-py3-none-any.whl`, 144,613 bytes, SHA-256 `d50ab331bff062b5e7f74e19fb16a2e891a47e893d805bcdbff8e6e6beb09c37`.
- Notice: 2,699 bytes, SHA-256 `b1b379fcaf3219593a4c433feb1b35c780bed23fafaae440b1ae2771a9521e3a`.
- Sources: [versioned license](https://github.com/antlr/antlr4/blob/e4c1a74c66bd5290364ea2b36c97cd724b247357/LICENSE.txt), [matching Python source header](https://github.com/antlr/antlr4/blob/e4c1a74c66bd5290364ea2b36c97cd724b247357/runtime/Python3/src/antlr4/Recognizer.py).

**Proxy-tools 0.1.0: metadata conflict retained.** [Complete upstream license](proxy-tools-0.1.0-UPSTREAM-LICENSE.txt), copyright 2013 Armin Ronacher and 2014 Jonathan Tushman. The wheel/PyPI metadata and historical `setup.py` declare MIT. The matching source header and repository license instead say BSD. This index reports both declarations; it does not choose an SPDX identifier or resolve the conflict. The license file is unchanged, including its literal `<COPYRIGHT HOLDER>` placeholder and malformed trailing sentence.

- Cached wheel: `proxy_tools-0.1.0-py3-none-any.whl`, 2,943 bytes, SHA-256 `a049f8570f5ce89b723ba282b90291ac3aa1fdcbd7d7100426ff659447400c68`.
- Notice: 1,436 bytes, SHA-256 `a428fb8a2e762af3eb0a6edbbb88e9b42ccfee80fd9b423958bcacf9b9abbfe4`.
- Official pre-upload commit `f82ae43524fd6d9917b0e9490c7d0394dff8d155` declares 0.1.0; the package module matches the retained wheel member. The captured official tag list was empty. This does not establish an exact release commit or publisher-signed artifact.
- Sources: [historical license](https://github.com/jtushman/proxy_tools/blob/f82ae43524fd6d9917b0e9490c7d0394dff8d155/LICENSE.txt), [matching source header](https://github.com/jtushman/proxy_tools/blob/f82ae43524fd6d9917b0e9490c7d0394dff8d155/proxy_tools/__init__.py), [conflicting setup metadata](https://github.com/jtushman/proxy_tools/blob/f82ae43524fd6d9917b0e9490c7d0394dff8d155/setup.py).

These notices do not establish legal clearance, authenticate every package member, or qualify package installation, script execution or model behavior.
