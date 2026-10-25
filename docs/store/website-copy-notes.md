# uoink.app install copy for 3.11

This is a website handoff, not a deployment. The source of truth is
`extension/store-config.json`. After changing its URL, run
`python scripts/sync_store_links.py`. It updates this block and the README.
The helper splash and extension setup read the same bundled JSON directly.

<!-- store-install:start -->
Keep the current download and sideload instructions until the store link is live.

Install the Windows helper, then load its bundled extension. On first launch, Uoink shows a one-time setup splash. Use it to open your browser's extensions page and copy the installed extension path; then enable Developer mode, click **Load unpacked**, and select that folder.
<!-- store-install:end -->

Apply that copy to the homepage extension button, `/install`, and any
"Load unpacked" onboarding instructions. Keep the Windows helper requirement
beside the install button. A store install removes the Developer mode step;
it does not replace the helper. Show sideloading in an Advanced disclosure
once the store link is live. Remove any `uoink.video` link in these surfaces.

Before submission, verify `/privacy` includes the opt-in usage counts and
this affirmative statement: "Uoink's use and transfer of user data complies
with the Chrome Web Store User Data Policy, including its Limited Use
requirements." The local repository privacy draft is not the published policy.
