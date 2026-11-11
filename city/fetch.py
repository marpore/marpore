"""Collect everything the picture needs: GitHub activity, today's weather, sunrise and sunset.

Only aggregated numbers leave this module. Repository names never appear in the
output or in the logs, so private repositories stay private.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from zoneinfo import ZoneInfo

GRAPHQL = "https://api.github.com/graphql"
USER_AGENT = "city-readme"
OTHER = "Other"

VIEWER = "{ viewer { login id createdAt contributionsCollection { contributionYears } } }"

YEAR = """
query($from: DateTime!, $to: DateTime!) {
  viewer { contributionsCollection(from: $from, to: $to) {
    totalCommitContributions
    contributionCalendar { weeks { contributionDays { date contributionCount } } }
  } }
}"""

REPO_FIELDS = "id isEmpty languages(first: 6, orderBy: {field: SIZE, direction: DESC}) { edges { size node { name color } } }"

OWNED = """
query($cursor: String) {
  viewer { repositories(first: 100, after: $cursor, ownerAffiliations: [OWNER, COLLABORATOR, ORGANIZATION_MEMBER]) {
    pageInfo { hasNextPage endCursor } nodes { %s }
  } }
}""" % REPO_FIELDS

CONTRIBUTED = """
query($cursor: String) {
  viewer { repositoriesContributedTo(first: 100, after: $cursor, contributionTypes: [COMMIT], includeUserRepositories: false) {
    pageInfo { hasNextPage endCursor } nodes { %s }
  } }
}""" % REPO_FIELDS

HISTORY_FIELDS = "pageInfo { hasNextPage endCursor } nodes { oid authoredDate }"

HISTORY_BATCH = """
query($ids: [ID!]!, $author: ID!, $n: Int!) {
  nodes(ids: $ids) { ... on Repository { id defaultBranchRef { target { ... on Commit {
    history(first: $n, author: {id: $author}) { %s }
  } } } } }
}""" % HISTORY_FIELDS

HISTORY_PAGE = """
query($id: ID!, $author: ID!, $n: Int!, $cursor: String) {
  node(id: $id) { ... on Repository { id defaultBranchRef { target { ... on Commit {
    history(first: $n, after: $cursor, author: {id: $author}) { %s }
  } } } } }
}""" % HISTORY_FIELDS


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def gql(token: str, query: str, variables: dict | None = None, tries: int = 4) -> dict:
    """Run one GraphQL query. Partial data is accepted (some repositories may be off limits)."""
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    reason = "unknown error"
    for attempt in range(tries):
        request = urllib.request.Request(GRAPHQL, data=body, headers={
            "Authorization": f"bearer {token}", "User-Agent": USER_AGENT, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                payload = json.load(response)
            if payload.get("data") is not None:
                return payload["data"]
            reason = "the response had no data"
        except urllib.error.HTTPError as error:
            reason = f"HTTP {error.code}"
            if error.code in (401, 403):
                break
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            reason = type(error).__name__
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"GitHub GraphQL request failed ({reason})")


def list_repositories(token: str, ignore: set[str]) -> tuple[dict[str, dict[str, float]], dict[str, str]]:
    """Return {repository id: {language: share}} and {language: color}."""
    repos: dict[str, dict[str, float]] = {}
    colors: dict[str, str] = {}
    for query, field in ((OWNED, "repositories"), (CONTRIBUTED, "repositoriesContributedTo")):
        cursor = None
        while True:
            page = gql(token, query, {"cursor": cursor})["viewer"][field]
            for node in page["nodes"]:
                if not node or node["isEmpty"] or node["id"] in repos:
                    continue
                edges = [e for e in node["languages"]["edges"] if e["node"]["name"].lower() not in ignore]
                total = sum(e["size"] for e in edges)
                if total > 0:
                    repos[node["id"]] = {e["node"]["name"]: e["size"] / total for e in edges}
                    for e in edges:
                        if e["node"]["color"]:
                            colors[e["node"]["name"]] = e["node"]["color"]
                else:
                    repos[node["id"]] = {OTHER: 1.0}
            if not page["pageInfo"]["hasNextPage"]:
                break
            cursor = page["pageInfo"]["endCursor"]
    return repos, colors


def fetch_commits(token: str, repo_ids: list[str], author_id: str) -> tuple[dict[str, tuple[str, str]], int]:
    """Return {commit oid: (authored date, repository id)} for the author's commits on default branches."""
    commits: dict[str, tuple[str, str]] = {}
    skipped = 0

    def take(repo_id: str, history: dict) -> str | None:
        for node in history["nodes"]:
            commits.setdefault(node["oid"], (node["authoredDate"], repo_id))
        return history["pageInfo"]["endCursor"] if history["pageInfo"]["hasNextPage"] else None

    def history_of(node: dict | None) -> dict | None:
        ref = (node or {}).get("defaultBranchRef") or {}
        return (ref.get("target") or {}).get("history")

    def one(repo_id: str, cursor: str | None, size: int) -> str | None:
        node = gql(token, HISTORY_PAGE, {"id": repo_id, "author": author_id, "n": size, "cursor": cursor})["node"]
        history = history_of(node)
        return take(repo_id, history) if history else None

    pending: list[tuple[str, str | None]] = []
    for start in range(0, len(repo_ids), 8):
        chunk = repo_ids[start:start + 8]
        try:
            nodes = gql(token, HISTORY_BATCH, {"ids": chunk, "author": author_id, "n": 100})["nodes"]
            for repo_id, node in zip(chunk, nodes):
                history = history_of(node)
                if history:
                    cursor = take(repo_id, history)
                    if cursor:
                        pending.append((repo_id, cursor))
        except RuntimeError:
            pending.extend((repo_id, None) for repo_id in chunk)   # retry one by one below

    for repo_id, cursor in pending:
        first = cursor is None
        try:
            cursor = one(repo_id, cursor, 50 if first else 100)
            while cursor:
                cursor = one(repo_id, cursor, 100)
        except RuntimeError:
            skipped += 1
    return commits, skipped


def longest_streak(days: dict[str, int]) -> int:
    best = run = 0
    previous = None
    for key in sorted(days):
        day = dt.date.fromisoformat(key)
        if days[key] > 0:
            run = run + 1 if previous and (day - previous).days == 1 else 1
            best = max(best, run)
            previous = day
        else:
            previous = None
    return best


def wmo_kind(code: int | None) -> str:
    """Map a WMO weather code to one of the kinds the renderer can draw."""
    if code is None:
        return "clear"
    if code in (0, 1):
        return "clear"
    if code == 2:
        return "partly"
    if code in (45, 48):
        return "fog"
    if 51 <= code <= 67 or 80 <= code <= 82:
        return "rain"
    if 71 <= code <= 77 or code in (85, 86):
        return "snow"
    if code >= 95:
        return "thunder"
    return "cloudy"


def sun_times(lat: float, lon: float, day: dt.date, utc_offset: float) -> tuple[float, float]:
    """Approximate sunrise and sunset in local clock hours (used only when the weather API is down)."""
    n = day.timetuple().tm_yday
    declination = math.radians(-23.44) * math.cos(2 * math.pi / 365 * (n + 10))
    x = -math.tan(math.radians(lat)) * math.tan(declination)
    half_day = math.acos(max(-1.0, min(1.0, x))) * 12 / math.pi
    b = 2 * math.pi * (n - 81) / 364
    equation_of_time = 9.87 * math.sin(2 * b) - 7.53 * math.cos(b) - 1.5 * math.sin(b)
    noon = 12 - equation_of_time / 60 - (lon - 15 * utc_offset) / 15
    return noon - half_day, noon + half_day


def fetch_weather(lat: float, lon: float, tzname: str, now: dt.datetime) -> dict:
    def clock(stamp: str) -> float:
        t = dt.datetime.fromisoformat(stamp)
        return t.hour + t.minute / 60

    try:
        query = urllib.parse.urlencode({
            "latitude": lat, "longitude": lon, "hourly": "weather_code,snow_depth",
            "daily": "sunrise,sunset", "timezone": tzname, "forecast_days": 1})
        request = urllib.request.Request(f"https://api.open-meteo.com/v1/forecast?{query}", headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
        codes = (payload["hourly"]["weather_code"] + [None] * 24)[:24]
        depth = ((payload["hourly"].get("snow_depth") or []) + [0] * 24)[:24]
        kinds = [wmo_kind(c) for c in codes]
        return {
            "weather": kinds,
            "snow_cover": [k == "snow" or (d or 0) > 0.005 for k, d in zip(kinds, depth)],
            "sunrise": clock(payload["daily"]["sunrise"][0]),
            "sunset": clock(payload["daily"]["sunset"][0]),
        }
    except Exception as error:   # the picture is still worth drawing without a forecast
        log(f"weather unavailable ({type(error).__name__}); drawing a clear day")
        sunrise, sunset = sun_times(lat, lon, now.date(), now.utcoffset().total_seconds() / 3600)
        return {"weather": ["clear"] * 24, "snow_cover": [False] * 24, "sunrise": sunrise, "sunset": sunset}


def collect(token: str, lat: float, lon: float, tzname: str, ignore: set[str] | None = None) -> dict:
    tz = ZoneInfo(tzname)
    now = dt.datetime.now(tz)
    today = now.date()
    ignore = {name.lower() for name in (ignore or set())}

    viewer = gql(token, VIEWER)["viewer"]
    years = sorted(viewer["contributionsCollection"]["contributionYears"])

    days: dict[str, int] = {}
    official_commits = 0
    for year in years:
        cc = gql(token, YEAR, {"from": f"{year}-01-01T00:00:00Z", "to": f"{year}-12-31T23:59:59Z"})["viewer"]["contributionsCollection"]
        official_commits += cc["totalCommitContributions"]
        for week in cc["contributionCalendar"]["weeks"]:
            for day in week["contributionDays"]:
                days[day["date"]] = day["contributionCount"]
    active_years = sorted({int(key[:4]) for key, count in days.items() if count > 0})
    since = active_years[0] if active_years else int(viewer["createdAt"][:4])

    repos, colors = list_repositories(token, ignore)
    commits, skipped = fetch_commits(token, list(repos), viewer["id"])
    log(f"repositories: {len(repos)}, commits: {len(commits)}, repositories skipped: {skipped}")

    week_start = today - dt.timedelta(days=today.weekday())   # Monday
    month_start = today.replace(day=1)
    week = month = 0
    hist: dict[int, dict[int, dict[str, float]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    for stamp, repo_id in commits.values():
        when = dt.datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(tz)
        if when.date() > today:
            continue
        week += when.date() >= week_start
        month += when.date() >= month_start
        year = max(when.year, since)
        for language, share in repos[repo_id].items():
            hist[when.hour][year][language] += share

    return {
        "login": viewer["login"],
        "date": today.isoformat(),
        "timezone": tzname,
        "since": since,
        "total_commits": max(official_commits, len(commits)),
        "week_commits": week,
        "month_commits": month,
        "longest_streak": longest_streak(days),
        "hist": {h: {y: {k: round(v, 3) for k, v in langs.items()} for y, langs in by_year.items()} for h, by_year in hist.items()},
        "colors": colors,
        **fetch_weather(lat, lon, tzname, now),
    }
