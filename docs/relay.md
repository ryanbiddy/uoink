# Phone inbox: the Uoink Relay

Share a link from your phone, and Uoink on your computer captures it the next
time it checks. There is no phone app and no Uoink cloud. The link travels
through a small relay that you deploy to your own Render account.

**The flow:** your phone, then your relay, then Uoink on your computer.
**What it costs:** a free Render account (you sign up once, and the relay runs
on Render's free plan). The relay holds links only, and deletes each one after
Uoink picks it up or after 7 days.

**What it is.** A tiny web service with a few endpoints. Your phone adds a link
to it with one token. Uoink lists pending links with a second token, captures
each one locally exactly like `uoink capture <url>`, then deletes it from the
relay.

**What it isn't.** It is not a sync service, a library or a backup. The relay
never sees your captures, transcripts or notes in Uoink. It holds a link and
an optional note, and nothing else, until Uoink picks it up. Anything Uoink
hasn't picked up after 7 days is deleted.

## The quick way: three steps in Uoink

Open **Dashboard > Settings > Capture > Phone inbox**. It walks you through
three numbered steps.

1. **Make your relay.** You need a Render account first. Signing up is free.
   Then select **Deploy to Render**:

   [![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/ryanbiddy/uoink)

   The button reads [`render.yaml`](../render.yaml) and creates two things on
   your Render account:

   - `uoink-relay`, a free Python web service (the code is in [`relay/`](../relay/app.py));
   - `uoink-relay-kv`, a free Key Value instance that only `uoink-relay` can reach.

   Render generates both tokens for you. When it finishes, copy the relay's
   address, for example `https://uoink-relay-abcd.onrender.com`, and open
   **uoink-relay > Environment** to copy `RELAY_PULL_TOKEN`.

2. **Connect it.** Paste the relay address and the pull token and select
   **Save**. Uoink checks the relay and shows **Connected**, or **Not
   connected** with the reason: a wrong address, a wrong token, or a relay
   that is still asleep. A free Render service sleeps when nobody uses it, so
   the first check can take up to a minute. Uoink stores the pull token in your
   system's credential store, never in `settings.json`.

3. **Set up your phone.** Once step 2 says Connected, Uoink shows a QR code.
   Scan it with the phone's camera. Uoink draws the code on your computer, and
   no outside QR service is used. The code opens
   `https://<your-relay>/phone#t=<push token>`, a page your own relay serves.
   The token sits after the `#`, so the browser never sends it to the relay
   and it never reaches a log. The page keeps it in the phone's local storage
   and removes it from the address bar.

When all three work, the card collapses to **Phone inbox is on**, with the last
pickup time and a **Show phone setup again** link. **Copy pairing link** in
step 3 gives you the same link as text, to paste into the page's **Pair with a
link** box when a camera is not handy.

### The phone page

`GET /phone` on your relay is a small page for the phone, with no outside
scripts, fonts or analytics and a strict Content Security Policy:

- **Paste a link** and **Send**, with a plain sent or failed result. If the
  relay was asleep, the page says it is waking and retries by itself for up to
  90 seconds.
- **Android:** install the page (Chrome menu, **Install app** or **Add to Home
  screen**). It then appears in the share sheet, because its manifest declares
  a share target. Share a link from any app and pick Uoink.
- **iPhone:** add the page to the Home Screen to paste links quickly. iPhone
  web pages cannot join the Share sheet, so the page also shows a short,
  one-time Shortcut recipe with **Copy address** and **Copy Authorization
  value** buttons.
- **Forget this phone** clears the stored token.

### Older relays: update to get the QR code

A relay deployed before Uoink 3.17 has no `/phone` page and no `/v1/pairing`
endpoint, so the dashboard cannot read its push token. Uoink notices the 404
and says **Update your relay: Render > uoink-relay > Manual Deploy**. Updates
to the Uoink repository never redeploy your relay by themselves, so choose
**Manual Deploy** on the service in Render, then check again. Until then you
can paste the push token (**Render > uoink-relay > Environment >
`RELAY_PUSH_TOKEN`**) into the dashboard, or use the manual setup below.

### Security note: the pull token now also reveals the push token

`GET /v1/pairing` requires the pull token and returns the push token. Both
tokens belong to you and sit side by side on your Render service, so this does
not widen access in a way that matters, but it is worth saying plainly:
anyone who holds the **pull** token can now also read the **push** token, and
so could add links to your relay. The push token still cannot read or delete
anything. The call goes through the same wrong-token limiter as every other
route, and the push token on it answers `403`. Keep the pull token private,
and rotate both (see below) if it leaks.

## Manual setup (fallback)

Use these if you would rather not use the QR code, or your phone cannot scan.

### 1. Find the two tokens

In the Render dashboard, open **uoink-relay > Environment**.

- `RELAY_PUSH_TOKEN` goes on your phone. It can only add links.
- `RELAY_PULL_TOKEN` goes in Uoink. It can list and delete links, and it can
  read the push token for pairing.

Each token is at least 32 characters, and the two must differ, or the relay
refuses to start.

### 2. Set up your phone by hand

#### iPhone and iPad: a Shortcut

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

#### Android: HTTP Shortcuts

Install the free **HTTP Shortcuts** app and create a shortcut:

- Method **POST**, URL `https://<your-relay>.onrender.com/v1/links`
- Header `Authorization` = `Bearer <your push token>`
- Body type **Form data** (`application/x-www-form-urlencoded`) with
  `text` = the shared text variable, or **JSON** with `url` = that variable
- Under trigger settings, allow it to appear as a **share target**.

The relay also reads `url`, `text` and `title` form fields, and a plain-text
body.

#### Any device: curl

```sh
curl -X POST https://<your-relay>.onrender.com/v1/links \
  -H "Authorization: Bearer <your push token>" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://www.youtube.com/watch?v=jNQXAC9IVRw","note":"Watch the opening"}'
```

A new link answers `201` with its `id` and `expires_at`. Sharing a link that
is still waiting answers `200` with the same `id`.

### 3. Set up Uoink by hand

In **Dashboard > Settings > Capture > Phone inbox**, step 2 holds these fields:

1. **Relay address**: the `https://...onrender.com` address.
2. **Pull token**: paste `RELAY_PULL_TOKEN`. The field shows **Saved**
   afterwards.
3. Turn on **Pick up links shared from my phone**, pick how often to check,
   and select **Save**.

**Check now** checks at once. The status line shows when Uoink last checked
and how many links it picked up, or what went wrong.

## What Uoink does with each link

Each link is captured with the same tool `uoink capture` uses: YouTube videos
and playlists, X posts, Reddit threads, podcast feeds and web pages. If the
share had a note and the capture worked, Uoink also saves a note titled "From
my phone" with the note and the link.

A link Uoink can't capture becomes a note, so nothing you share is lost. That
covers a kind of link Uoink doesn't support, a capture that fails, and a web
page on a site that isn't in **Sites Uoink works on**. The note is titled
"From my phone (not captured)" and holds your note, the link and why it
wasn't captured. For a blocked site, allow it in Settings, then Re-uoink. Uoink
removes the link from the relay only after the note is saved; if the note
can't be saved, the link waits for the next check.

## Free plan notes

The free plan works for a personal inbox, with two tradeoffs:

- **The relay sleeps.** A free web service stops after 15 minutes with no
  requests and takes about a minute to wake. The first share after a quiet
  spell is slow, and Uoink waits up to 90 seconds when it checks. The phone
  page says "Waking your relay" and retries by itself.
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
2. Paste the new pull token in **Settings > Phone inbox** and select **Save**.
3. Scan the new QR code with the phone, or put the new push token in your
   Shortcut or HTTP Shortcuts request. On the phone page, **Forget this
   phone** clears the old key first.

To stop using the relay, turn off **Pick up links shared from my phone** in
Uoink, then suspend or delete both services in Render.

## What's stored, and for how long

| Where | What | How long |
|---|---|---|
| Relay (your Key Value) | The link, the optional note, a random id and the time it was shared | Until Uoink picks it up, or 7 days |
| The relay's own log lines | Method, route, status code and duration only. Never tokens, links, notes or IP addresses | Render's log retention |
| Uoink settings | Relay address, on/off, check interval | Until you change them |
| System credential store | The pull token | Until you replace it |
| The phone (browser local storage) | The push token, after you scan the QR code | Until you select **Forget this phone** |

Render hosts the relay, so its platform handles each request under Render's own policy.
The relay has no page that shows your links. The `/phone` page is static and
holds no token or link, and the push token in the QR code follows a `#`, so it
is never sent to the server. `GET /healthz` answers whether the store is
reachable, with no counts. Every response is marked `Cache-Control: no-store`.

Abuse limits: after 30 requests with a missing or wrong token from one address
in 10 minutes, further wrong-token requests from that address get `429` until
the window passes. A valid token is never refused, so nobody can lock your
phone out. The address is the one Render's proxy records. The relay accepts 60
new links a minute, links of up to 2048 characters, notes of up to 500
characters and requests of up to 16 KiB. It holds at most 500 waiting links
and answers `429 inbox full` past that.

## Troubleshooting

- **Uoink says "Update your relay".** Your relay was deployed before the phone
  page existed. Render > uoink-relay > Manual Deploy, then check again.
- **The phone page says Not paired.** Scan the QR code in Uoink again, or paste
  the pairing link into **Pair with a link**. An iPhone Home Screen icon keeps
  its own storage, so pair again from inside the icon if it asks.
- **The Shortcut says 401.** The push token is wrong or has a typo. The
  header must be `Bearer ` followed by the token.
- **403.** The push and pull tokens are swapped. The phone uses
  `RELAY_PUSH_TOKEN`; Uoink uses `RELAY_PULL_TOKEN`.
- **The Shortcut times out.** The relay was asleep. Try again; the next share
  is fast. The phone page retries by itself.
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
