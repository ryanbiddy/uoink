"""Build the made-up shelf routing fixture (library.json + items.json).

Run from the repo root: python tests/fixtures/shelves/make_fixture.py
The output is committed; the tests read the JSON, not this script. Every
name, handle and domain here is invented.

library.json: saves already on shelves (the evidence a router may learn
from), including a few that sit on the wrong shelf, as real libraries do.
items.json: new saves with the shelf a careful person would pick ("truth").
Truth is "Uncategorized" when no shelf fits, and "Clips" for short videos
with nothing to go on.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent

POOLS = {
    "AI and ML": [
        "LLM", "fine-tuning", "embeddings", "a 7B model", "inference costs", "GPU memory",
        "prompting tricks", "agents", "an eval harness", "the tokenizer", "a longer context window",
        "open weights", "quantization", "a RAG pipeline", "a vector database", "model cards",
        "benchmark scores", "a diffusion model", "the training run", "attention layers",
        "an AI agent", "a local model", "LoRA adapters", "chain of thought", "hallucinations",
        "synthetic data", "model distillation", "ChatGPT", "transformer internals", "reward models",
    ],
    "Social Media Research": [
        "engagement rate", "the algorithm", "a hook in the first second", "watch time",
        "the retention graph", "posting cadence", "the creator economy", "follower growth",
        "carousel posts", "reach and impressions", "short-form video", "TikTok", "Instagram reels",
        "audience growth", "content strategy", "thumbnail tests", "comment replies", "UGC",
        "brand deals", "LinkedIn posts", "a viral format", "story views", "creator analytics",
        "save rate", "duets and stitches",
    ],
    "New Tools to Try": [
        "a new app", "a browser extension", "a menu bar app", "a free tool", "an open source app",
        "a tiny CLI", "a keyboard launcher", "a screenshot tool", "a clipboard manager",
        "an app launch", "a beta invite", "a side project", "an indie tool", "this little utility",
        "a tool review", "a Mac app", "a self-hosted dashboard", "a plugin", "underrated tools",
        "the waitlist", "a must try app",
    ],
    "Job Hunt and Career": [
        "my resume", "the job search", "a recruiter", "the hiring manager", "interview prep",
        "salary negotiation", "an offer letter", "a career change", "a portfolio review",
        "a cover letter", "the layoff", "a job offer", "a referral", "the onsite loop",
        "behavioral questions", "a promotion packet", "career advice", "tech jobs",
        "remote work", "a take-home assignment", "the job hunt",
    ],
    "Developer Marketing": [
        "devrel", "the developer community", "the docs site", "API onboarding",
        "developer experience", "build in public", "an open source launch", "the SDK",
        "a hackathon", "a conference talk", "technical content", "developer advocacy",
        "the changelog", "devtools", "product-led growth", "a Discord community",
        "sample apps", "the quickstart guide", "indie hacker", "founder-led marketing",
        "developer relations",
    ],
    "Productivity and Workflows": [
        "time blocking", "deep work", "a second brain", "a Notion template", "my Obsidian vault",
        "the weekly review", "a task manager", "inbox zero", "focus sessions", "pomodoro",
        "a morning routine", "a habit tracker", "workflow automation", "Zapier",
        "keyboard shortcuts", "calendar blocks", "note-taking", "daily planning",
        "getting things done", "time management",
    ],
    "Finance and Markets": [
        "the earnings report", "the stock price", "the S&P 500", "bond yields", "dividend stocks",
        "market cap", "company valuation", "interest rates", "index funds", "my portfolio",
        "the Nasdaq", "an IPO filing", "treasury yields", "quarterly earnings", "the sell-off",
        "investors", "the inflation print", "credit spreads", "the share price", "value investing",
    ],
    "Cooking": [
        "sourdough", "cast iron", "a slow braise", "knife skills", "pasta dough",
        "a weeknight dinner", "fermentation", "a spice blend", "the recipe", "meal prep",
        "a dutch oven", "pan sauce", "bread proofing", "ramen broth", "dumplings", "roast chicken",
        "brown butter", "a sheet pan supper",
    ],
    "Woodworking": [
        "dovetails", "the table saw", "a hand plane", "walnut slabs", "joinery", "a shop jig",
        "the router table", "an oil finish", "sharp chisels", "the workbench", "plywood",
        "mortise and tenon", "sanding grits", "an epoxy pour", "a cutting board", "box joints",
    ],
    "Music": [
        "a synth patch", "a chord progression", "the drum machine", "mixing vocals", "vinyl",
        "jazz piano", "a bass line", "a guitar pedal", "the sampler", "the album", "a live set",
        "mastering", "a melody", "a modular rack", "tape loops", "the horn section",
    ],
}

NO_SHELF = {
    "travel": ["a night train", "the old town", "carry-on packing", "a ferry crossing", "hostel tips",
               "a mountain pass", "jet lag", "street food stalls"],
    "gardening": ["tomato seedlings", "raised beds", "compost", "pruning roses", "seed starting",
                  "garden soil", "companion planting", "mulch"],
    "fitness": ["a deadlift", "zone two cardio", "a mobility routine", "rest days", "kettlebells",
                "a 10k plan", "grip strength"],
    "pets": ["the new puppy", "cat litter", "a dog walk", "the vet visit", "a parrot", "leash training"],
    "home": ["a leaky faucet", "drywall patch", "the water heater", "grout cleaning", "a squeaky door"],
}

MEME_LINES = ["lmao", "this is me", "when the build finally passes", "mood", "no context needed",
              "why is this so accurate", "me every monday", "the audacity", "real", "ok this got me",
              "sending this to everyone", "i can't breathe"]

TITLE_FRAMES = [
    "{A}: what I learned", "Why {A} matters more than {B}", "I tried {A} for a week",
    "{A} in 10 minutes", "The problem with {A}", "{A} and {B}, explained simply", "Notes on {A}",
    "How we handled {A}", "{A} vs {B}", "Stop ignoring {A}", "A small win with {A}",
    "{A}, {B} and a lot of coffee", "What nobody tells you about {A}", "{A} after one year",
    "Three mistakes with {A}", "My honest take on {A}", "Rethinking {A}",
]
BODY_FRAMES = [
    "Spent the weekend on {A}. The part nobody mentions is {B}.",
    "Short version: {A} works if you care about {B}.",
    "A few thoughts on {A}, {B} and {C}.",
    "Saving this for later. {A} again, and this time with {B}.",
    "We changed how we think about {A}. {B} was the surprise.",
    "If you only read one thing about {A} this month, make it this.",
    "Long post on {A}. It starts with {B} and ends somewhere near {C}.",
    "Honestly {A} is underrated. Pair it with {B}.",
]
NEUTRAL = ["Wild week.", "Worth a look.", "Bookmarking this.", "Took me a while to get here.",
           "Curious what others think.", "Still thinking about this one."]

# A second wording, never used while tuning the router: the holdout set
# checks that the numbers are not just the router learning these frames.
HOLDOUT_TITLES = [
    "Everything I got wrong about {A}", "A beginner's map of {A}", "{A} without the hype",
    "Is {A} worth it?", "Field report: {A} meets {B}", "Our team's playbook for {A}",
    "{A} at scale", "Cheap tricks for {A}", "The case against {A}", "{A} from scratch",
    "Unpopular opinion about {A}", "Where {A} falls apart", "{A}, {B}, and what comes next",
    "Six months of {A}", "A field guide to {A} and {B}",
]
HOLDOUT_BODIES = [
    "Our team leaned on {A} all quarter, and {B} kept coming up.",
    "Hot take: {A} beats {B} for most people.",
    "Bookmarked for the {A} rabbit hole. {B} too.",
    "The demo was {A}. The real lesson was {B}, then {C}.",
    "Pinning this. {A} plus {B} is the combo I keep coming back to.",
    "Someone asked about {A} so here is the long answer, with a detour into {C}.",
]
HOLDOUT_NEUTRAL = ["Big if true.", "Filing this away.", "More soon.", "Agree or disagree?",
                   "This took three tries.", "Saving for the weekend."]
BOILERPLATE = [
    "Follow me on Instagram: https://instagram.example.test/someone",
    "Twitter: https://x.example.test/someone",
    "TikTok - https://tiktok.example.test/@someone",
    "Business inquiries: press@example.com",
    "Join 40,000 subscribers on the newsletter https://news.example.test",
    "This video is sponsored by a made-up VPN. Use code SAVE20.",
    "Music by a stock library. Timestamps below.",
    "Support the channel on Patreon https://patreon.example.test/x",
    "Turn on notifications so you never miss a threads drop!",
]
SYLL = ["cedar", "lumen", "ferro", "quill", "tango", "maple", "orbit", "pixel", "rook", "sable",
        "tidal", "umber", "vesper", "willow", "zephyr", "amber", "basil", "coral", "delta", "ember",
        "fable", "garnet", "harbor", "indigo", "juniper", "kelp", "lark", "moss", "nectar", "opal"]
TAILS = ["bytes", "lab", "notes", "works", "daily", "loop", "desk", "fm", "hq", "club", "studio", "talks"]


def handle(rng):
    return "@" + rng.choice(SYLL) + "_" + rng.choice(TAILS) + str(rng.randint(1, 99))


def channel_name(rng):
    return rng.choice(SYLL).title() + " " + rng.choice(["Studio", "Notes", "Weekly", "Lab", "Talks", "Desk"])


def pick(rng, pool, n):
    return rng.sample(pool, min(n, len(pool)))


def topical_text(rng, pool, thin=False, distractor=None):
    terms = pick(rng, pool, 3)
    if distractor:
        terms[-1] = distractor
    a, b, c = terms[0], terms[1 % len(terms)], terms[2 % len(terms)]
    title = rng.choice(TITLE_FRAMES).format(A=a, B=b)
    title = title[0].upper() + title[1:]
    if thin:
        return title, ""
    body = rng.choice(BODY_FRAMES).format(A=a, B=b, C=c)
    if rng.random() < 0.4:
        body += " " + rng.choice(NEUTRAL)
    return title, body


class Maker:
    def __init__(self, seed):
        self.rng = random.Random(seed)
        self.n = 0
        self.authors = {shelf: [handle(self.rng) for _ in range(4)] for shelf in list(POOLS) + ["Memes"]}
        self.channels = {shelf: [channel_name(self.rng) for _ in range(3)] for shelf in POOLS}

    def vid(self, prefix):
        self.n += 1
        return f"{prefix}_{self.n:05d}"

    def item(self, shelf, pool, *, kind=None, thin=None, recurring=None, distractor=None):
        rng = self.rng
        kind = kind or rng.choice(["youtube", "youtube", "x", "x", "reddit", "page", "podcast"])
        thin = (rng.random() < 0.3) if thin is None else thin
        recurring = (rng.random() < 0.5) if recurring is None else recurring
        title, body = topical_text(rng, pool, thin=thin, distractor=distractor)
        row = {"truth": shelf, "kind": kind, "tags": [], "duration": None, "transcript": ""}
        if kind == "youtube":
            author = rng.choice(self.channels.get(shelf) or [channel_name(rng)]) if recurring else channel_name(rng)
            desc = body
            if rng.random() < 0.5:
                desc += "\n\n" + "\n".join(rng.sample(BOILERPLATE, rng.randint(2, 4)))
            row.update(video_id=self.vid("yt"), source_type="video", title=title, text=desc,
                       author=author, duration=rng.choice([45, 58, 240, 600, 900, 1500, 2400]),
                       url=f"https://www.youtube.com/watch?v={self.n:011d}")
            if rng.random() < 0.3:
                row["tags"] = [t.split()[-1].lower() for t in pick(rng, pool, 2)]
        elif kind == "x":
            author = rng.choice(self.authors.get(shelf) or [handle(rng)]) if recurring else handle(rng)
            text = (title + ". " + body).strip()
            snippet = text[:60]
            row.update(video_id=self.vid("x"), source_type="x_thread", title=f"{author}: {snippet}",
                       text=text, author=author, url=f"https://x.com/{author[1:]}/status/{10**15 + self.n}")
            if rng.random() < 0.25:
                row["has_video"] = True
                row["duration"] = rng.choice([12, 30, 48, 75, 140])
        elif kind == "reddit":
            author = "r/" + (shelf.split()[0].lower() if recurring else rng.choice(SYLL))
            row.update(video_id=self.vid("reddit"), source_type="reddit_thread", title=title,
                       text=body, author=author,
                       url=f"https://www.reddit.com/r/{author[2:]}/comments/{self.n:x}/post/")
        elif kind == "page":
            author = rng.choice(SYLL) + ".example.com"
            row.update(video_id=self.vid("page"), source_type="page", title=title,
                       text=body + " " + " ".join(rng.choice(NEUTRAL) for _ in range(2)),
                       author=author, url=f"https://{author}/post/{self.n}")
        else:
            author = channel_name(rng)
            terms = pick(rng, pool, 4)
            row.update(video_id=self.vid("pod"), source_type="podcast", title=title, text="",
                       author=author, duration=2700, url=f"https://feeds.example.test/ep/{self.n}",
                       transcript=" ".join(f"So we talked about {t} for a while." for t in terms)
                       + " Thanks for listening.")
        return row

    def clip(self, truth, *, author=None, line=None):
        rng = self.rng
        author = author or handle(rng)
        text = line if line is not None else rng.choice(["", "", "wait for it", "ok", "lol", "this", "unreal"])
        return {"truth": truth, "kind": "x", "video_id": self.vid("x"), "source_type": "x_thread",
                "title": f"{author}: {text}" if text else f"{author}: X post", "text": text,
                "author": author, "tags": [], "has_video": True,
                "duration": rng.choice([7, 11, 15, 22, 34, 52, 80]), "transcript": "",
                "url": f"https://x.com/{author[1:]}/status/{10**15 + self.n}"}


def build(seed=318):
    m = Maker(seed)
    rng = m.rng
    library = []
    # Existing shelves. Real libraries are uneven, and a few saves sit on the
    # wrong shelf.
    for shelf, pool in POOLS.items():
        count = 18 if shelf in ("Cooking", "Woodworking", "Music") else 24
        for _ in range(count):
            row = m.item(shelf, pool)
            row["topic"] = shelf
            library.append(row)
    for _ in range(14):
        author = rng.choice(m.authors["Memes"])
        row = m.clip("Memes", author=author, line=rng.choice(MEME_LINES))
        row["topic"] = "Memes"
        library.append(row)
    shelves = list(POOLS)
    for _ in range(10):
        wrong = rng.choice(shelves)
        right = rng.choice([s for s in shelves if s != wrong])
        row = m.item(right, POOLS[right])
        row["topic"] = wrong
        library.append(row)

    items = []
    for shelf, pool in POOLS.items():
        count = 26 if shelf not in ("Cooking", "Woodworking", "Music") else 16
        for i in range(count):
            distractor = None
            if rng.random() < 0.2:
                other = rng.choice([s for s in POOLS if s != shelf])
                distractor = rng.choice(POOLS[other])
            items.append(m.item(shelf, pool, distractor=distractor))
    for _ in range(14):
        items.append(m.clip("Memes", author=rng.choice(m.authors["Memes"]), line=rng.choice(MEME_LINES + [""])))
    for _ in range(30):
        items.append(m.clip("Clips"))
    for topic, pool in NO_SHELF.items():
        for _ in range(9 if topic == "gardening" else 7):
            row = m.item("Uncategorized", pool, kind=rng.choice(["youtube", "x", "reddit", "page"]),
                         recurring=False, thin=False)
            if row.get("duration") and row["duration"] <= 90 and row["kind"] in ("youtube", "x"):
                row["duration"] = 600 if row["kind"] == "youtube" else None
                row.pop("has_video", None)
            items.append(row)
    for folder, pool in (("Tools to try", POOLS["New Tools to Try"] + NO_SHELF["home"]),
                         ("AI learning", POOLS["AI and ML"]),
                         ("Memes", MEME_LINES)):
        for _ in range(10):
            if folder == "Memes":
                row = m.clip(folder, line=rng.choice(MEME_LINES))
            else:
                row = m.item(folder, pool, kind="x", thin=rng.random() < 0.5)
            row["folder"] = folder
            items.append(row)
    items.extend(hand_written(m))
    return library, items


def hand_written(m):
    """Cases written by hand from what goes wrong in real libraries."""
    rows = []

    def add(truth, kind, title, text="", author="", duration=None, tags=(), transcript="",
            source_type=None, has_video=None):
        vid = m.vid({"youtube": "yt", "x": "x", "reddit": "reddit", "page": "page", "podcast": "pod"}[kind])
        row = {"truth": truth, "kind": kind, "video_id": vid, "title": title, "text": text,
               "author": author, "duration": duration, "tags": list(tags), "transcript": transcript,
               "source_type": source_type or {"youtube": "video", "x": "x_thread", "reddit": "reddit_thread",
                                              "page": "page", "podcast": "podcast"}[kind],
               "url": f"https://example.com/hand/{vid}"}
        if has_video is not None:
            row["has_video"] = has_video
        rows.append(row)

    socials = ("Follow me on Instagram: https://instagram.example.test/devguy\n"
               "Twitter: https://x.example.test/devguy\nThreads: https://threads.example.test/devguy\n"
               "Join 120k subscribers!")
    add("Uncategorized", "youtube", "React hooks tutorial for beginners",
        "Learn useState and useEffect step by step.\n\n" + socials, "Byte Sized Dev", 1300)
    add("Uncategorized", "youtube", "React server components in 20 minutes",
        "We build a small app with server components.\n\n" + socials, "Byte Sized Dev", 1200)
    add("Music", "youtube", "Rare 1992 interview: a jazz pianist on improvising",
        "From a cassette in the attic. She talks about jazz piano, the album and the horn section.\n"
        "Subscribe for more threads from the archive.", "Archive Tapes", 1800)
    add("Music", "youtube", "Interview with a synth builder about modular racks",
        "We talk about a modular rack, tape loops and a synth patch that took a year.",
        "Archive Tapes", 2100)
    add("Clips", "x", "@pixel_loop7: ", "", "@pixel_loop7", 14, has_video=True)
    add("Clips", "x", "@harbor_fm2: watch till the end", "watch till the end", "@harbor_fm2", 41, has_video=True)
    add("Clips", "x", "@moss_desk11: 🤯", "🤯", "@moss_desk11", 9, has_video=True)
    add("AI and ML", "x", "@opal_lab4: this agent demo is wild",
        "this agent demo is wild. it plans, calls tools, and fixes its own bugs. LLM evals next.",
        "@opal_lab4", 58, has_video=True)
    add("AI and ML", "podcast", "Episode 41: The week in models",
        transcript=("Today we cover fine-tuning on a laptop, a new open weights LLM, and why "
                    "embeddings beat keyword search for a RAG pipeline. Then an AI agent that books travel."),
        author="Signal Hour", duration=3100)
    add("Finance and Markets", "podcast", "Market open, Tuesday",
        transcript=("Stocks fell after the earnings report, bond yields climbed, and the S&P 500 "
                    "gave back the week. Treasury yields are the story."), author="Open Bell", duration=1500)
    add("Uncategorized", "podcast", "A walk through the old harbor",
        transcript="We walk along the harbor and talk about ferries, fishing boats and fog.",
        author="Harbor Walks Radio", duration=2400)
    add("Uncategorized", "page", "Ten photos from a foggy coast",
        "Shot on a cheap film camera on a cold morning.", "photos.example.com")
    add("Job Hunt and Career", "reddit", "Got the offer after six onsite rounds",
        "Sharing my interview prep notes, the recruiter timeline and how I handled salary negotiation.",
        "r/careers")
    add("Uncategorized", "reddit", "My grandfather's interview tapes from 1971",
        "We found reels of tape in the garage with an interview about his farm.", "r/oldphotos")
    add("Developer Marketing", "x", "@ember_works3: our docs got 3x more signups",
        "rewrote the quickstart guide and the SDK samples. devrel wins are boring and that is fine.",
        "@ember_works3")
    add("Productivity and Workflows", "youtube", "My weekly review in Obsidian",
        "Time blocking, a weekly review and a second brain that actually gets used.\n\n" + socials,
        "Calm Desk", 840)
    add("Social Media Research", "youtube", "Why your Reels stall at 300 views",
        "Watch time, the hook and posting cadence. The algorithm cares about the first second.\n\n" + socials,
        "Growth Notes", 720)
    add("Woodworking", "x", "@walnut_and_pine: first set of hand cut dovetails",
        "first set of hand cut dovetails. chisels sharpened, walnut glued up.", "@walnut_and_pine", 28,
        has_video=True)
    add("Cooking", "x", "@crumb_club9: sourdough crumb shot", "sourdough crumb shot, 78% hydration",
        "@crumb_club9", 19, has_video=True)
    add("New Tools to Try", "x", "@lark_studio5: tiny menu bar app that shows your clipboard",
        "tiny menu bar app that shows your clipboard history. free, open source, no account.",
        "@lark_studio5")
    add("Uncategorized", "x", "@tidal_hq8: anyone else's train late again",
        "anyone else's train late again. third time this week", "@tidal_hq8")
    add("Uncategorized", "youtube", "Fixing a squeaky door hinge", "Two minutes, one screwdriver, some soap.",
        "Handy Hour", 300)
    add("Clips", "youtube", "#shorts", "#shorts #fyp", "Quick Cuts", 31)
    add("Clips", "youtube", "wait for it", "", "Quick Cuts", 18)
    add("AI and ML", "youtube", "Building AI agents in 30 seconds", "", "Quick Cuts", 30)
    return rows


def main():
    global TITLE_FRAMES, BODY_FRAMES, NEUTRAL
    library, items = build()
    (HERE / "library.json").write_text(json.dumps(library, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    (HERE / "items.json").write_text(json.dumps(items, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"library {len(library)} items {len(items)}")
    TITLE_FRAMES, BODY_FRAMES, NEUTRAL = HOLDOUT_TITLES, HOLDOUT_BODIES, HOLDOUT_NEUTRAL
    library, items = build(seed=2026)
    (HERE / "holdout-library.json").write_text(
        json.dumps(library, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    (HERE / "holdout-items.json").write_text(
        json.dumps(items, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"holdout library {len(library)} items {len(items)}")


if __name__ == "__main__":
    main()
