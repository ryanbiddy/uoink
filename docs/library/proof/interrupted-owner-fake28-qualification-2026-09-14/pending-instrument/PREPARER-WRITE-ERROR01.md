# Preparation write error

The first functions.exec attempt to write the text preparer failed during JavaScript parsing with `SyntaxError: Unexpected identifier 'nimport'`: embedded PowerShell backticks ended the JavaScript template. No nested tool ran and no preparer or candidate source was written by that attempt. The following write uses an explicit line-feed variable. This is an orchestration preparation error, with no candidate result.
