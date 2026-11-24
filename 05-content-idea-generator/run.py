"""Content Idea Generator: read what founders and freelancers are really asking and keep only the ideas worth making."""

import html
import json
import sys
import time
from datetime import date
from pathlib import Path
from typing import Literal

import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
from common.claude import DRY_RUN, ask, run_stamp, write  # noqa: E402

POSTS_PER_SOURCE = 20
MIN_SCORE = 7
SEEN_FILE = HERE / "output" / "seen.json"
UA = {"User-Agent": "content-idea-generator/1.0 (portfolio demo)"}
WEEK = 7 * 24 * 3600
STACK_SITE = "freelancing"  # freelancing.stackexchange.com

SYSTEM = """You are the content strategist of an AI and automation brand for busy women who run businesses.
You get a batch of real posts from online communities. For each post, find the real problem behind it
and score from 1 to 10 how useful a post answering it would be for that audience.
Score low anything off topic, promotional, too technical or too niche.
Return one idea per post, keeping each post's id."""


class Idea(BaseModel):
    post_id: str
    pain_point: str
    score: int  # 1 to 10
    angle: str
    hook: str
    format: Literal["carousel", "reel", "text post"]


class Batch(BaseModel):
    ideas: list[Idea]


def from_hacker_news() -> list[dict]:
    """Ask HN threads from the last 7 days: people asking other founders for help."""
    since = int(time.time()) - WEEK
    url = f"https://hn.algolia.com/api/v1/search?tags=ask_hn&numericFilters=created_at_i>{since}&hitsPerPage={POSTS_PER_SOURCE}"
    r = requests.get(url, headers=UA, timeout=30)
    r.raise_for_status()
    return [
        {
            "id": f"hn-{h['objectID']}",
            "source": "Hacker News",
            "title": h["title"],
            "text": html_to_text(h.get("story_text") or ""),
            "votes": h.get("points") or 0,
            "replies": h.get("num_comments") or 0,
            "url": f"https://news.ycombinator.com/item?id={h['objectID']}",
        }
        for h in r.json()["hits"]
    ]


def from_stack_exchange() -> list[dict]:
    """Questions freelancers asked in the last 30 days, most voted first."""
    since = int(time.time()) - 30 * 24 * 3600
    url = (
        "https://api.stackexchange.com/2.3/questions"
        f"?order=desc&sort=votes&site={STACK_SITE}&pagesize={POSTS_PER_SOURCE}&fromdate={since}&filter=withbody"
    )
    r = requests.get(url, headers=UA, timeout=30)
    r.raise_for_status()
    return [
        {
            "id": f"se-{q['question_id']}",
            "source": "Freelancing Stack Exchange",
            "title": html.unescape(q["title"]),
            "text": html_to_text(q.get("body") or ""),
            "votes": q.get("score", 0),
            "replies": q.get("answer_count", 0),
            "url": q["link"],
        }
        for q in r.json()["items"]
    ]


def html_to_text(s: str) -> str:
    return " ".join(BeautifulSoup(s, "html.parser").get_text(" ").split())


def main() -> None:
    seen = set(json.loads(SEEN_FILE.read_text())) if SEEN_FILE.exists() else set()

    posts = []
    for source in (from_hacker_news, from_stack_exchange):
        try:
            posts += [p for p in source() if p["id"] not in seen]
        except requests.RequestException as err:
            print(f"  {source.__name__} not reachable: {err}")
    print(f"{len(posts)} new posts")
    if not posts:
        return
    if DRY_RUN:
        print("DRY RUN: no API key, nothing sent.")
        return

    by_id = {p["id"]: p for p in posts}
    batch = "\n\n".join(
        f"[id: {p['id']}] {p['source']} · {p['votes']} votes · {p['replies']} replies\n"
        f"Title: {p['title']}\n{p['text'][:1500]}"
        for p in posts
    )
    ideas = [i for i in ask(SYSTEM, batch, Batch).ideas if i.post_id in by_id]
    keep = sorted((i for i in ideas if i.score >= MIN_SCORE), key=lambda i: -i.score)

    week = date.today().isoformat()
    lines = [
        f"# Idea bank · {week}",
        "",
        f"_Last run: {run_stamp()} · {len(posts)} real posts read · {len(keep)} kept (score {MIN_SCORE}+)_",
        "",
    ]
    for i in keep:
        p = by_id[i.post_id]
        lines += [
            f"## {i.hook}",
            f"- **Score:** {i.score}/10 · **Format:** {i.format}",
            f"- **Pain point:** {i.pain_point}",
            f"- **Angle:** {i.angle}",
            f"- **Source:** [{p['title']}]({p['url']}) · {p['source']}",
            "",
        ]
    out = HERE / "output"
    write(out / f"ideas-{week}.md", "\n".join(lines))
    write(out / "latest.md", "\n".join(lines))

    seen |= set(by_id)
    write(SEEN_FILE, json.dumps(sorted(seen)))


if __name__ == "__main__":
    main()
