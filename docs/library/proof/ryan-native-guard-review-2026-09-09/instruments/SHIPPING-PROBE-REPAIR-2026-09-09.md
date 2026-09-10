# Independent shipping-decoder probe correction

astra-shipping-media-c1 records three passes / one failure in 3.03 seconds.
The newly written scratch probe called only _screenshot_interval_for, which
handles short-clip density, and omitted the later screenshot-cap loop in
server._run_extraction at lines 5026-5035. FFmpeg correctly produced 240 frames
at its requested 30-second interval. This does not demonstrate a production
cap failure: the production caller raises that interval before invoking FFmpeg.

Preserve the original probe in the failed run. Add the same bounded estimate
loop to this new, uncommitted instrument: start at the requested interval and
increment while server._estimated_screenshot_count([7200], interval) exceeds
server.MAX_SCREENSHOTS. The assertion remains 0 < frames <= MAX_SCREENSHOTS.
No original product or acceptance-test file changes. Run the corrected new
probe with the three original screenshot tests as astra-shipping-media-c2.
Retain both observed outcomes and actual command receipts; do not relabel c1.
