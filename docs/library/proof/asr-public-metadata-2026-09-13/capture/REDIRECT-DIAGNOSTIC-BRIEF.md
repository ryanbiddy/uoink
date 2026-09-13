# Redirect diagnostic after partial metadata capture

The original run01 failed overall: 10 of 11 public metadata requests succeeded and five pinned plans were captured. The large-v3-turbo repository returned a redirect, which the collector correctly refused. The first instrument omitted its status and Location header, so the alias destination is still unknown. Preserve that result and collector unchanged.

Run one fresh diagnostic GET against the same public metadata URL. Continue refusing all redirects. Record only the status, Location and Content-Type headers, final observed URL and any bounded response body (4 KiB); do not follow the destination. No model, configuration or audio asset request is permitted. This repairs the missing diagnostic information; it does not repeat the successful ten requests or grant a new repository/source decision. Keep the resulting status separate from plan acceptance.
