import os
import shutil
import subprocess

import pytest
from PIL import Image

import utils.config as config
from core import media
from core.scanner import Scanner
from core.store import Store

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")


def video(path, source="testsrc", size="320x240", seconds=12, codec="libx264"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"{source}=size={size}:rate=24",
                    "-f", "lavfi", "-i", "sine=f=440", "-t", str(seconds), "-c:v", codec, "-preset", "ultrafast",
                    "-c:a", "aac", "-ac", "2", path], check=True)


def picture(path, size, colour_shift=0):
    image = Image.new("RGB", (60, 90))
    for x in range(60):
        for y in range(90):
            image.putpixel((x, y), ((x * 4 + colour_shift) % 256, (y * 3) % 256, (x * y) % 256))
    image.resize(size).save(path)


@pytest.fixture(scope="module")
def library(tmp_path_factory):
    root = tmp_path_factory.mktemp("lib")
    movies, tv = str(root / "movies"), str(root / "tv")
    # The same film twice: a bigger copy, and a smaller one in a folder named differently, linked by its .nfo
    video(f"{movies}/Dune (2021) {{tmdb-438631}}/Dune (2021) 2160p.mkv", size="640x480")
    video(f"{movies}/Dune Part One (2021)/Dune.Part.One.2021.1080p.mp4", size="320x240")
    with open(f"{movies}/Dune Part One (2021)/movie.nfo", "w") as f:
        f.write('<movie><uniqueid type="tmdb">438631</uniqueid></movie>')
    with open(f"{movies}/Dune Part One (2021)/Dune.Part.One.2021.1080p.en.srt", "w") as f:
        f.write("1\n00:00:01,000 --> 00:00:02,000\nhi\n")
    # Same name, different picture: a mislabelled file
    video(f"{movies}/Heat (1995)/Heat (1995).mkv", source="testsrc")
    video(f"{movies}/Heat (1995) copy/Heat.1995.mkv", source="mandelbrot")
    # Editions and disc parts aren't duplicates to remove
    video(f"{movies}/Aliens (1986)/Aliens (1986).mkv", seconds=10)
    video(f"{movies}/Aliens (1986)/Aliens (1986) {{edition-Directors Cut}}.mkv", seconds=12)
    video(f"{movies}/Old (1990)/Old cd1.mkv", seconds=4)
    video(f"{movies}/Old (1990)/Old cd2.mkv", source="smptebars", seconds=4)
    # A hardlink is one file, not two
    video(f"{movies}/Solo (2018)/Solo (2018).mkv", seconds=4)
    os.makedirs(f"{movies}/Solo (2018) linked")
    os.link(f"{movies}/Solo (2018)/Solo (2018).mkv", f"{movies}/Solo (2018) linked/Solo (2018).mkv")
    # Identical trailers, and the same poster twice
    video(f"{movies}/Dune (2021) {{tmdb-438631}}/Trailers/Trailer 1.mkv", seconds=3)
    shutil.copy(f"{movies}/Dune (2021) {{tmdb-438631}}/Trailers/Trailer 1.mkv",
                f"{movies}/Dune (2021) {{tmdb-438631}}/Trailers/Trailer 1 (copy).mkv")
    picture(f"{movies}/Dune (2021) {{tmdb-438631}}/poster.jpg", (600, 900))
    picture(f"{movies}/Dune (2021) {{tmdb-438631}}/folder.jpg", (300, 450))
    picture(f"{movies}/Dune (2021) {{tmdb-438631}}/fanart.jpg", (300, 450), colour_shift=128)
    # An episode stored twice
    video(f"{tv}/The Show (2019)/Season 01/The Show - S01E01 - Pilot.mkv", size="640x480")
    video(f"{tv}/The Show (2019)/Season 01/The.Show.S01E01.720p.mp4", size="320x240")
    video(f"{tv}/The Show (2019)/Season 01/The Show - S01E02.mkv", source="mandelbrot", seconds=4)
    return movies, tv


@pytest.fixture
def scanner(library, tmp_path):
    config.update({"libraries": ", ".join(library), "compare_frames": True, "check_images": True, "recycle_days": 7})
    s = Scanner(Store(str(tmp_path / "test.db")))
    s.scan()
    return s


def groups(scanner):
    return {g["title"]: g for g in scanner.results()["groups"]}


def test_finds_the_same_film_in_two_folders(scanner):
    dune = groups(scanner)["Dune (2021)"]
    assert dune["verdict"] == "same"
    keep = [f for f in dune["files"] if f["suggest"] == "keep"]
    assert len(keep) == 1 and keep[0]["height"] == 480  # the bigger copy
    remove = [f for f in dune["files"] if f["suggest"] == "remove"]
    assert len(remove) == 1 and remove[0]["path"].endswith("1080p.mp4")


def test_a_mislabelled_film_is_not_ticked(scanner):
    heat = groups(scanner)["Heat (1995)"]
    assert heat["verdict"] == "different"
    assert all(f["suggest"] == "" for f in heat["files"])


def test_editions_parts_and_hardlinks_are_left_alone(scanner):
    g = groups(scanner)
    assert g["Aliens (1986)"]["verdict"] == "editions"
    assert not [f for f in g["Aliens (1986)"]["files"] if f["suggest"] == "remove"]
    assert "Old (1990)" not in g
    assert "Solo (2018)" not in g


def test_finds_an_episode_stored_twice(scanner):
    episode = groups(scanner)["The Show S01E01"]
    assert episode["kind"] == "episode" and episode["verdict"] == "same"
    assert "The Show S01E02" not in groups(scanner)


def test_identical_extras_and_pictures(scanner):
    g = groups(scanner)
    extra = g["Extra in Dune (2021)"]
    assert len(extra["files"]) == 2
    assert os.path.basename(next(f["path"] for f in extra["files"] if f["suggest"] == "keep")) == "Trailer 1.mkv"
    pictures = g["Picture in Dune (2021)"]
    names = sorted(os.path.basename(f["path"]) for f in pictures["files"])
    assert names == ["folder.jpg", "poster.jpg"]  # not the fanart
    assert not [f for f in pictures["files"] if f["suggest"] == "remove"]


def test_remove_a_copy_and_restore_it(scanner):
    dune = groups(scanner)["Dune (2021)"]
    smaller = next(f["path"] for f in dune["files"] if f["suggest"] == "remove")
    subtitle = smaller.replace(".mp4", ".en.srt")
    with pytest.raises(ValueError, match="At least one copy"):
        scanner.recycle(dune["id"], [f["path"] for f in dune["files"]])

    assert "Moved 1 copy" in scanner.recycle(dune["id"], [smaller])
    assert not os.path.exists(smaller) and not os.path.exists(subtitle)
    assert "Dune (2021)" not in groups(scanner)
    _, history = scanner.store.history()
    assert history[0]["state"] == "recycled" and media.RECYCLE_NAME in history[0]["recycled"]
    assert history[0]["sidecars"][0][0] == subtitle

    scanner.restore(history[0]["id"])
    assert os.path.exists(smaller) and os.path.exists(subtitle)
    assert scanner.store.history()[1][0]["state"] == "restored"


def test_recycled_files_are_emptied_after_the_set_days(scanner, monkeypatch):
    heat = groups(scanner)["Heat (1995)"]
    path = heat["files"][1]["path"]
    scanner.recycle(heat["id"], [path])
    recycled = scanner.store.history()[1][0]["recycled"]
    import time
    monkeypatch.setattr(time, "time", lambda: 10 ** 11)
    scanner.purge()
    assert not os.path.exists(recycled)
    assert scanner.store.history()[1][0]["state"] == "purged"
