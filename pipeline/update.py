#!/usr/bin/env python3
"""Build SwordFinder's data files from Baseball Savant. No database, no API server.

Reads each day's Statcast pitches, keeps the swords, finds each one's clip, and writes plain JSON that the
static site loads from ui/data/. Safe to rerun: rows merge by pitch id, so nothing shrinks if a fetch fails.

Usage: update.py [--season 2026] [--days 3 | --backfill] [--clips 150] [--workers 3]
Set AZURE_STORAGE_CONNECTION_STRING to copy new clips into Azure; without it a row links to MLB's copy.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "ui" / "data"
STATE = ROOT / "pipeline" / "state"
AZURE_INDEX = ROOT / "pipeline" / "azure-clips.json"
SAVANT = "https://baseballsavant.mlb.com"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/130.0 Safari/537.36")
MIN_PUBLIC_SCORE = 90.0
SEASON_START = (3, 1)
SEASON_END = (10, 15)  # regular season only; the upper bound just limits requests
KEEP = ("pitch_type", "pitch_name", "release_speed", "effective_speed", "release_spin_rate", "description",
        "events", "zone", "bat_speed", "swing_length", "swing_path_tilt", "home_team", "away_team")
CONTAINER = "swordfinder-videos"


def fetch(url: str, tries: int = 4, timeout: int = 120) -> bytes:
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except OSError:
            if attempt == tries - 1:
                raise
            time.sleep(3 * (attempt + 1))
    raise AssertionError("unreachable")


def number(value):
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return int(out) if out.is_integer() and abs(out) < 1e12 else out


def sword_score(bat_speed: float, tilt, length) -> float:
    speed_part = (60 - bat_speed) / 60 * 50
    tilt_part = min(tilt / 60 * 25, 25) if tilt is not None else 0
    length_part = min(length / 10 * 25, 25) if length is not None else 0
    return round(50 + speed_part + tilt_part + length_part, 2)


def is_sword(pitch: dict) -> bool:
    """No K, no sword: a two-strike swing and miss with tracked bat speed that ended the at-bat."""
    speed = number(pitch.get("bat_speed"))
    return ("swinging_strike" in (pitch.get("description") or "")
            and pitch.get("strikes") == "2"
            and "strikeout" in (pitch.get("events") or "")
            and speed is not None and 0 < speed < 60)


def perceived_velocity(speed, extension):
    if speed is None or extension is None or 60.5 - extension <= 0:
        return None
    return round(speed * (60.5 / (60.5 - extension)), 1)


def zone_distance_inches(plate_x, plate_z, top, bottom):
    if None in (plate_x, plate_z, top, bottom):
        return None
    across = max(0, abs(plate_x) - 8.5 / 12)
    up_down = plate_z - top if plate_z > top else bottom - plate_z if plate_z < bottom else 0
    return round((across ** 2 + up_down ** 2) ** 0.5 * 12, 1)


def to_row(pitch: dict) -> dict:
    speed, tilt, length = (number(pitch.get(k)) for k in ("bat_speed", "swing_path_tilt", "swing_length"))
    row = {k: (number(pitch.get(k)) if k not in ("pitch_type", "pitch_name", "description", "events",
                                                 "home_team", "away_team") else pitch.get(k) or None)
           for k in KEEP}
    row.update(
        id=f"{pitch['game_pk']}-{pitch['at_bat_number']}-{pitch['pitch_number']}",
        game_date=pitch["game_date"],
        game_type="R",
        game_pk=int(pitch["game_pk"]),
        at_bat_number=int(pitch["at_bat_number"]),
        pitch_number=int(pitch["pitch_number"]),
        batter=int(pitch["batter"]),
        pitcher=int(pitch["pitcher"]),
        perceived_velocity=perceived_velocity(number(pitch.get("release_speed")), number(pitch.get("release_extension"))),
        strike_zone_distance_inches=zone_distance_inches(*(number(pitch.get(k)) for k in ("plate_x", "plate_z", "sz_top", "sz_bot"))),
        sword_score=sword_score(speed, tilt, length),
    )
    return row


def day_pitches(day: str) -> list[dict]:
    query = urllib.parse.urlencode({
        "all": "true", "hfSea": f"{day[:4]}|", "hfGT": "R|", "game_date_gt": day, "game_date_lt": day,
        "type": "details", "player_type": "batter", "min_results": 0,
    })
    text = fetch(f"{SAVANT}/statcast_search/csv?{query}").decode("utf-8-sig")
    if text.lstrip().startswith("<"):
        raise OSError(f"Savant returned a page instead of data for {day}")
    return list(csv.DictReader(io.StringIO(text)))


def read_day(day: str) -> tuple[str, list[dict], dict]:
    pitches = day_pitches(day)
    totals = {"batter": {}, "pitcher": {}}
    for pitch in pitches:
        for side in totals:
            totals[side][pitch[side]] = totals[side].get(pitch[side], 0) + 1
    rows = [to_row(p) for p in pitches if is_sword(p)]
    return day, [r for r in rows if r["sword_score"] >= MIN_PUBLIC_SCORE], totals


def add_game_details(game_pk: int, rows: list[dict]) -> None:
    """Names and MLB's play id come from Savant's game feed."""
    feed = json.loads(fetch(f"{SAVANT}/gf?game_pk={game_pk}"))
    pitches = {(p.get("ab_number"), p.get("pitch_number")): p for side in ("team_home", "team_away") for p in feed.get(side) or []}
    for row in rows:
        found = pitches.get((row["at_bat_number"], row["pitch_number"]))
        if not found:
            continue
        row["play_id"] = found.get("play_id")
        row["batter_name"] = row["player_name"] = found.get("batter_name")
        row["pitcher_name"] = found.get("pitcher_name")


def plain(text: str) -> str:
    return unicodedata.normalize("NFC", text or "").lower()


def last_name(full_name: str) -> str:
    parts = [p for p in plain(full_name).split() if p.rstrip(".") not in ("jr", "sr", "ii", "iii", "iv")]
    return parts[-1] if parts else ""


def existing_clip(row: dict, by_day: dict, base: str) -> str | None:
    """Clips already in Azure are named by date, the pitcher's name, then bat speed or score."""
    if not row.get("pitcher_name"):
        return None
    name = last_name(row["pitcher_name"])
    speed = f"_{row['bat_speed']:.1f}mph.mp4"
    score = round(row["sword_score"])
    for blob in by_day.get(row["game_date"].replace("-", ""), []):
        low = plain(blob)
        if name not in low:
            continue
        if low.endswith(speed) or any(low.endswith(f"_{s}.mp4") for s in (score - 1, score, score + 1)):
            return f"{base}/{urllib.parse.quote(blob)}"
    return None


def blobs_by_day(blobs: list[str]) -> dict:
    out: dict[str, list[str]] = {}
    for blob in blobs:
        parts = blob.split("/")
        if parts[0] in ("swords", "sword_videos") and len(parts) == 3:
            out.setdefault(parts[1].replace("-", ""), []).append(blob)
    return out


def mlb_clip_url(play_id: str) -> str | None:
    page = fetch(f"{SAVANT}/sporty-videos?playId={play_id}").decode("utf-8", "replace")
    found = re.search(r'https://[^"\' ]+\.mp4', page)
    return found.group(0) if found else None


def copy_to_azure(url: str, row: dict, conn: str, base: str) -> str:
    from azure.storage.blob import BlobClient, ContentSettings

    name = f"swords/{row['game_date']}/{row['play_id']}.mp4"
    client = BlobClient.from_connection_string(conn, CONTAINER, name)
    client.upload_blob(fetch(url, timeout=180), overwrite=True, content_settings=ContentSettings(content_type="video/mp4"))
    return f"{base}/{name}"


def needs_clip(row: dict) -> bool:
    return ".blob.core.windows.net/" not in (row.get("video_azure_blob_url") or "")


def fill_clips(rows: list[dict], limit: int, base: str, workers: int) -> int:
    """Newest and nastiest first, so a capped run still fixes what people see."""
    conn = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
    todo = [r for r in rows if r.get("play_id") and needs_clip(r) and (conn or not r.get("video_azure_blob_url"))]
    todo.sort(key=lambda r: (r["game_date"], r["sword_score"]), reverse=True)
    failures = [0]

    def work(row: dict) -> None:
        try:
            url = mlb_clip_url(row["play_id"])
            if not url:
                return
            row["video_azure_blob_url"] = url
            if conn:
                row["video_azure_blob_url"] = copy_to_azure(url, row, conn, base)
        except Exception as exc:  # noqa: BLE001 — one bad clip must not stop the day's data
            failures[0] += 1
            print(f"  clip {row['id']}: {exc}", file=sys.stderr)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(work, todo[:limit]))
    return failures[0]


def load(path: Path, default):
    return json.loads(path.read_text()) if path.exists() else default


def save(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
    tmp.replace(path)


def default_season(today: date) -> int:
    return today.year if (today.month, today.day) >= SEASON_START else today.year - 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=default_season(date.today()))
    ap.add_argument("--days", type=int, default=3)
    ap.add_argument("--backfill", action="store_true")
    ap.add_argument("--clips", type=int, default=150)
    ap.add_argument("--workers", type=int, default=3)
    args = ap.parse_args()

    today = date.today()
    first, last = date(args.season, *SEASON_START), min(date(args.season, *SEASON_END), today - timedelta(days=1))
    start = first if args.backfill else max(first, today - timedelta(days=args.days))
    days = [(start + timedelta(days=i)).isoformat() for i in range((last - start).days + 1)]

    rows_path, totals_path, days_path = DATA / f"{args.season}.json", DATA / f"{args.season}-totals.json", STATE / f"{args.season}-days.json"
    rows = {r["id"]: r for r in load(rows_path, {"rows": []})["rows"]}
    per_day = load(days_path, {})
    errors = 0

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [(d, pool.submit(read_day, d)) for d in days]
        for day, future in futures:
            try:
                _, found, totals = future.result()
            except Exception as exc:  # noqa: BLE001
                errors += 1
                print(f"{day}: {exc}", file=sys.stderr)
                continue
            if found or totals["batter"]:
                print(f"{day}: {sum(totals['batter'].values())} pitches, {len(found)} swords", flush=True)
                per_day[day] = totals
            for row in found:
                rows[row["id"]] = {**rows.get(row["id"], {}), **row}

    games: dict[int, list[dict]] = {}
    for row in rows.values():
        if not row.get("play_id"):
            games.setdefault(row["game_pk"], []).append(row)

    def game_work(item) -> None:
        nonlocal errors
        try:
            add_game_details(*item)
        except Exception as exc:  # noqa: BLE001
            errors += 1
            print(f"game {item[0]}: {exc}", file=sys.stderr)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(game_work, games.items()))

    index = load(AZURE_INDEX, {"base": "", "blobs": []})
    grouped = blobs_by_day(index["blobs"])
    for row in rows.values():
        if needs_clip(row):
            row["video_azure_blob_url"] = existing_clip(row, grouped, index["base"]) or row.get("video_azure_blob_url")
    clip_errors = fill_clips(list(rows.values()), args.clips, index["base"], args.workers)

    ordered = sorted(rows.values(), key=lambda r: (r["game_date"], r["sword_score"]), reverse=True)
    save(rows_path, {"season": args.season, "rows": ordered})
    totals = {"batter": {}, "pitcher": {}}
    for day_totals in per_day.values():
        for side, counts in day_totals.items():
            for player, count in counts.items():
                totals[side][player] = totals[side].get(player, 0) + count
    save(totals_path, totals)
    save(days_path, per_day)
    old_status = load(DATA / "status.json", {})
    if not ordered and old_status.get("swords"):  # the new year hasn't played yet: keep showing the last one
        old_status["checked_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        save(DATA / "status.json", old_status)
        print(f"no {args.season} swords yet; still showing {old_status.get('season')}")
        return 1 if errors else 0
    save(DATA / "status.json", {
        "season": args.season,
        "latest_date": ordered[0]["game_date"] if ordered else None,
        "swords": len(ordered),
        "with_clip": sum(1 for r in ordered if r.get("video_azure_blob_url")),
        "in_azure": sum(1 for r in ordered if not needs_clip(r)),
        "pitches": sum(sum(t["batter"].values()) for t in per_day.values()),
        "errors": errors,
        "clip_errors": clip_errors,
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    print(f"{len(ordered)} swords through {ordered[0]['game_date'] if ordered else 'none'}; {errors} fetch errors, {clip_errors} clip errors")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
