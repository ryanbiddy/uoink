# Phone inbox: the Uoink Relay

Share a link from your phone, and Uoink on your computer captures it the next
time it checks. There is no phone app and no Uoink cloud. The link travels
through a small relay that you deploy to your own Render account.

**What it is.** A tiny web service with two endpoints. Your phone adds a link
to it with one token. Uoink lists pending links with a second token, captures
each one locally exactly like `uoink capture <url>`, then deletes it from the
relay.

**What it isn't.** It is not a sync service, a library or a backup. The relay
never sees your captures, transcripts or notes in Uoink. It holds a link and
an optional note, and nothing else, until Uoink picks it up. Anything Uoink
hasn't picked up after 7 days is deleted.

## 1. Deploy the relay

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/ryanbiddy/uoink)

The button reads [`render.yaml`](../render.yaml) and creates two things on your
Render account:

- `uoink-relay`, a free Python web service (the code is in [`relay/`](../relay/app.py));
- `uoink-relay-kv`, a free Key Value instance that only `uoink-relay` can reach.

Render generates both tokens for you. When it finishes, note the relay's
address, for example `https://uoink-relay-abcd.onrender.com`. Open it in a
browser: you should see a short "Uoink Relay" page.

Updates to the Uoink repository don't redeploy your relay. To take a newer
relay version, choose **Manual Deploy** on the service in Render.

## 2. Find the two tokens

In the Render dashboard, open **uoink-relay > Environment**.

- `RELAY_PUSH_TOKEN` goes on your phone. It can only add links.
- `RELAY_PULL_TOKEN` goes in Uoink. It can only list and delete links.

Each token is at least 32 characters, and the two must differ, or the relay
refuses to start.

## 3. Set up your phone

### iPhone and iPad: a Shortcut

In the Shortcuts app, create a shortcut with these actions:

1. In the shortcut's details, turn on **Show in Share Sheet**. Set it to
   receive **URLs** and **Text**.
2. **Get Contents of URL**: `https://<your-relay>.onrender.com/v1/links`
   - Method: **POST**
   - Headers: `Authorization` = `Bearer <your push token>`
   - Request Body: **JSON**, with one field: `url` (Text) = **Shortcut Input**
3. **Show Notification**: "Sent to Uoink".

Share a page from Safari, YouTube or X and pick the shortcut. If the share
sends text such as `A good video https://youtu.be/...`, the relay uses the
first `http` or `https` link and keeps the rest as the note. To add your own
note, add a `note` field to the JSON body (for example from an **Ask for
Input** action).

### Android: HTTP Shortcuts

Install the free **HTTP Shortcuts** app and create a shortcut:

- Method **POST**, URL `https://<your-relay>.onrender.com/v1/links`
- Header `Authorization` = `Bearer <your push token>`
- Body type **Form data** (`application/x-www-form-urlencoded`) with
  `text` = the shared text variable, or **JSON** with `url` = that variable
- Under trigger settings, allow it to appear as a **share target**.

The relay also reads `url`, `text` and `title` form fields, and a plain-text
body.

### Any device: curl

```sh
curl -X POST https://<your-relay>.onrender.com/v1/links \
  -H "Authorization: Bearer <your push token>" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://www.youtube.com/watch?v=jNQXAC9IVRw","note":"Watch the opening"}'
```

A new link answers `201` with its `id` and `expires_at`. Sharing a link that
is still waiting answers `200` with the same `id`.

## 4. Set up Uoink

Open **Dashboard > Settings > Capture > Phone inbox**:

1. **Relay address**: the `https://...onrender.com` address.
2. **Pull token**: paste `RELAY_PULL_TOKEN`. Uoink stores it in your system's
   credential store, never in `settings.json`, and the field shows **Saved**
   afterwards.
3. Turn on **Pick up links shared from my phone**, pick how often to check,
   and select **Save**.

**Check now** checks at once. The status line shows when Uoink last checked
and how many links it picked up, or what went wrong.

Each link is captured with the same tool `uoink capture` uses: YouTube videos
and playlists, X posts, Reddit threads, podcast feeds and web pages. A link
Uoink can't capture is removed from the relay. Once a capture finishes, the
link is removed whether it worked or not; a failed capture shows in Activity
like any other. A web page on a site that isn't in **Sites Uoink works on** is
refused, so add the site there first. If the share had a note and the capture
worked, Uoink also saves a note titled "From my phone" with the note and the
link.

## Free plan notes

The free plan works for a personal inbox, with two tradeoffs:

- **The relay sleeps.** A free web service stops after 15 minutes with no
  requests and takes about a minute to wake. The first share after a quiet
  spell is slow, and Uoink waits up to 90 seconds when it checks.
- **Restarts drop waiting links.** Free Key Value keeps data in memory only.
  If Render restarts it, links Uoink hasn't picked up yet are lost. Render
  allows one free Key Value instance per workspace.

Free web services also share a monthly allowance of instance hours per
workspace. A paid Key Value plan keeps waiting links across restarts, and a
paid web service never sleeps. Pick them if you share links often and want
none to wait or go missing. Change the plan on each service in Render.

## Rotating the tokens

1. In Render, open **uoink-relay > Environment**, edit `RELAY_PUSH_TOKEN` or
   `RELAY_PULL_TOKEN` (at least 32 random characters, no spaces) and save
   the change so Render redeploys the relay with it.
2. Put the new push token in your Shortcut or HTTP Shortcuts request.
3. Paste the new pull token in **Settings > Phone inbox** and select **Save**.

To stop using the relay, turn off **Pick up links shared from my phone** in
Uoink, then suspend or delete both services in Render.

## What's stored, and for how long

| Where | What | How long |
|---|---|---|
| Relay (your Key Value) | The link, the optional note, a random id and the time it was shared | Until Uoink picks it up, or 7 days |
| The relay's own log lines | Method, route, status code and duration only. Never tokens, links, notes or IP addresses | Render's log retention |
| Uoink settings | Relay address, on/off, check interval | Until you change them |
| System credential store | The pull token | Until you replace it |

Render hosts the relay, so its platform handles each request under Render's own policy.
The relay has no page that shows your links. `GET /healthz` answers whether
the store is reachable, with no counts. Every response is marked
`Cache-Control: no-store`.

Abuse limits: after 30 requests with a missing or wrong token from one address
in 10 minutes, further wrong-token requests from that address get `429` until
the window passes. A valid token is never refused, so nobody can lock your
phone out. The address is the one Render's proxy records. The relay accepts 60
new links a minute, links of up to 2048 characters, notes of up to 500
characters and requests of up to 16 KiB. It holds at most 500 waiting links
and answers `429 inbox full` past that.

## Troubleshooting

- **The Shortcut says 401.** The push token is wrong or has a typo. The
  header must be `Bearer ` followed by the token.
- **403.** The push and pull tokens are swapped. The phone uses
  `RELAY_PUSH_TOKEN`; Uoink uses `RELAY_PULL_TOKEN`.
- **The Shortcut times out.** The relay was asleep. Try again; the next share
  is fast.
- **Uoink says it "didn't answer within 90 seconds".** Same cause. Uoink tries
  again at the next check.
- **Uoink says "There's no relay at this address".** Copy the address from
  the service's page in Render, starting with `https://`.
- **A link never shows up.** If the relay restarted on the free plan before
  Uoink checked, the link was lost. Share it again.
- **The relay won't start.** Its log names the setting to fix: a missing or
  short token, identical tokens, or no `RELAY_KEYVALUE_URL`.
- **429 inbox full.** 500 links are waiting. Check that Uoink is running with
  the phone inbox turned on.

To run a relay on your own computer for testing, start it with
`RELAY_DEV_MEMORY=1`, two tokens and `PORT`, then use
`http://127.0.0.1:<port>` as the relay address. Uoink accepts `http://` only
for `127.0.0.1` and `localhost`.
