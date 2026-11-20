// Dashboard smoke: the main paths a person clicks before a release.
// Each test runs at 390px and 1280px, light and dark (see playwright.config.mjs).
import {
  test, expect, api, expectInfo, shot, layoutProblems, waitForLibrary, gotoDashboard,
  bodyLuminance, expectNoNewProblems,
} from "./lib/qa.mjs";

const scrollList = async (page, selector) => {
  await page.locator(selector).scrollIntoViewIfNeeded();
};

async function checkTheme(page, testInfo) {
  const lum = await bodyLuminance(page);
  if (testInfo.project.use.colorScheme === "dark") expect(lum, "dark mode background").toBeLessThan(0.35);
  else expect(lum, "light mode background").toBeGreaterThan(0.6);
}

async function checkLayout(page, testInfo, where) {
  expectNoNewProblems("layout", (await layoutProblems(page)).map((p) => `${where}: ${p}`), testInfo);
}

async function openSearch(page, query) {
  const box = page.locator("#searchInput");
  await box.fill(query);
}

test.describe("seeded library", { tag: "@seeded" }, () => {
  test("dashboard loads with no console errors", async ({ dash: { page } }, testInfo) => {
    const info = expectInfo();
    await gotoDashboard(page);
    await waitForLibrary(page);
    await expect(page.locator("#libraryCount")).toHaveText(String(info.total));
    await expect(page.locator("#libraryNavCount")).toHaveText(String(info.total));
    await checkTheme(page, testInfo);
    await checkLayout(page, testInfo, "library");
    await shot(page, testInfo, "01-library");
  });

  test("library lists every item and every kind", async ({ dash: { page } }, testInfo) => {
    const info = expectInfo();
    await gotoDashboard(page);
    await waitForLibrary(page);
    // First page, then Load more until every saved item is listed.
    const cards = page.locator("#libraryGrid .uoink-card");
    for (let i = 0; i < 5 && (await cards.count()) < info.total; i++) {
      const before = await cards.count();
      await page.locator("#loadMore").click();
      await expect.poll(() => cards.count()).toBeGreaterThan(before);
    }
    await expect(cards).toHaveCount(info.total);
    // Every card has a readable title (a long one keeps its full text in a tooltip).
    const titles = await page.locator("#libraryGrid .uoink-card .card-title").evaluateAll((els) =>
      els.map((el) => ({ text: el.textContent.trim(), title: el.getAttribute("title") || "", cut: el.scrollHeight > el.clientHeight + 2 || el.scrollWidth > el.clientWidth + 2 })));
    expect(titles.filter((t) => !t.text), "cards with no title").toEqual([]);
    expect(titles.filter((t) => t.cut && t.title.length < t.text.length).map((t) => t.text), "cut titles without a tooltip").toEqual([]);
    // Kind chips: the counts match what was saved.
    for (const [kind, count] of Object.entries(info.kinds_shown)) {
      await page.locator(`[data-library-kind="${kind}"]`).click();
      await expect(page.locator(`[data-library-kind="${kind}"]`)).toHaveAttribute("aria-pressed", "true");
      await expect(page.locator("#resultSummary")).toContainText(`of ${count}`);
    }
    await page.locator('[data-library-kind=""]').click();
    await expect(page.locator("#resultSummary")).toContainText(`of ${info.total}`);
    await checkLayout(page, testInfo, "library list");
    await scrollList(page, "#libraryGrid");
    await shot(page, testInfo, "02-library-list");
  });

  test("shelf counts in the sidebar add up to the library", async ({ dash: { page } }, testInfo) => {
    const info = expectInfo();
    await gotoDashboard(page);
    await waitForLibrary(page);
    const facets = await api("/library/facets");
    expect(facets.status).toBe(200);
    const topics = (facets.data.facets.topic || []).map((t) => [t.value, Number(t.count)]);
    expect(topics.length, "the library has shelves").toBeGreaterThan(1);
    const shelved = topics.reduce((sum, [, n]) => sum + n, 0);
    const problems = [];
    if (shelved !== info.total) problems.push(`shelf counts add up to ${shelved}, library has ${info.total} (${JSON.stringify(topics)})`);
    expectNoNewProblems("shelf-counts", problems, testInfo);
    const overview = page.locator("#topicOverview");
    if (await overview.isVisible()) {
      for (const [name] of topics.slice(0, 3)) await expect(overview).toContainText(name);
    }
    await shot(page, testInfo, "03-shelves");
  });

  test("search finds a phrase and shows the matching timestamp", async ({ dash: { page } }, testInfo) => {
    const info = expectInfo();
    await gotoDashboard(page);
    await waitForLibrary(page);
    await openSearch(page, info.search_phrase);
    const card = page.locator(`#libraryGrid .uoink-card[data-card-id="${info.search_item_id}"]`);
    await expect(card).toBeVisible();
    await expect(card.locator(".card-match q mark").first()).toBeVisible();
    const quote = (await card.locator(".card-match q").textContent()).toLowerCase();
    expect(quote).toContain(info.search_phrase);
    const link = card.locator(".card-match a.reader-time");
    const label = await link.getAttribute("aria-label");
    expect(label).toMatch(new RegExp(`^Open ${info.search_item_title} at \\d+:\\d\\d$`));
    const [m, s] = (await link.textContent()).trim().split(":").map(Number);
    const seconds = m * 60 + s;
    // The match is a passage: its time is at or a little before the spoken phrase.
    expect(seconds).toBeLessThanOrEqual(info.search_seconds);
    expect(seconds).toBeGreaterThanOrEqual(info.search_seconds - 60);
    await checkLayout(page, testInfo, "search");
    await shot(page, testInfo, "04-search");
    await link.click();
    await expect(page).toHaveURL(new RegExp(`#item/${info.search_item_id}\\?t=${seconds}`));
    await expect(page.locator("#yoinkHeading")).toHaveText(info.search_item_title);
    const para = page.locator(`.reader-para[data-reader-seconds="${seconds}"]`);
    await expect(para).toBeVisible();
    await expect(para).toContainText(info.search_phrase);
    await expect(para).toBeFocused();
    await shot(page, testInfo, "05-search-moment");
  });

  test("open an item and read its transcript", async ({ dash: { page } }, testInfo) => {
    const info = expectInfo();
    for (const [flow, item] of [["06-item-video", info.video_item], ["07-item-podcast", info.podcast_item],
      ["08-item-post", info.post_item], ["09-item-page", info.page_item]]) {
      await gotoDashboard(page, `#item/${item.id}`);
      await expect(page.locator("#yoinkHeading")).toHaveText(item.title, { timeout: 20_000 });
      const doc = page.locator("#yoinkDetail");
      await expect(doc).toContainText(item.text);
      if (item.transcript) expect(await page.locator("#yoinkDetail .reader-para").count()).toBeGreaterThan(3);
      await checkLayout(page, testInfo, flow);
      await shot(page, testInfo, flow);
    }
    // Opening from the list works too, and Back returns to the list.
    await gotoDashboard(page);
    await waitForLibrary(page);
    const first = page.locator("#libraryGrid .uoink-card").first();
    const title = (await first.locator(".card-title").textContent()).trim();
    await first.click();
    await expect(page.locator("#yoinkHeading")).toHaveText(title);
    await page.locator("#yoinkBack").click();
    await expect(page.locator("#tab-library")).toBeVisible();
  });

  test("an item with no transcript says why", async ({ dash: { page } }, testInfo) => {
    const info = expectInfo();
    await gotoDashboard(page, `#item/${info.no_transcript_id}`);
    await expect(page.locator("#yoinkHeading")).toHaveText(info.no_transcript_title, { timeout: 20_000 });
    const note = page.locator("#yoinkTranscriptNote");
    await expect(note).toBeVisible();
    await expect(note).not.toHaveText("");
    await checkLayout(page, testInfo, "no transcript");
    await shot(page, testInfo, "10-item-no-transcript");
  });

  test("move an item to a shelf", async ({ dash: { page } }, testInfo) => {
    const info = expectInfo();
    await gotoDashboard(page, `#item/${info.move_item_id}`);
    await expect(page.locator("#yoinkHeading")).toHaveText(info.move_item_title, { timeout: 20_000 });
    const reader = page.locator("#tab-yoink");
    // Look for a shelf control in the reader, including the More actions menu.
    let control = reader.getByRole("button", { name: /shelf|move to/i })
      .or(reader.getByRole("combobox", { name: /shelf/i }))
      .or(reader.locator("[data-qa=move-to-shelf], [data-move-shelf]"));
    if (!(await control.count())) {
      const more = reader.locator("#yoinkActionMenu > summary");
      if (await more.isVisible()) {
        await more.click();
        control = reader.locator("#yoinkActionMenu").getByRole("button", { name: /shelf|move to/i });
      }
    }
    if (!(await control.count())) {
      await shot(page, testInfo, "11-move-to-shelf-missing");
      testInfo.annotations.push({ type: "gap", description: "No move-to-shelf control in the dashboard reader in this build." });
      test.skip(true, "No move-to-shelf control in the dashboard reader in this build.");
    }
    const target = info.shelves.find((s) => s !== "Uncategorized");
    await control.first().click();
    const choice = page.getByRole("option", { name: target })
      .or(page.getByRole("menuitem", { name: target }))
      .or(page.getByRole("button", { name: target, exact: true })).first();
    if (await page.getByRole("combobox", { name: /shelf/i }).count()) {
      await page.getByRole("combobox", { name: /shelf/i }).first().selectOption({ label: target });
    } else {
      await choice.click();
    }
    const confirm = page.getByRole("button", { name: /^(move|save|done|apply)/i });
    if (await confirm.count()) await confirm.first().click();
    await expect.poll(async () => (await api(`/api/corpus/v1/items/${info.move_item_id}`)).data?.data?.item?.facets?.topic,
      { timeout: 20_000 }).toBe(target);
    await shot(page, testInfo, "11-move-to-shelf");
  });

  test("settings open and a switch toggles and persists", async ({ dash: { page } }, testInfo) => {
    const key = "rediscover_shelves_enabled";
    const before = (await api("/settings")).data.settings[key] !== false;
    await gotoDashboard(page, "#settings/capture");
    const box = page.locator("#rediscoverShelvesToggle");
    await expect(box).toBeVisible({ timeout: 20_000 });
    await box.scrollIntoViewIfNeeded();
    await expect(box).toBeChecked({ checked: before });
    await checkTheme(page, testInfo);
    await checkLayout(page, testInfo, "settings");
    await shot(page, testInfo, "12-settings");
    await box.click();
    await expect(box).toBeChecked({ checked: !before });
    await expect.poll(async () => (await api("/settings")).data.settings[key] !== false, { timeout: 10_000 }).toBe(!before);
    await expect(page.locator("#rediscoverShelvesToggleSaveStatus")).not.toHaveText("");
    await shot(page, testInfo, "13-settings-saved");
    await page.reload();
    await expect(page.locator("#rediscoverShelvesToggle")).toBeChecked({ checked: !before, timeout: 20_000 });
    // Put it back so the next run starts the same way.
    await page.locator("#rediscoverShelvesToggle").click();
    await expect.poll(async () => (await api("/settings")).data.settings[key] !== false, { timeout: 10_000 }).toBe(before);
  });

  test("health view renders", async ({ dash: { page } }, testInfo) => {
    const info = expectInfo();
    await gotoDashboard(page);
    await waitForLibrary(page);
    await openSearch(page, info.no_transcript_title);
    const card = page.locator(`#libraryGrid .uoink-card[data-card-id="${info.no_transcript_id}"]`);
    await expect(card).toBeVisible();
    // A match quote is plain words, never the saved file's Markdown.
    const quotes = await page.locator("#libraryGrid .uoink-card .card-match").allTextContents();
    expectNoNewProblems("search-snippet", quotes.filter((q) => /\*\*|(^|["“\s])#{1,3} \S/.test(q))
      .map((q) => `search quote shows raw Markdown: ${q.trim().slice(0, 90)}`), testInfo);
    await shot(page, testInfo, "14-search-no-transcript");
    const badge = card.locator(".health-exception");
    await expect(badge).toBeVisible();
    await badge.click();
    const drawer = page.locator("#itemHealthDrawer");
    await expect(drawer).toBeVisible();
    await expect(page.locator("#itemHealthTitle")).toHaveText(info.no_transcript_title);
    await expect(page.locator("#itemHealthIssues li").first()).toBeVisible();
    await checkLayout(page, testInfo, "health drawer");
    await shot(page, testInfo, "15-health-drawer");
    await page.keyboard.press("Escape");
    await expect(drawer).toBeHidden();
    // Activity and the helper status read cleanly too.
    await gotoDashboard(page, "#activity");
    await expect(page.locator("#tab-activity")).toBeVisible();
    await checkLayout(page, testInfo, "activity");
    await shot(page, testInfo, "16-activity");
    await gotoDashboard(page, "#settings/app");
    await expect(page.locator("#helperStatus")).not.toHaveText(/Checking/, { timeout: 20_000 });
    await shot(page, testInfo, "17-settings-app");
  });
});

test.describe("empty library", { tag: "@empty" }, () => {
  test("empty library state", async ({ dash: { page } }, testInfo) => {
    await gotoDashboard(page);
    await waitForLibrary(page, { empty: true });
    await expect(page.locator("#libraryEmpty h2")).toHaveText("No saved uoinks yet.");
    await expect(page.locator("#libraryGrid .uoink-card")).toHaveCount(0);
    // The count badge hides at zero, or says 0.
    const count = page.locator("#libraryCount");
    if (await count.isVisible()) await expect(count).toHaveText("0");
    await checkTheme(page, testInfo);
    await checkLayout(page, testInfo, "empty library");
    await shot(page, testInfo, "20-empty-library");
    for (const [tab, flow] of [["activity", "21-empty-activity"], ["for-you", "22-empty-for-you"]]) {
      await gotoDashboard(page, `#${tab}`);
      await expect(page.locator(`#tab-${tab}`)).toBeVisible({ timeout: 20_000 });
      await checkLayout(page, testInfo, flow);
      await shot(page, testInfo, flow);
    }
  });
});

test.describe("1,000-item library", { tag: "@big" }, () => {
  test("a 1,000-item library scrolls without layout breakage", async ({ dash: { page } }, testInfo) => {
    const info = expectInfo();
    await gotoDashboard(page);
    await waitForLibrary(page);
    await expect(page.locator("#libraryCount")).toHaveText(String(info.total));
    const cards = page.locator("#libraryGrid .uoink-card");
    const pageSize = await cards.count();
    expect(pageSize).toBeGreaterThan(0);
    // Scroll the whole library in, one Load more at a time, like a person would.
    const timings = [];
    for (let i = 0; i < 60 && (await cards.count()) < info.total; i++) {
      const before = await cards.count();
      const started = Date.now();
      await page.locator("#loadMore").scrollIntoViewIfNeeded();
      await page.locator("#loadMore").click();
      await expect.poll(() => cards.count(), { timeout: 15_000 }).toBeGreaterThan(before);
      timings.push(Date.now() - started);
      if (i === 2) await shot(page, testInfo, "29-big-library-page-4");
    }
    await expect(cards).toHaveCount(info.total);
    await expect(page.locator("#loadMore")).toBeHidden();
    const slowest = Math.max(...timings);
    testInfo.annotations.push({ type: "timing", description: `${timings.length} x Load more to ${info.total} cards: first ${timings[0]} ms, last ${timings.at(-1)} ms, slowest ${slowest} ms` });
    expect(slowest, "each Load more answers within 5 seconds").toBeLessThan(5_000);
    // Cards stack without overlapping and stay inside the window.
    const boxes = await cards.evaluateAll((els) => els.map((el) => { const r = el.getBoundingClientRect(); return { top: r.top, bottom: r.bottom, left: r.left, right: r.right, h: r.height }; }));
    const vw = await page.evaluate(() => document.documentElement.clientWidth);
    const problems = [];
    boxes.forEach((b, i) => {
      if (b.h < 20) problems.push(`card ${i} is ${Math.round(b.h)}px tall`);
      if (b.right > vw + 1 || b.left < -1) problems.push(`card ${i} runs outside the window (${Math.round(b.left)}..${Math.round(b.right)} of ${vw})`);
      if (i && b.top < boxes[i - 1].bottom - 1 && b.left < boxes[i - 1].right - 1) problems.push(`card ${i} overlaps card ${i - 1}`);
    });
    expectNoNewProblems("layout", problems, testInfo);
    await cards.last().scrollIntoViewIfNeeded();
    await checkLayout(page, testInfo, "big library");
    await shot(page, testInfo, "30-big-library-scrolled");
    // Search stays quick on a big library.
    const started = Date.now();
    await openSearch(page, "pricing lessons");
    await expect(cards.first().locator(".card-title")).toContainText(/pricing lessons/i, { timeout: 15_000 });
    await expect(page.locator("#resultSummary")).toContainText("shown of");
    testInfo.annotations.push({ type: "timing", description: `search on ${info.total} items: ${Date.now() - started} ms` });
    await shot(page, testInfo, "31-big-library-search");
  });
});
