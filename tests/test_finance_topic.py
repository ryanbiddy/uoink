"""Offline routing regressions against the shipped topic configuration."""
from __future__ import annotations

import ast
import json
import logging
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
FINANCE = "Finance and Markets"


@pytest.fixture(scope="module")
def classify_topic():
    # Load the real routing functions without server startup or profile access.
    source = ROOT / "server.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    names = {"_load_topics", "_classify_topic"}
    nodes = [node for node in tree.body
             if isinstance(node, ast.FunctionDef) and node.name in names]
    assert {node.name for node in nodes} == names
    scope = {
        "json": json, "log": logging.getLogger(__name__),
        "TOPICS_PATH": ROOT / "topics.json",
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), "exec"), scope)
    return scope["_classify_topic"]


@pytest.mark.parametrize("title", [
    "CoreWeave Shares Plunge, Bond Yields Explode to 15%",
    "How Low Can We Go? AI Stock Sell Off Continues",
    "CoreWeave Stock Is TANKING... Here's My Next Move",
    "Is the Bond Market Signaling THE END for CoreWeave?",
    "AI Stocks Are Crashing. Here's What I'm Actually Doing",
    "CoreWeave earnings and capex outlook",
    "Nasdaq and S&P: investor concerns over valuation",
    "Corporate bonds and treasury yields",
    "IPO pricing and the initial public offering",
    "Credit spreads and corporate debt",
    "Dividend outlook and market cap after the sell-off",
    "CoreWeave earnings call highlights",
    "What the latest earnings report tells us",
    "Quarterly earnings explained",
    "Preparing for earnings season",
    "Company valuation explained",
    "Understanding stock valuation",
    "What is a valuation multiple?",
    "Tech stocks to watch",
    "Growth stocks explained",
    "Getting started with stock investing",
    "Value investing explained",
    "CoreWeave Stock Drops 20% After Earnings",
    "CoreWeave shares fell after earnings",
    "Nvidia Q3 earnings: what happened",
    "Nvidia stock is crashing",
    "CoreWeave stocks are tanking",
    "CoreWeave IPO explained",
    "Why bonds are selling off",
    "Adobe earnings beat expectations",
    "Retail earnings miss estimates",
    "A closer look at Q1 earnings",
    "Q2 earnings: the numbers",
    "Q4 earnings: what changed?",
    "Earnings growth slows at the chipmakers",
    "Intel earnings outlook for next year",
    "Earnings results from the banks",
    "Oracle stock falls following guidance",
    "A stock crash explained",
    "Apple stock rally accelerates",
    "AMD stock surges on results",
    "Tesla stock jumps on delivery numbers",
    "Amazon shares dropped on guidance",
    "Meta shares jumped after results",
    "Bank shares rallied on rate cut hopes",
    "Airline shares surged as fuel prices fell",
    "Treasury bonds explained for beginners",
    "Treasury yields rise again",
    "How to find an IPO date",
    "The latest IPO debut",
    "Understanding credit ratings",
    "Government debt explained",
    "Debt markets under pressure",
    "How debt financing works",
    "Debt refinancing explained",
    "What causes a debt crisis?",
    "CoreWeave Stock Plunges",
    "Why Nvidia stock fell",
    "Stocks to buy now",
    "Why stocks fell today",
    "Where the S&P 500 goes next",
])
def test_finance_titles(classify_topic, title):
    assert classify_topic({"title": title}) == FINANCE


@pytest.mark.parametrize("metadata", [
    {"title": "AI Stocks Are Crashing. Here's What I'm Actually Doing",
     "description": "Follow me on Twitter for daily updates."},
    {"title": "CoreWeave Stock Is TANKING... Here's My Next Move",
     "description": "An earnings report review and my research workflow."},
    {"title": "How Low Can We Go? AI Stock Sell Off Continues",
     "description": "Stock market news and the earnings outlook. Follow me on Instagram and Twitter."},
])
def test_finance_outscores_boilerplate(classify_topic, metadata):
    # Illustrative metadata; the handoff supplies titles, not descriptions.
    assert classify_topic(metadata) == FINANCE


@pytest.mark.parametrize("metadata, previous_topic", [
    ({"title": "AI Stocks Are Crashing. Here's What I'm Actually Doing",
      "description": "Follow me on Twitter for daily updates.",
      "tags": ["AI stocks", "stock market news"], "channel": "Market Notes"},
     "Social Media Research"),
    ({"title": "CoreWeave Stock Is TANKING... Here's My Next Move",
      "description": "An earnings report review and my research workflow.",
      "tags": ["stock analysis"], "channel": "Market Notes"},
     "Productivity and Workflows"),
    ({"title": "How Low Can We Go? AI Stock Sell Off Continues",
      "description": "Stock market news and the earnings outlook. Follow me on Instagram and Twitter.",
      "tags": ["AI stocks"], "channel": "Market Notes"},
     "Social Media Research"),
    ({"title": "Is the Bond Market Signaling THE END for CoreWeave?",
      "description": "Follow me on Twitter for daily updates.",
      "tags": ["fixed income"], "channel": "Market Notes"},
     "Social Media Research"),
    ({"title": "CoreWeave Shares Plunge, Bond Yields Explode to 15%",
      "description": "Subscribe for more analysis.",
      "tags": ["share price", "twitter"], "channel": "Market Notes"},
     "Social Media Research"),
    ({"title": "CoreWeave, Nebius & IREN Are Crashing",
      "description": "Earnings outlook, corporate debt and stock prices. Follow me on Twitter and Instagram.",
      "tags": ["AI stocks", "stock analysis"], "channel": "Market Notes"},
     "Social Media Research"),
])
def test_finance_metadata_corrects_misroutes(classify_topic, monkeypatch, metadata, previous_topic):
    # Illustrative financial context competes with social and workflow keywords.
    scope = classify_topic.__globals__
    config = scope["_load_topics"]()
    previous = {
        **config,
        "topics": [topic for topic in config["topics"] if topic["name"] != FINANCE],
    }
    with monkeypatch.context() as patch:
        patch.setitem(scope, "_load_topics", lambda: previous)
        assert classify_topic(metadata) == previous_topic
    assert classify_topic(metadata) == FINANCE


def test_finance_keywords_do_not_double_count_substrings(classify_topic):
    config = classify_topic.__globals__["_load_topics"]()
    topics = [topic for topic in config["topics"] if topic["name"] == FINANCE]
    assert len(topics) == 1
    assert set(topics[0]) == {"name", "keywords"}
    keywords = topics[0]["keywords"]
    assert all(isinstance(keyword, str) and keyword == keyword.strip()
               for keyword in keywords)
    keywords = [keyword.lower() for keyword in keywords]
    assert len(keywords) == len(set(keywords))
    assert "investing workflow" not in keywords
    assert not [(short, long) for short in keywords for long in keywords
                if short != long and short in long]


@pytest.mark.parametrize("metadata, expected", [
    ({"title": "Notion workflow for time management and deep work"},
     "Productivity and Workflows"),
    ({"title": "An expert shares a productivity tip",
      "description": "Give credit to the team; small changes yield results."},
     "Productivity and Workflows"),
    ({"title": "Shorts made with stock footage"}, "Social Media Research"),
    ({"title": "A workflow for paying down technical debt"},
     "Productivity and Workflows"),
    ({"title": "Tripod setup and camera angles"}, "Uncategorized"),
    ({"title": "James Bond behind the scenes"}, "Uncategorized"),
    ({"title": "Python generators and yield"}, "Uncategorized"),
    ({"title": "Give credit to the team"}, "Uncategorized"),
    ({"title": "Free stock footage sites for video editors"}, "Uncategorized"),
    ({"title": "Best royalty-free stock music for vlogs"}, "Uncategorized"),
    ({"title": "My key learnings from a year of filming"}, "Uncategorized"),
    ({"title": "Yearnings for a simpler life"}, "Uncategorized"),
    ({"title": "Model evaluation explained"}, "Uncategorized"),
    ({"title": "Self-evaluation tips"}, "Uncategorized"),
    ({"title": "How to create upsell offers for your course"}, "Uncategorized"),
    ({"title": "How to sell offline at craft fairs"}, "Uncategorized"),
    ({"title": "AI stock footage generator review"}, "Uncategorized"),
    ({"title": "Make money selling AI stock images"}, "Uncategorized"),
    ({"title": "Investing in yourself"}, "Uncategorized"),
    ({"title": "Stocksy contributor review"}, "Uncategorized"),
    ({"title": "GPT model evaluation: my key learnings"}, "AI and ML"),
    ({"title": "Productivity system review",
      "description": "My learnings after a month, plus a self-evaluation."},
     "Productivity and Workflows"),
    ({"title": "Instagram growth learnings",
      "description": "How I upsell offers and evaluation of my funnel."},
     "Social Media Research"),
    ({"title": "Stock footage editing workflow",
      "tags": ["AI stock images", "Stocksy"],
      "channel": "Investing in yourself", "uploader": "Key Learnings"},
     "Productivity and Workflows"),
    ({"title": "Livestock farming in rural Kenya"}, "Uncategorized"),
    ({"title": "Selling offline at craft fairs"}, "Uncategorized"),
    ({"title": "Mom shares fall cleaning routine"}, "Uncategorized"),
    ({"title": "Interior designer shares fall decor ideas"}, "Uncategorized"),
    ({"title": "Patient shares surgery recovery story"}, "Uncategorized"),
    ({"title": "Coach shares jump rope workout"}, "Uncategorized"),
    ({"title": "Expert shares dropshipping mistakes"}, "Uncategorized"),
    ({"title": "Tennis pro shares rally drills"}, "Uncategorized"),
    ({"title": "Driver shares rally racing secrets"}, "Uncategorized"),
    ({"title": "Jordan 4 restock drop date"}, "Uncategorized"),
    ({"title": "Target restock fall decor haul"}, "Uncategorized"),
    ({"title": "Target restocks fall decor haul"}, "Uncategorized"),
    ({"title": "Hobby Lobby restocks fall decor 50% off"}, "Uncategorized"),
    ({"title": "Dollar Tree restocks fall items"}, "Uncategorized"),
    ({"title": "When do Pokemon restocks drop?"}, "Uncategorized"),
    ({"title": "Nike restocks drop this week"}, "Uncategorized"),
    ({"title": "A cozy entryway",
      "tags": ["homegoods restocks", "fall decor"]}, "Uncategorized"),
    ({"title": "Dollar Tree restock fall finds"}, "Uncategorized"),
    ({"title": "A cozy living room",
      "tags": ["homegoods restock", "fall decor 2026"]}, "Uncategorized"),
    ({"title": "Pokemon card restock drop haul"}, "Uncategorized"),
    ({"title": "Corporate bonding games for team building"}, "Uncategorized"),
    ({"title": "Learning to code pays dividends"}, "Uncategorized"),
    ({"title": "Why consistency pays dividends"}, "Uncategorized"),
    ({"title": "Is the stock marketplace worth it for photographers?"}, "Uncategorized"),
    ({"title": "Selling photos on the stock marketplace"}, "Uncategorized"),
    ({"title": "Upselling offers that convert"}, "Uncategorized"),
    ({"title": "Selling off my camera gear"}, "Uncategorized"),
    ({"title": "Adobe Stock marketplace review"}, "Uncategorized"),
    ({"title": "Best stock marketplace for photographers"}, "Uncategorized"),
    ({"title": "Salt & pepper S&P shakers"}, "Uncategorized"),
    ({"title": "My camera bag",
      "description": "Gear: https://www.amazon.com/dp/B0EXAMPLE?tag=x-20&s=electronics&psc=1"},
     "Uncategorized"),
    ({"title": "Stockholm travel vlog"}, "Uncategorized"),
    ({"title": "Grandma shares her lasagna recipe"}, "Uncategorized"),
    ({"title": "Chef shares 5 knife skills every cook needs"}, "Uncategorized"),
    ({"title": "A walk through the countryside",
      "description": "B-roll from Storyblocks stock footage"}, "Uncategorized"),
    ({"title": "Making a short film", "description": "Filming on a budget.",
      "tags": ["stock footage", "stock music"],
      "channel": "Stockholm Film Club", "uploader": "Alex shares tips"},
     "Uncategorized"),
])
def test_existing_routes_are_preserved(classify_topic, monkeypatch, metadata, expected):
    scope = classify_topic.__globals__
    config = scope["_load_topics"]()
    previous = {
        **config,
        "topics": [topic for topic in config["topics"] if topic["name"] != FINANCE],
    }
    with monkeypatch.context() as patch:
        patch.setitem(scope, "_load_topics", lambda: previous)
        assert classify_topic(metadata) == expected
    assert classify_topic(metadata) == expected


@pytest.mark.parametrize("title", [
    "CoreWeave Shares Plunge, Bond Yields Explode to 15%",
    "AI Stocks Are Crashing. Here's What I'm Actually Doing",
])
def test_finance_beats_a_three_platform_link_block(classify_topic, title):
    metadata = {
        "title": title,
        "description": ("Not financial advice. I am not a financial advisor.\n"
                        "Follow me on Twitter, Instagram and TikTok for daily updates. #stockmarket"),
        "tags": ["coreweave stock", "stock market", "stocks", "investing"],
        "channel": "Market Notes",
    }
    assert classify_topic(metadata) == FINANCE


HEADLINES = [
    "CoreWeave Shares Plunge, Bond Yields Explode to 15% -Elon Musk Reacts Amid Private Credit Warning",
    "Is the Bond Market Signaling THE END for CoreWeave? (CRWV Stock)",
    "CoreWeave, Nebius & IREN Are Crashing...The Market Is Wrong",
    "AI Stocks Are Crashing. Here's What I'm Actually Doing",
    "How Low Can We Go? | AI Stock Sell Off Continues | Latest KEEL, BTBT, CRWV, GLXY, RIOT & CORZ News",
    "CoreWeave Stock Is TANKING... Here's My Next Move",
]
CREATOR_DESCRIPTION = (
    "Get 2 free stocks when you open a Webull account: https://example.com/webull\n"
    "Support the channel on Patreon: https://example.com/patreon\n"
    "Follow me on Twitter, Instagram and TikTok.\n"
    "I am not a financial adviser. This is not financial advice.\n"
    "#coreweave #stocks #investing{extra}"
)
CREATOR_TAGS = ["coreweave", "crwv", "coreweave stock", "crwv stock", "stocks",
                "investing", "stock market"]


@pytest.mark.parametrize("extra", [" #stockmarket", ""], ids=["with-stockmarket", "without"])
@pytest.mark.parametrize("title", HEADLINES)
def test_headline_videos_route_to_finance_with_creator_metadata(classify_topic, title, extra):
    # The six captures from Oct 15 with a typical finance-creator description:
    # broker referral, Patreon, three social platforms, disclaimer, hashtags.
    metadata = {"title": title, "description": CREATOR_DESCRIPTION.format(extra=extra),
                "tags": CREATOR_TAGS, "channel": "Market Notes"}
    assert classify_topic(metadata) == FINANCE
