# Phase 3 UI Consent and Failure Test Plan (2026-09-07)

**Document:** `docs/library/PHASE3-UI-TEST-PLAN-2026-09-07.md`  
**Author:** Gemini (UI & Verification Worker)  
**Run:** AL (Specification & Test Planning)  
**Target Implementation:** Run AM (Claude Worker & Gemini)  
**Scope:** Sources UI consent flows, failure cases, input validation, and Run AM automated test suite with fixtures.

---

## 1. Sources UI Architecture & Standing Subscriptions Wireframe

### 1.1 UI Placement & Integration Point
In `assets/dashboard/index.html`, the current Sources tab (`#tab-sources`) contains capture capability descriptions, manual capture dropzones (URL, note, image), and a collapsed roadmap. Under Phase 3, the Sources tab becomes the active management surface for standing subscriptions.

A new section, `#standingSubscriptions`, is inserted directly beneath the Sources page header and before the manual URL dropzone. It presents:
1. **Summary Bar:** Total subscribed sources, count with standing capture active (`consent = 'on'`), daily starts used across all sources today (UTC), and next scheduled scheduler tick.
2. **Source Subscription Cards (`.subscription-card`):** One card per registered source (RSS podcast feed or YouTube channel/playlist).
3. **Empty State:** Visual prompt when no standing sources are registered, guiding the user to paste an RSS feed or YouTube channel link into the capture input.

### 1.2 Subscription Card Layout
Each subscription card displays:
- **Header:**
  - Source title (or sanitized fallback to URL).
  - Source type badge: `podcast` or `youtube`.
  - Health indicator pill: `healthy` (green), `polling` (blue pulse), `degraded` (amber), or `error` (vermillion).
  - Last polled timestamp (relative and ISO hover) and next due poll interval.
- **Consent Control Group:**
  - Toggle button: Explicitly switches between `Off` and `On`.
  - State pill:
    - `Off (Metadata only)`: Ingest is disabled; detection cursor tracks new items without downloading media.
    - `On (Standing capture)`: Automatic ingest is active up to policy limits.
    - `Draining`: User toggled off while a download or transcription was active; in-flight work finishes cleanly.
- **Back-Catalog Enrollment Indicator:**
  - Displays back-catalog status and the 25-item ceiling:
    - When `Off`: "Back catalog: 0 / 25 enrolled (idle)".
    - When `On`: "Back catalog: 25 items enrolled (oldest: 2026-08-14). 42 older items excluded by cap."
- **Daily Ingest Allowance Meter:**
  - Visual progress bar and fraction: e.g., `3 / 10 starts used today (UTC)`.
  - Reset counter: `Resets at 00:00 UTC (in 3h 44m)`.
  - When exhausted (10/10): Amber border and note: `Daily allowance reached. Polling pauses starts until next UTC day.`
- **In-Flight Activity Box:**
  - Hidden when idle.
  - Visible when a start reservation is claimed: Episode/video title, current phase (`downloading`, `transcribing`, `enqueuing_classification`), and progress indicator.
  - Direct deep-link to `#tab-activity` for low-level job logs.
- **Error Callout:**
  - Rendered conditionally if `error_count > 0`. Shows HTTP status code or failure reason, consecutive failure count, and next backoff retry time. Includes a "Retry poll now" button.

---

## 2. Real Consent Flows in the Sources UI

### Flow 2.1: Default Off (Discovery and Registration)
1. **Trigger:** A user pastes an RSS feed URL or YouTube channel URL into the universal capture input, or registers a feed via the `add_source` tool.
2. **Initial State:**
   - Database record created in `source_subscriptions` with `consent_state = 'off'`.
   - Detection cursor is initialized to the feed head (or empty).
3. **UI Rendering:**
   - Card displays with toggle switch set to `Off`.
   - Consent status pill reads: `Metadata only`.
   - Info text states: *"Standing capture is off. Uoink will watch for new episodes and catalog metadata, but will not download audio or spend compute."*
   - Daily allowance meter reads: `0 / 10 starts used today (UTC)`.
4. **Behavior Verification:**
   - Polling checks fetch feed XML and insert `discovered` episode rows.
   - Zero start ledger reservations are created.
   - Zero media files are downloaded.
   - Phase 2 classification work queue receives zero items from this source.

### Flow 2.2: Explicit Opt-In (Off -> On)
1. **Trigger:** User clicks the toggle button `Turn On Standing Capture`.
2. **Confirmation & Modal/Popover:**
   - The UI displays an explicit enrollment confirmation dialog:
     - Heading: *"Enable standing capture for [Source Name]?"*
     - Details:
       - *"Back-catalog policy: up to 25 most recent items will be enrolled."*
       - *"Daily allowance: up to 10 starts per UTC day."*
       - *"Audio download and local transcription will begin on the next scheduler cycle."*
     - Actions: `[Cancel]` and `[Confirm & Enable]`.
3. **Submission:**
   - On confirmation, UI issues an authenticated POST to `/api/sources/subscriptions/consent` (or MCP tool `set_source_consent`) with payload:
     ```json
     {
       "source_id": 14,
       "consent": "on"
     }
     ```
4. **State Transition & Back-Catalog Enrollment:**
   - Server updates `source_subscriptions.consent_state = 'on'` and sets `consent_updated_at`.
   - Server executes back-catalog enrollment query: selects up to 25 items for `source_id` ordered by `published_at DESC`, setting their status to `enrolled`.
   - Items beyond the 25-item cutoff remain `discovered_only` and are flagged `back_catalog_excluded = 1`.
5. **UI Update:**
   - Toggle switches to active state (`On`).
   - Pill updates to: `Standing capture: Active`.
   - Toast message appears: *"Standing capture enabled. 25 back-catalog items enrolled."*
   - Back-catalog meter displays: `25 items enrolled (cap reached)`.
   - First candidate item begins preparation on the next scheduler tick.

### Flow 2.3: Active Standing Ingest & Allowance Depletion
1. **Scheduler Tick:**
   - When a scheduler tick runs, it queries due sources with `consent_state = 'on'`.
   - Checks the atomic start ledger for the source for the current UTC day:
     ```sql
     SELECT COUNT(*) FROM source_start_ledger
     WHERE source_id = :source_id AND utc_day = :utc_day AND status != 'cancelled';
     ```
2. **Allowance Metering:**
   - If count < 10, the scheduler reserves one start:
     ```sql
     INSERT INTO source_start_ledger (source_id, item_id, utc_day, status, created_at)
     VALUES (:source_id, :item_id, :utc_day, 'reserved', :now);
     ```
3. **UI Display During Capture:**
   - The card's daily allowance meter increments: `1 / 10 starts used today (UTC)`.
   - The in-flight box opens: `Downloading audio: Episode 108 — The Architecture of Memory`.
   - Activity pill animates with a blue pulse.
4. **Post-Ingest Hand-off:**
   - Upon audio download and Whisper transcription completion, the item is committed to the local corpus/index.
   - Only after commit succeeds, a Phase 2 classification work row is enqueued.
   - Item status moves from `in_flight` to `completed`.
   - Start ledger row moves to `status = 'completed'`.

### Flow 2.4: Explicit Opt-Out (On -> Off) with Draining In-Flight State
1. **Trigger:** User clicks the toggle button `Turn Off Standing Capture`.
2. **Submission:**
   - UI issues authenticated POST to `/api/sources/subscriptions/consent`:
     ```json
     {
       "source_id": 14,
       "consent": "off"
     }
     ```
3. **Server State Transition:**
   - `source_subscriptions.consent_state` updates to `'off'`.
   - Any enrolled items that have not yet started (`status = 'enrolled'`) are disarmed back to `status = 'discovered'`.
   - Any currently active start ledger reservation (`status IN ('reserved', 'in_flight')`) is **not** aborted or corrupted. The media process is allowed to cleanly drain to completion or fail.
4. **UI Rendering:**
   - Toggle immediately moves to `Off`.
   - A warning/draining badge appears: `Draining in-flight work`.
   - Info banner displays:
     *"Standing capture turned off. No new downloads will start. 1 active download in progress will finish cleanly."*
   - The in-flight progress box remains visible until the active process exits.
   - When the active process finishes, the card transitions to pure `Off (Metadata only)` state.
   - The start ledger retains the completed start for that UTC day; turning the feed off and on cannot reset the 10-start allowance.

---

## 3. Failure Cases and Edge State Specifications

### 3.1 Failure Case 1: Feed Unreachable / Network Failure
- **Root Causes:** Upstream host returns HTTP 404/500/503, connection times out (connect/read > 15s), TLS certificate failure, or DNS resolution fails.
- **System Behavior:**
  - `source_subscriptions.error_count` increments by 1.
  - `last_error` records the sanitized error string (truncated to 512 characters).
  - Next poll time applies exponential backoff: 5m, 15m, 30m, 1h, 2h, up to a maximum of 6h.
  - Scheduler heartbeat records the poll failure.
- **UI Presentation:**
  - Status indicator changes from green to vermillion: `Feed unreachable`.
  - Alert strip on the card: *"Fetch failed at 20:14 UTC: HTTP 503 Service Unavailable. Next retry in 15 minutes."*
  - An inline button `[Retry Now]` allows the user to force an immediate manual check without waiting for the backoff timer.
  - Existing discovered items remain completely intact and navigable in the Library.

### 3.2 Failure Case 2: Media Download / Extraction Failure
- **Root Causes:** Enclosure URL returns 404, yt-dlp receives HTTP 429 (rate-limit / bot block), partial audio file downloaded due to network drop, or disk is full (`ENOSPC`).
- **Accounting & Ledger Rules:**
  - The start ledger row was inserted as `status = 'reserved'`.
  - If failure is transient (e.g., network timeout, HTTP 503, or rate limit):
    - Up to 2 retries are permitted within the same UTC day.
    - Retries **reuse the existing start ledger reservation ID**. They do not consume additional daily allowance slots.
  - If failure is permanent (e.g., HTTP 404, corrupt codec, or retries exhausted):
    - The start ledger row transitions to `status = 'failed_terminal'`.
    - **Accounting Decision:** A permanently failed download still counts toward the 10-start daily cap. This protects the local system from entering a tight crash loop against an unextractable media stream.
- **UI Presentation:**
  - Item in the card's activity list displays an error chip: `Download failed (Attempt 2/3): Network timeout`.
  - Daily allowance meter displays breakdown: `4 starts used (3 completed, 1 failed) — 6 remaining`.
  - When disk is full, the card presents a banner: `Disk space exhausted. Standing capture paused until storage is cleared.`

### 3.3 Failure Case 3: Daily Ingest Allowance Exhausted (10/10 Starts Used)
- **Root Causes:** Source has 10 successful or permanently failed starts within the current UTC calendar day (00:00:00 to 23:59:59 UTC).
- **System Behavior:**
  - Scheduler tick skips candidate item selection for this source.
  - Network polling for metadata continues on schedule; new items are cataloged with `status = 'discovered'`.
  - No new reservations are added to `source_start_ledger`.
- **UI Presentation:**
  - Allowance meter fills to 100% with amber styling: `10 / 10 starts used today (UTC)`.
  - Notice badge: `Daily allowance cap reached`.
  - Subtext: *"Capture paused until 00:00 UTC (resumes in 4 hours 18 minutes). Metadata continues to update."*
  - Candidate queue shows remaining enrolled items marked: `Pending next UTC allowance window`.

### 3.4 Failure Case 4: Helper Restart Mid-Reservation
- **Root Causes:** The Uoink helper process is terminated (SIGTERM, system reboot, application crash) while an item is actively downloading or transcribing (`source_start_ledger.status IN ('reserved', 'in_flight')`).
- **System Recovery Behavior:**
  - On helper startup, a recovery procedure scans `source_start_ledger` for unresolved reservations.
  - If a reservation has `status = 'reserved'` or `'in_flight'` and its `last_heartbeat` is older than 10 minutes:
    - Any orphaned temporary download files (`.part`, `.tmp`) in the cache are cleaned up.
    - If the reservation's `utc_day` matches the current UTC day:
      - If retry count < 3, the reservation is reset to `status = 'reserved'` and re-queued.
      - If retry count >= 3, it transitions to `status = 'failed_terminal'`.
    - If the reservation belonged to a previous UTC day:
      - The reservation is closed as `status = 'abandoned_on_restart'` to prevent historical spillover from consuming the new day's allowance.
- **UI Presentation:**
  - On dashboard reload following restart, the UI renders the recovered state without hanging.
  - The card displays an informational banner: *"Recovered active capture following restart. Resuming: Episode 104."*
  - Daily allowance meters accurately reflect ledger rows without orphan leakage or double-counting.

---

## 4. Input Validation & Adversarial Rejection Matrix

All inputs through registry tools (`list_sources`, `set_source_consent`, `source_status`) and dashboard endpoints (`/api/sources/*`) must enforce strict server-side validation.

| Input Vector | Attack / Malformed Pattern | Target Surface | Expected Handling / Error Code |
|---|---|---|---|
| **JSON Schema** | Missing required `source_id` or `consent` | `set_source_consent` | HTTP 400 / Tool error: `Missing required field: source_id` |
| **JSON Schema** | Unknown additional properties: `{"source_id": 1, "consent": "on", "bypass_cap": true}` | All tools / endpoints | HTTP 400 / Tool error: `additionalProperties not permitted` |
| **Type Confusion** | String for integer ID: `{"source_id": "14"}` | `source_id` | HTTP 400 / Tool error: `Expected integer for source_id` |
| **Type Confusion** | Boolean for integer ID: `{"source_id": true}` | `source_id` | HTTP 400: Strict integer check (prevent SQLite boolean coercion) |
| **Type Confusion** | Float / NaN / Infinity: `{"source_id": 14.5}`, `NaN` | `source_id` | HTTP 400: Rejects non-finite or fractional numeric values |
| **Type Confusion** | Non-enum consent value: `{"consent": "yes"}`, `{"consent": 1}`, `{"consent": "ACTIVE"}` | `consent` | HTTP 400: Enum check; only exact literals `"on"` and `"off"` allowed |
| **Boundary Violation**| Negative or zero source ID: `{"source_id": -1}`, `{"source_id": 0}` | `source_id` | HTTP 400: Value must be positive integer `>= 1` |
| **SSRF** | Loopback / internal IPs: `http://127.0.0.1:5179/feed`, `http://localhost:8080/rss` | Feed URL registration | HTTP 400: `Invalid feed URL: Loopback and local addresses prohibited` |
| **SSRF** | Cloud metadata endpoint: `http://169.254.169.254/latest/meta-data/` | Feed URL registration | HTTP 400: `Link-local and metadata addresses prohibited` |
| **SSRF** | Private LAN addresses: `http://192.168.1.1/feed.xml`, `http://10.0.0.5/rss` | Feed URL registration | HTTP 400: `Private subnet addresses prohibited` |
| **Scheme Abuse** | Non-HTTP schemes: `file:///etc/passwd`, `javascript:alert(1)`, `gopher://` | Feed URL registration | HTTP 400: Only `http://` and `https://` schemes allowed |
| **Oversized String** | URL longer than 2,048 characters | Feed URL registration | HTTP 400: `URL exceeds maximum length of 2048 characters` |
| **Path Traversal** | Directory traversal in feed ID or channel name: `../../etc/shadow` | Source identification | HTTP 400: Strict alphanumeric/integer validation, no path separators |
| **XML Parser (XXE)** | DTD entity expansion / Billion Laughs XML payload in RSS feed | Feed Poller | XML parser configured with `resolve_entities=False`, DTD disabled |
| **XML Decompression**| Gzip bomb expanding to gigabytes | Feed Poller | HTTP stream capped at 10 MB maximum response body size |
| **Stored XSS** | `<script>alert('xss')</script>` in `<channel><title>` or `<item><title>` | Dashboard UI | UI uses `htmlEscape()` or `textContent`; script tags neutralized |
| **Markdown / Link Injection**| `[Click Me](javascript:steal())` in podcast description | Dashboard UI | Markdown sanitizer blocks `javascript:` and non-standard protocols |
| **DOM Clobbering** | GUID or episode title equaling `sourceMap`, `universalCaptureButton` | Dashboard UI | Attribute and ID naming scopes isolated; no bare DOM lookups |
| **Race Condition** | Rapid concurrent toggle requests (flipping `on` / `off` in parallel) | Consent Endpoint | SQLite `BEGIN IMMEDIATE` transaction; serializes state changes |

---

## 5. Run AM Implementation Test Plan

The tests below will be implemented during Run AM. They test the UI markup, dashboard client logic, and tool/API endpoints.

### 5.1 Test Suite 1: UI Consent & Display Verification
**File:** `tests/test_phase3_ui_consent.py`  
**Purpose:** Verify DOM structure, data bindings, consent state transitions, and allowance representations in `assets/dashboard/index.html`.

- `test_sources_ui_contains_standing_subscription_panel()`
  - Verifies presence of `#standingSubscriptions`, summary counters, and subscription list containers in `assets/dashboard/index.html`.
- `test_subscription_card_renders_default_off_state()`
  - Mounts dashboard template with a newly registered feed (`consent_state = 'off'`).
  - Asserts toggle button is in `off` position, status badge is `Metadata only`, and audio download notice is present.
- `test_explicit_opt_in_renders_confirmation_modal()`
  - Simulates click on `Turn On Standing Capture`.
  - Asserts modal appears detailing the 25-item back-catalog cap and 10-start daily allowance.
- `test_back_catalog_meter_shows_25_item_cap_boundary()`
  - Provides a mock feed with 60 available episodes.
  - Asserts UI renders `25 items enrolled` and explicitly notes that 35 older items are excluded.
- `test_daily_allowance_meter_reflects_utc_day_budget()`
  - Feeds state with 4 consumed starts today.
  - Asserts meter displays `4 / 10 starts used today (UTC)` and includes UTC countdown reset string.
- `test_opt_out_renders_draining_in_flight_state()`
  - Provides state with `consent_state = 'off'` but one item in `source_start_ledger` with `status = 'in_flight'`.
  - Asserts card renders `Draining in-flight work` badge, displays the active episode name, and disallows new starts.
- `test_idempotent_toggle_does_not_duplicate_enrollment()`
  - Sends multiple consecutive `consent = 'on'` signals.
  - Asserts no secondary back-catalog enrollment occurs and allowance count is unchanged.

### 5.2 Test Suite 2: Failure Case Handling & Recovery
**File:** `tests/test_phase3_ui_failures.py`  
**Purpose:** Verify UI error rendering, scheduler resilience, backoff timers, and restart recovery.

- `test_unreachable_feed_renders_degraded_pill_and_backoff_notice()`
  - Injects feed failure: `error_count = 3`, `last_error = 'HTTP 503: Service Unavailable'`.
  - Asserts card status pill turns vermillion (`Feed unreachable`), error message is visible, and retry button exists.
- `test_download_failure_preserves_retry_budget_without_double_counting()`
  - Simulates transient download error on item attempt 1.
  - Asserts reservation ID is preserved, attempt counter increments to 2/3, and daily allowance meter does not double-count.
- `test_daily_cap_exhaustion_locks_queue_and_shows_countdown()`
  - Injects start ledger state with 10 completed rows for current UTC date.
  - Asserts card displays `10 / 10 starts used today (UTC)` in amber, disallows immediate starts, and shows time until 00:00 UTC.
- `test_scheduler_restart_mid_reservation_reconciles_cleanly()`
  - Creates SQLite database with uncompleted reservation row (`status = 'in_flight'`).
  - Invokes helper startup recovery routine.
  - Asserts stale reservation is re-queued or terminated cleanly, and dashboard does not show stuck or orphaned state.
- `test_concurrent_schedulers_atomic_reservation_race()`
  - Spawns two simulated scheduler workers attempting to claim the 10th allowance slot simultaneously.
  - Asserts SQLite `BEGIN IMMEDIATE` locks ensure exactly one scheduler succeeds and the 10-start daily cap is never exceeded.

### 5.3 Test Suite 3: Malformed & Adversarial Rejections
**File:** `tests/test_phase3_adversarial_inputs.py`  
**Purpose:** Verify that registry tools and API routes reject invalid types, malformed URLs, SSRF attempts, and XSS vectors.

- `test_registry_tool_rejects_non_object_payload()`
  - Passes raw strings, arrays, and numbers to `set_source_consent`. Asserts error response with schema validation failure.
- `test_registry_tool_rejects_additional_properties()`
  - Passes `{"source_id": 1, "consent": "on", "extra_param": "malicious"}`. Asserts rejection.
- `test_registry_tool_rejects_type_confused_parameters()`
  - Tests string IDs (`"1"`), boolean IDs (`true`), floats (`1.5`), and invalid consent strings (`"TRUE"`, `"enabled"`). Asserts HTTP 400.
- `test_ssrf_protection_blocks_internal_and_metadata_addresses()`
  - Tests registration with `http://127.0.0.1:5179`, `http://169.254.169.254`, and `http://10.0.0.1`.
  - Asserts immediate rejection without initiating network connections.
- `test_feed_parser_neutralizes_xxe_and_billion_laughs()`
  - Feeds parser an XML payload containing recursive entity expansions.
  - Asserts parser raises safe XML parsing error without entity expansion or memory exhaustion.
- `test_ui_escapes_xss_in_feed_metadata()`
  - Injects `<script>window.pwned=true</script>` into channel title, episode title, and author fields.
  - Evaluates rendered DOM using `mini_dom.mjs` or regex parser.
  - Asserts script tags are escaped as `&lt;script&gt;` and no executable code enters the DOM.
- `test_ui_resists_dom_clobbering()`
  - Injects episode titles containing reserved HTML IDs (`id="sourceMap"`).
  - Asserts dashboard elements remain unshadowed and script lookups succeed.

---

## 6. Fixtures Specification (`tests/fixtures/phase3/`)

The following test fixtures will be created in `tests/fixtures/phase3/` to support the Run AM test suite:

1. **`feed_standard_podcast.xml`**
   - RSS 2.0 feed containing 5 episodes with audio enclosures, GUIDs, and pubDates. Valid baseline for happy-path polling.
2. **`feed_large_back_catalog_100.xml`**
   - RSS 2.0 feed containing 100 well-formed episodes spanning two years. Used to test the 25-item back-catalog cap cutoff.
3. **`feed_xxe_billion_laughs.xml`**
   - RSS feed containing DTD definitions with recursive entity expansion. Used to verify XXE defenses in `podcasts.py`.
4. **`feed_xss_vectors.xml`**
   - RSS feed with XSS vectors in `<title>`, `<itunes:author>`, `<description>`, and `<guid>` tags.
5. **`feed_corrupt_syntax.xml`**
   - Truncated XML with unclosed tags and invalid byte sequences to test parser error recovery.
6. **`mock_db_phase3.py`**
   - Pytest fixture constructing an in-memory SQLite database initialized with migrations through `0028_source_subscriptions.sql`.
   - Pre-populates sample subscriptions, consent states, and start ledger rows.
7. **`mock_utc_clock.py`**
   - Time-freezing helper permitting programmatic progression of UTC time across the 23:59:59 -> 00:00:00 midnight boundary to test daily allowance reset.
