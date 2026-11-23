# Quiet desktop notifications

Desktop notifications are on by default. To keep background feed watches and
captures invisible, open **Dashboard → Settings → Local app** and turn off
**Show desktop notifications**. Uoink keeps suppressed updates in the
dashboard's **Activity** view, so silence does not discard the event. Uoink
also applies the same courtesy automatically while a foreground app covers its
monitor, including borderless and exclusive-fullscreen games.

The persisted setting is `notifications_enabled` in `settings.json`. Local
clients can read it through `GET /settings` or update it with an authenticated
`POST /settings` body such as `{"notifications_enabled": false}`. Restart is
not required.
