# Submit Uoink 3.11 to the Chrome Web Store

Allow about 15 minutes for the dashboard work once your images and helper
release are ready. Account verification, helper packaging, screenshot capture
and Google's review are extra. Ryan does every account, payment, upload and
submission step. Nothing in this worktree publishes anything.

## Before opening the dashboard

Have these ready:

- `dist/uoink-extension-3.11.0-cws.zip`, built with `python scripts/build_cws.py`.
- `listing.md`, `permissions-justification.md`, `privacy-practices.md` and
  `reviewer-test-instructions.md` from this folder.
- At least one fresh 1280x800 screenshot from `SCREENSHOTS.md`, preferably the
  YouTube capture and helper setup shots. Do not use the July images unchanged.
- `extension/icons/icon128.png`; optional small and marquee tiles in `tiles/`.
- A monitored support email. Verify that `hi@uoink.app` receives mail.
- The Limited Use statement from `privacy-practices.md`, published on
  https://uoink.app/privacy. The live policy already covers opt-in usage counts.

The public v3.11.0 Windows installer exists. It does not yet contain the changes
in this worktree or a store item ID. You can create the draft now, but finish the
helper identity/release step below before submitting for review. This pass has
not changed any release version or replaced any public download.

## 1. Register and secure the account, about 3 minutes

1. Open the [Chrome Web Store Developer Dashboard](https://chrome.google.com/webstore/devconsole/).
2. Sign in with the Google account you want to own Uoink. Read and accept the
   developer agreement and policies, then pay the **$5 one-time registration
   fee** shown in registration. Ryan pays it himself.
3. In [Google Account security](https://myaccount.google.com/security), enable
   **2-Step Verification** if it is not already enabled. Return to the dashboard.
4. Open **Account**. Complete the publisher name, contact email and any required
   verification or trader declarations truthfully. Verify the email if prompted.

Google documents [registration](https://developer.chrome.com/docs/webstore/register)
and [2-Step Verification](https://developer.chrome.com/docs/webstore/program-policies/policies#2-step_verification).
Its current [publisher announcement](https://developer.chrome.com/docs/extensions/whats-new)
also references the $5 registration fee. Extra account checks can take longer.

## 2. Create the draft and copy its ID, about 2 minutes

5. Click **Add new item** (or **New item**).
6. Click **Browse files**, select `dist/uoink-extension-3.11.0-cws.zip`, then
   upload it. Confirm the detected name is **Uoink**, version **3.11.0**, MV3.
7. Open **Package**. Copy the **Item ID**, a 32-letter string. It exists now,
   before review. **View public key** on this tab is for matching development
   installs to that item; do not replace Uoink's existing developer key.
8. Open `extension/store-config.json` in this worktree. Paste the copied ID
   between the empty quotes for **`chrome_web_store_id`**. Leave
   **`chrome_web_store_url`** empty until the public listing works.

Google's [manifest key guide](https://developer.chrome.com/docs/extensions/reference/manifest/key)
documents the draft-item/public-key flow. The store ID is separate from the
bundled developer ID `bkcapfidedhfcjpmjabeopfbcjcbmdmi`.

**Helper release gate:** ship this worktree's `uoink_store.py`, updated helper,
and `extension/store-config.json` in the Windows helper release. `build.ps1`
already stages them. The store ID is accepted alongside the developer ID.
Existing `UOINK_EXTENSION_IDS` or settings `extension_ids` also add exact IDs
for controlled tests, but should not be a normal user's installation step.

The first uploaded zip can keep its blank store config: Chrome supplies its
runtime ID, and the helper is the part that must trust it. No second upload is
needed just to register the ID. If the helper needs a new approved release,
coordinate its download target in `extension/setup.js` and the release version
surfaces through the normal release process before submitting. Do not silently
replace the already-published installer. A revised store package must follow
Google's [version increase rule](https://developer.chrome.com/docs/webstore/update).

Before review, test a real capture using that identity in a disposable profile.
For a local identity test, put the draft item's public key in a separate extracted
copy only. Keep the repository's developer key unchanged. Do not advertise the
store link until the public helper accepts the store ID.

## 3. Fill in the listing, about 6 minutes

9. Open **Store listing**. Confirm the manifest's name and summary, then paste
   **Detailed description** from `listing.md`. Set the category and language
   from that file. Fill website, support URL, support email and privacy URL
   wherever the dashboard offers those fields.
10. Upload `extension/icons/icon128.png` if requested and the fresh screenshots
    in their intended order. Optional: add the 440x280 small tile and 1400x560
    marquee. Skip the 920x680 spare. Save the page.
11. Open **Privacy practices**. Paste the single-purpose paragraph and each
    permission justification. Select **No, I am not using remote code**.
    Complete the data-type table and three certifications in
    `privacy-practices.md`. Enter **https://uoink.app/privacy**. Save.
12. Open **Test instructions**. Paste `reviewer-test-instructions.md`. No test
    account is needed. Verify the helper download now recognizes this item ID.
13. Open **Distribution**. Select **Free** and **Public** for a searchable
    listing, or **Unlisted** if you only want installation by link. Choose the
    countries where you want to offer it and answer content questions. Save.

Google's [publishing guide](https://developer.chrome.com/docs/webstore/publish)
describes these tabs. Dashboard labels can change; keep the field values above.

## 4. Submit, about 2 minutes

14. Resolve any incomplete-field messages. Check the helper requirement is
    prominent, the privacy URL opens without sign-in, and the images show 3.11.
15. Click **Submit for review**. In the confirmation dialog, turn off automatic
    publication so you can coordinate the helper and website. Confirm submission.
16. Enable review/staged notifications on **Account** and monitor that inbox.

Most reviews finish in a few days, but some take a few weeks. Google says to
seek developer support if review exceeds three weeks. New publishers, new
items and sensitive permissions can add time. See the [review process](https://developer.chrome.com/docs/webstore/review-process).
There is no guaranteed approval date. Once approved with deferred publishing,
Google gives you up to 30 days to publish before the staged item returns to draft.

## 5. Publish and turn on link installation

17. Once approved and the helper is ready, click **Publish** in the dashboard.
    Open the listing and copy its HTTPS Chrome Web Store detail URL.
18. Paste that URL into `chrome_web_store_url` in `extension/store-config.json`.
    It must end with the same item ID. Run:

    ```powershell
    python scripts/sync_store_links.py
    python scripts/sync_store_links.py --check
    ```

19. Ship the helper/bundled extension with that JSON and apply
    `website-copy-notes.md` to uoink.app. The splash, setup page, README and
    website copy now lead with **Add to Chrome**. Sideloading is the Advanced
    fallback. With an empty URL, the existing sideload flow remains.
20. Share the store link. If you also update the store package to include the
    link, do that in a normal versioned release. It is not needed for installed
    store users to capture with the correctly configured helper.

## If Google rejects it

Read the rejection code and cited policy in the dashboard/email. Reproduce the
reported issue, fix the specific code or disclosure, rerun verification, and
update the same item. Increase the version for a changed package; metadata-only
corrections do not require a new zip. Keep the item ID and its helper configuration.
Do not create another item to avoid the decision.

If the finding is mistaken, Ryan can use the dashboard's appeal action with a
short explanation, the relevant source paths and reproducible test steps.
Google permits one appeal per violation decision. For likely issues and concrete
mitigations, use [POLICY-AUDIT.md](POLICY-AUDIT.md). No one was contacted in this pass.

## Edge Add-ons

The current key-free zip is a candidate for Edge too. Microsoft generally
supports [porting Chromium extensions](https://learn.microsoft.com/en-us/microsoft-edge/extensions/developer-guide/port-chrome-extension)
with few changes, and [registration is free](https://learn.microsoft.com/en-us/microsoft-edge/extensions/publish/create-dev-account).
Use Partner Center, its own listing fields and Microsoft review. There is no
`update_url` in this package to remove.

An Edge listing gets a different ID. Add that exact ID through the helper's
`extension_ids` setting or `UOINK_EXTENSION_IDS`; never replace the Chrome or
developer ID. Test offscreen clipboard, notifications, shortcuts and capture
in a disposable Edge profile before submission. A future Edge-specific link
must not replace the Chrome URL with an Edge URL: the current validator and
"Add to Chrome" text are deliberately Chrome-specific. The present empty-link
zip avoids that mismatch. No Edge account or submission was created.
