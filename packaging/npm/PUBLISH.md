# Publishing `uoink` to npm (owner steps)

Nothing in the repo publishes this package. You do it once with your own npm account.

## First publish

1. Check the name is still free: `npm view uoink` should say 404.
2. `npm login` (create an account at npmjs.com first if you need one).
3. Turn on two-factor auth for writes: npmjs.com > Account > Two-Factor Authentication > "Authorization and publishing".
4. From this folder:

   ```sh
   cd packaging/npm
   node --test
   npm pack --dry-run        # expect 6 files: LICENSE, README.md, bin/uoink.js, lib/main.js, lib/net.js, package.json
   npm publish --access public
   ```
5. Check it: `npx uoink --help`, then `npx uoink --dry-run` in a scratch folder.

`package.json` `version` must equal the repo `VERSION` file (a test enforces it), and the first publish ships that version.

## Later releases

1. When the repo `VERSION` changes, set `version` in `packaging/npm/package.json` to the same value.
2. `node --test`, then `npm publish --access public` from `packaging/npm`.
3. The package never contains the installer. `npx uoink` always fetches the latest GitHub release, so a stale package still installs the newest Uoink. Bump it anyway so the versions line up.

Never publish with a token in the repo or in `.npmrc` inside it. Use `npm login`.
