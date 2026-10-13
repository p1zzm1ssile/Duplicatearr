"""Finding duplicates, and moving the copies you don't want to the recycle folder.

A scan only reads. It walks the libraries, groups files that are the same film,
episode or picture, reads the copies (cached), checks they really are the same
(identical files, or matching frames and length), and suggests the best copy to
keep. Nothing is moved until someone ticks a copy and presses the button.
"""

import hashlib
import json
import os
import re
import shutil
import threading
import time

import utils.config as config
from core import media, probe
from services.connections import ServiceError, connected
from utils.logger import logger

RESULTS_FILE = os.path.join(config.config_dir, "results.json")

SAME, LIKELY, UNSURE, DIFFERENT, EDITIONS, LENGTHS = "same", "likely", "unsure", "different", "editions", "lengths"
VERDICTS = {
    SAME: "The same video: identical files, or the same frames at the same length.",
    LIKELY: "Very likely the same: the names match and the lengths are within a minute of each other. "
            "Frames weren't compared (turn it on in Settings to be sure).",
    UNSURE: "The names match but the frames couldn't be compared. Check them before removing one.",
    DIFFERENT: "The names match, but the frames don't. They may be different films or a mislabelled file.",
    EDITIONS: "Different editions or cuts (for example theatrical and extended), so probably not duplicates.",
    LENGTHS: "Different lengths, so they may be different cuts. Check them before removing one.",
}
# Copies are only ticked for removal when Duplicatearr is sure they're the same
TICK = {SAME, LIKELY}
HDR_RANK = {"DV": 3, "HDR10": 2, "HLG": 1, "": 0}


class Busy(Exception):
    pass


class Scanner:
    def __init__(self, store):
        self.store = store
        self.lock = threading.Lock()
        self.stop_requested = False
        self.state = {"running": False, "phase": "", "done": 0, "total": 0, "started": None}

    # Running

    def progress(self):
        return dict(self.state)

    def background(self, fn, *args):
        if self.lock.locked():
            raise Busy("A scan or a removal is already running")
        threading.Thread(target=self._run, args=(fn, *args), daemon=True).start()

    def _run(self, fn, *args):
        if not self.lock.acquire(blocking=False):
            return
        try:
            fn(*args)
        except Exception as e:
            logger.error(f"{fn.__name__} stopped: {e}")
        finally:
            self.state.update(running=False, phase="")
            self.lock.release()

    def stop(self):
        self.stop_requested = True

    def results(self):
        try:
            with open(RESULTS_FILE) as f:
                data = json.load(f)
        except (OSError, ValueError):
            return {"scanned_at": None, "groups": []}
        ignored = self.store.ignored()
        for g in data["groups"]:
            g["ignored"] = g["id"] in ignored
        return data

    def _save(self, data):
        os.makedirs(config.config_dir, exist_ok=True)
        tmp = RESULTS_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f)
        os.replace(tmp, RESULTS_FILE)

    # Scanning

    def scan(self):
        self.stop_requested = False
        started = time.time()
        self.state.update(running=True, phase="Looking through your libraries", done=0, total=0, started=started)
        libraries = [l.strip() for l in config.split_labels(config.libraries)]
        missing = [l for l in libraries if not os.path.isdir(l)]
        videos, images = media.walk([l for l in libraries if os.path.isdir(l)], stop=lambda: self.stop_requested)
        if self.stop_requested:
            logger.info("Scan stopped")
            return

        candidates = []
        movies = [f for f in videos if f.kind == "movie"]
        for key, files in media.group_movies(movies).items():
            files = distinct(files)
            if len(files) > 1 and not all_parts(files):
                candidates.append(("movie", key, files[0].title or os.path.basename(files[0].path), files))
        for key, files in media.group_episodes([f for f in videos if f.kind == "episode"]).items():
            files = distinct(files)
            if len(files) > 1:
                candidates.append(("episode", key, f"{files[0].title} {key.rsplit('|', 1)[1]}", files))

        self.state.update(phase="Comparing copies", total=len(candidates))
        tracked = self.tracked_files({
            os.path.relpath(f.path, f.library).split(os.sep)[0].lower()
            for kind, _, _, files in candidates if kind == "episode" for f in files})
        groups = []
        for kind, key, title, files in candidates:
            if self.stop_requested:
                logger.info("Scan stopped")
                return
            groups.append(self.compare(kind, key, title, files, tracked))
            self.state["done"] += 1

        self.state.update(phase="Checking extras")
        groups += self.identical_extras([f for f in videos if f.kind == "extra"])
        if config.check_images:
            self.state.update(phase="Comparing posters and artwork")
            groups += self.duplicate_images(images)

        self.store.forget_missing([f.path for f in videos] + [p for ps in images.values() for p in ps])
        groups.sort(key=lambda g: ({"movie": 0, "episode": 1, "extra": 2, "image": 3}[g["kind"]], g["title"].lower()))
        data = {
            "scanned_at": time.time(), "took": time.time() - started, "files": len(videos), "groups": groups,
            "missing_libraries": missing,
        }
        self._save(data)
        logger.info(f"Scan finished: {len(videos)} videos, {len(groups)} groups of duplicates, "
                    f"{bytes_text(sum(g['reclaimable'] for g in groups))} could be freed")

    def info(self, f):
        """What's in a video, from the cache when the file hasn't changed."""
        try:
            mtime = os.stat(f.path).st_mtime
        except OSError:
            return {"error": "The file has gone"}
        cached = self.store.cached(f.path, f.size, mtime)
        if "duration" in cached or "error" in cached:
            if config.compare_frames and "frames" not in cached and cached.get("duration"):
                cached["frames"] = probe.frame_hashes(f.path, cached["duration"])
                self.store.cache(f.path, f.size, mtime, cached)
            return cached
        info = probe.video_info(f.path)
        if config.compare_frames and info.get("duration"):
            info["frames"] = probe.frame_hashes(f.path, info["duration"])
        self.store.cache(f.path, f.size, mtime, info)
        return info

    def compare(self, kind, key, title, files, tracked):
        infos = [self.info(f) for f in files]
        rows = []
        for f, info in zip(files, infos):
            rows.append({
                "path": f.path, "size": f.size, "library": f.library, "links": f.links, "edition": f.edition,
                "tracked": tracked.get(track_key(f.path), ""), "error": info.get("error", ""),
                "duration": info.get("duration", 0), "width": info.get("width", 0), "height": info.get("height", 0),
                "hdr": info.get("hdr", ""), "codec": info.get("codec", ""), "audio": info.get("audio", ""),
                "audio_profile": info.get("audio_profile", ""), "channels": info.get("channels", 0),
            })

        verdict = self.verdict(files, infos)
        best = max(range(len(rows)), key=lambda i: score(rows[i]))
        tracked_rows = [i for i, r in enumerate(rows) if r["tracked"]]
        keep = tracked_rows[0] if len(tracked_rows) == 1 else best
        note = ""
        if len(tracked_rows) == 1 and keep != best:
            note = (f"{rows[keep]['tracked']} tracks a copy that isn't the best one. Keeping it means it won't "
                    f"download again; to keep the better copy instead, untick it and tick the other one, then "
                    f"import the better copy in {rows[keep]['tracked']} (Wanted > Manual Import).")
        for i, r in enumerate(rows):
            # Only suggest a keeper when they really are copies of one video
            r["suggest"] = ("keep" if i == keep else "remove") if verdict in TICK else ""
        return {
            "id": hashlib.sha1(f"{kind}|{key}".encode()).hexdigest()[:12],
            "kind": kind, "title": title, "verdict": verdict, "verdict_text": VERDICTS[verdict], "note": note,
            "files": rows, "reclaimable": sum(r["size"] for r in rows if r["suggest"] == "remove" and r["links"] < 2),
        }

    def verdict(self, files, infos):
        if all(f.size == files[0].size for f in files):
            try:
                if len({probe.quick_hash(f.path, f.size) for f in files}) == 1:
                    return SAME
            except OSError:
                pass
        if len({f.edition for f in files}) > 1:
            return EDITIONS
        durations = [i.get("duration") or 0 for i in infos]
        if all(durations):
            if max(durations) - min(durations) > max(120, 0.03 * max(durations)):
                return LENGTHS
        if not config.compare_frames or not all(durations):
            return LIKELY if all(durations) and max(durations) - min(durations) <= 60 else UNSURE
        first = infos[0].get("frames")
        results = [probe.same_frames(first, i.get("frames")) for i in infos[1:]]
        if any(r is False for r in results):
            return DIFFERENT
        if all(r is True for r in results):
            return SAME
        return UNSURE

    def identical_extras(self, extras):
        by_hash = {}
        for f in extras:
            try:
                by_hash.setdefault((media_folder(f), f.size, probe.quick_hash(f.path, f.size)), []).append(f)
            except OSError:
                continue
        groups = []
        for (folder, size, _), files in by_hash.items():
            files = distinct(files)
            if len(files) < 2:
                continue
            # Keep the plainest name: "Trailer 1.mkv" over "Trailer 1 (copy).mkv"
            files = sorted(files, key=lambda f: (len(os.path.basename(f.path)), f.path))
            rows = [{"path": f.path, "size": f.size, "library": f.library, "links": f.links, "tracked": "",
                     "suggest": "keep" if i == 0 else "remove"} for i, f in enumerate(files)]
            groups.append({
                "id": hashlib.sha1(f"extra|{'|'.join(r['path'] for r in rows)}".encode()).hexdigest()[:12],
                "kind": "extra", "title": f"Extra in {folder_title(folder)}", "verdict": SAME,
                "verdict_text": "Identical files.", "note": "", "files": rows,
                "reclaimable": sum(r["size"] for r in rows[1:] if r["links"] < 2),
            })
        return groups

    def duplicate_images(self, images):
        groups = []
        for folder, paths in images.items():
            if len(paths) < 2:
                continue
            hashed = []
            for path in sorted(paths):
                try:
                    st = os.stat(path)
                except OSError:
                    continue
                cached = self.store.cached(path, st.st_size, st.st_mtime)
                if "image" not in cached:
                    cached = {"image": probe.image_hash(path)}
                    self.store.cache(path, st.st_size, st.st_mtime, cached)
                if cached["image"]:
                    hashed.append((path, st.st_size, st.st_nlink, *cached["image"]))
            used = set()
            for i, (path, size, links, h, w, ht) in enumerate(hashed):
                if path in used:
                    continue
                same = [(path, size, links, w, ht)]
                for other in hashed[i + 1:]:
                    if other[0] in used:
                        continue
                    ratio_a, ratio_b = w / max(ht, 1), other[4] / max(other[5], 1)
                    if probe.bits_apart(h, other[3]) <= 4 and abs(ratio_a - ratio_b) < 0.05:
                        same.append((other[0], other[1], other[2], other[4], other[5]))
                        used.add(other[0])
                if len(same) < 2:
                    continue
                used.add(path)
                same.sort(key=lambda s: (-s[3] * s[4], s[0]))
                rows = [{"path": p, "size": sz, "library": "", "links": ln, "tracked": "", "width": w, "height": ht,
                         "suggest": "keep" if n == 0 else ""} for n, (p, sz, ln, w, ht) in enumerate(same)]
                groups.append({
                    "id": hashlib.sha1(f"image|{'|'.join(r['path'] for r in rows)}".encode()).hexdigest()[:12],
                    "kind": "image", "title": f"Picture in {folder_title(folder)}", "verdict": SAME,
                    "verdict_text": "The same picture saved more than once.",
                    "note": "Some players look for particular names (poster.jpg, folder.jpg, cover.jpg), so a copy "
                            "under another name may be on purpose. Nothing is ticked: choose what to remove.",
                    "files": rows, "reclaimable": 0,
                })
        return groups

    def tracked_files(self, series_folders=()):
        """{folder/file: "Radarr"} for the files Radarr and Sonarr track, matched on the last two path parts,
        so it works whatever each container calls the folders. Sonarr is only asked about series_folders."""
        tracked = {}
        services = connected(config)
        if "radarr" in services:
            try:
                for movie in services["radarr"].call("GET", "/movie"):
                    path = (movie.get("movieFile") or {}).get("path")
                    if path:
                        tracked[track_key(path)] = "Radarr"
            except ServiceError as e:
                logger.warning(f"Couldn't ask Radarr which files it tracks: {e}")
        if "sonarr" in services:
            try:
                sonarr = services["sonarr"]
                for series in sonarr.call("GET", "/series"):
                    if os.path.basename(series.get("path", "").rstrip("/")).lower() in series_folders:
                        for ef in sonarr.call("GET", f"/episodefile?seriesId={series['id']}"):
                            tracked[track_key(ef.get("path", ""))] = "Sonarr"
            except ServiceError as e:
                logger.warning(f"Couldn't ask Sonarr which files it tracks: {e}")
        return tracked

    # Removing and restoring

    def recycle(self, group_id, paths):
        """Move the chosen copies of one group to the recycle folder. At least one copy always stays."""
        data = self.results()
        group = next((g for g in data["groups"] if g["id"] == group_id), None)
        if not group:
            raise ValueError("That group isn't in the latest scan. Scan again")
        known = {r["path"]: r for r in group["files"]}
        paths = [p for p in dict.fromkeys(paths) if p in known]
        if not paths:
            raise ValueError("Tick at least one copy to remove")
        if len(paths) >= len(known):
            raise ValueError("At least one copy has to stay")
        moved, problems = [], []
        for path in paths:
            try:
                self._recycle_one(path, known[path], group["title"], group["kind"])
                moved.append(path)
            except OSError as e:
                problems.append(f"{os.path.basename(path)}: {e.strerror or e}")
        group["files"] = [r for r in group["files"] if r["path"] not in moved]
        group["reclaimable"] = 0
        if len(group["files"]) < 2:
            data["groups"] = [g for g in data["groups"] if g["id"] != group_id]
        self._save(data)
        if moved and group["kind"] in ("movie", "episode"):
            self.rescan(moved)
        message = f"Moved {len(moved)} cop{'y' if len(moved) == 1 else 'ies'} to the recycle folder"
        if config.recycle_days == 0:
            message = f"Deleted {len(moved)} cop{'y' if len(moved) == 1 else 'ies'}"
        if problems:
            message += ". Couldn't move: " + "; ".join(problems)
        return message

    def _recycle_one(self, path, row, title, kind):
        if not os.path.isfile(path):
            raise OSError(2, "It's no longer there")
        library = row.get("library") or next((l for l in config.split_labels(config.libraries)
                                              if path.startswith(l.rstrip("/") + "/")), os.path.dirname(path))
        sidecars = sidecars_of(path) if kind in ("movie", "episode") else []
        size = os.path.getsize(path)
        if config.recycle_days == 0:
            for p in [path] + sidecars:
                os.remove(p)
            self.store.add_history(path, "", size, title, "deleted", [[s, ""] for s in sidecars])
            logger.log("ACTION", f"Deleted duplicate {path}")
            return
        root = config.recycle_folder or os.path.join(library, media.RECYCLE_NAME)
        batch = os.path.join(root, time.strftime("%Y%m%d-%H%M%S") + f"-{os.getpid() % 1000}")
        moves = []
        for p in [path] + sidecars:
            target = os.path.join(batch, os.path.relpath(p, library) if p.startswith(library) else os.path.basename(p))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.move(p, target)
            moves.append([p, target])
        self.store.add_history(path, moves[0][1], size, title, "recycled", moves[1:])
        logger.log("ACTION", f"Moved duplicate {path} to the recycle folder")

    def restore(self, history_id):
        entry = self.store.entry(history_id)
        if not entry:
            raise ValueError("Not found")
        if entry["state"] != "recycled":
            raise ValueError({"restored": "It's already been restored", "purged": "It's been emptied from the recycle folder",
                              "deleted": "It was deleted straight away (recycle folder set to 0 days)"}.get(entry["state"], "It can't be restored"))
        moves = [[entry["original"], entry["recycled"]]] + entry["sidecars"]
        for original, recycled in moves:
            if os.path.exists(original):
                raise ValueError(f"There's already a file at {original}")
            if not os.path.exists(recycled):
                raise ValueError("It's no longer in the recycle folder")
        for original, recycled in moves:
            os.makedirs(os.path.dirname(original), exist_ok=True)
            shutil.move(recycled, original)
            remove_empty_parents(recycled)
        self.store.set_state(history_id, "restored")
        logger.log("ACTION", f"Restored {entry['original']}")
        self.rescan([entry["original"]])
        return f"Restored {os.path.basename(entry['original'])}. Scan again to see it in its group"

    def purge(self):
        """Empty files that have been in the recycle folder longer than the setting."""
        if config.recycle_days == 0:
            cutoff = time.time()
        else:
            cutoff = time.time() - config.recycle_days * 86400
        for entry in self.store.recycled_before(cutoff):
            for _, recycled in [[entry["original"], entry["recycled"]]] + entry["sidecars"]:
                try:
                    os.remove(recycled)
                    remove_empty_parents(recycled)
                except FileNotFoundError:
                    pass
                except OSError as e:
                    logger.warning(f"Couldn't empty {recycled} from the recycle folder: {e}")
            self.store.set_state(entry["id"], "purged")

    def rescan(self, paths):
        """Ask Radarr or Sonarr to look at the folders again, so they notice a file has gone or come back."""
        services = connected(config)
        folders = {os.path.basename(os.path.dirname(p)).lower() for p in paths}
        series_folders = {p.split("/")[-3].lower() if len(p.split("/")) > 3 else "" for p in paths} | folders
        try:
            if "radarr" in services:
                for movie in services["radarr"].call("GET", "/movie"):
                    if os.path.basename(movie.get("path", "").rstrip("/")).lower() in folders:
                        services["radarr"].call("POST", "/command", {"name": "RescanMovie", "movieId": movie["id"]})
            if "sonarr" in services:
                for series in services["sonarr"].call("GET", "/series"):
                    if os.path.basename(series.get("path", "").rstrip("/")).lower() in series_folders:
                        services["sonarr"].call("POST", "/command", {"name": "RescanSeries", "seriesId": series["id"]})
        except ServiceError as e:
            logger.warning(f"Couldn't ask Radarr or Sonarr to rescan: {e}")


# Helpers


def distinct(files):
    """Leave out extra hardlinks to the same file: they don't take up space twice."""
    seen, out = set(), []
    for f in sorted(files, key=lambda f: f.path):
        if f.inode not in seen:
            seen.add(f.inode)
            out.append(f)
    return out


def all_parts(files):
    """CD1 and CD2 of one film aren't duplicates."""
    parts = [f.part for f in files]
    return all(parts) and len(set(parts)) == len(parts)


def track_key(path):
    parts = path.replace("\\", "/").rstrip("/").split("/")
    return "/".join(parts[-2:]).lower()


def media_folder(f):
    """The film or series folder an extra belongs to."""
    relative = os.path.relpath(f.path, f.library).split(os.sep)
    return os.path.join(f.library, relative[0]) if len(relative) > 1 else f.library


def score(row):
    """Higher is better: resolution, then HDR, then audio channels, then size."""
    return (row.get("height", 0) // 100, HDR_RANK.get(row.get("hdr", ""), 0), row.get("channels", 0), row.get("size", 0))


def sidecars_of(video):
    """Subtitles, .nfo files and thumbnails named after a video, which belong with it."""
    folder, name = os.path.split(video)
    stem = os.path.splitext(name)[0]
    try:
        names = os.listdir(folder)
    except OSError:
        return []
    others = [os.path.splitext(n)[0] for n in names
              if os.path.splitext(n)[1].lower() in media.VIDEO and n != name]
    found = []
    for n in names:
        base, ext = os.path.splitext(n)
        if ext.lower() in media.VIDEO or n == name:
            continue
        if not (n.startswith(stem + ".") or n.startswith(stem + "-")):
            continue
        # Film.2160p.HDR.en.srt belongs to Film.2160p.HDR.mkv, not to Film.2160p.mkv
        if any(len(o) > len(stem) and (n.startswith(o + ".") or n.startswith(o + "-")) for o in others):
            continue
        found.append(os.path.join(folder, n))
    return found


def folder_title(folder):
    """"Dune (2021) {tmdb-438631}" -> "Dune (2021)"."""
    return re.sub(r"\s*[\[{][^\]}]*[\]}]", "", os.path.basename(folder.rstrip("/"))).strip() or folder


def remove_empty_parents(path):
    folder = os.path.dirname(path)
    for _ in range(12):
        if media.RECYCLE_NAME not in folder and not (config.recycle_folder and folder.startswith(config.recycle_folder)):
            return
        try:
            os.rmdir(folder)
        except OSError:
            return
        folder = os.path.dirname(folder)


def bytes_text(n):
    for unit in ("bytes", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "bytes" else f"{n:.1f} {unit}"
        n /= 1024
