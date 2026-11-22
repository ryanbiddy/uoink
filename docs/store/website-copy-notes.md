# uoink.app install copy for 3.11

This is a website handoff, not a deployment. The source of truth is
`extension/store-config.json`. After changing its URL, run
`python scripts/sync_store_links.py`. It updates this block and the README.
The helper splash and extension setup read the same bundled JSON directly.

<!-- store-install:start -->
Keep the current download and sideload instructions until the store link is live.

Install the Uoink helper app, then load its bundled extension. On the one-time setup splash, click **Open extensions page** to open your browser's extensions page. If you get a blank tab, enter the address shown on the splash. Click **Copy path** on the splash to copy the installed extension path. Turn on **Developer mode**, click **Load unpacked**, and select that folder. Pin **Uoink** from the browser's Extensions menu.
<!-- store-install:end -->

Apply that copy to the homepage extension button, `/install`, and any
"Load unpacked" onboarding instructions. Keep the Uoink helper app requirement
beside the install button. A store install removes the Developer mode step;
it does not replace the helper. Show sideloading in an Advanced disclosure
once the store link is live. Remove any `uoink.video` link in these surfaces.

Before submission, verify `/privacy` includes the opt-in usage counts and
this affirmative statement: "Uoink's use and transfer of user data complies
with the Chrome Web Store User Data Policy, including its Limited Use
requirements." The local repository privacy draft is not the published policy.
