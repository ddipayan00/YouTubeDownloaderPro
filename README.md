# YouTube Downloader Pro

A desktop YouTube downloader built with **PySide6 (Qt)** and **yt-dlp**. Download a single
video, or queue a whole playlist and pull several videos down at once — with live per-video
progress, speed and ETA.

![Playlist tab](assets/screenshot-playlist.png)

---

## Features

**Playlist downloads, in parallel**
- Fetch any playlist and see every video in a sortable queue before committing to anything.
- Tick and untick individual videos; download only what you want.
- **You choose how many download at the same time** (1–8). The rest wait in a queue and start
  as slots free up, so a 500-video playlist does not spawn 500 threads.
- Change the parallel limit *while a run is in progress* — it applies to everything still queued.
- One dead or region-blocked video fails on its own row and the rest of the run carries on.
- Optional playlist subfolder, with files numbered in playlist order.

**Single video**
- Fetch info first: thumbnail, title, channel, duration and view count before you download.
- Live progress bar with size, speed and ETA.

**Throughout**
- Cancel cleanly at any point — a whole run, or one video from its right-click menu.
- Dark and light themes.
- Twelve quality presets from 4K down to 144p, plus MP3 and M4A audio extraction.
- Sub-1080p presets prefer **H.264 + AAC**, so the files play on anything. 1440p/4K take the
  best available stream, since YouTube only publishes those as VP9/AV1.
- An activity log you can open when something goes wrong.
- Your folder, quality, theme and parallel limit are remembered between sessions.

| Single video | Light theme |
|---|---|
| ![Single video tab](assets/screenshot-single.png) | ![Light theme](assets/screenshot-light.png) |

---

## Install

Requires **Python 3.10+**.

```bash
git clone https://github.com/ddipayan00/YouTubeDownloaderPro.git
cd YouTubeDownloaderPro

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python run.py
```

### ffmpeg is required

This is not optional in practice. **YouTube now publishes video and audio as separate
streams** — a typical video has *zero* combined formats — so ffmpeg has to merge them.
Without it you are limited to whatever single-file format a video happens to offer, and
most offer none. Audio extraction to MP3 also needs it.

The app finds ffmpeg in either of two places:

1. **On your PATH** — the normal system install:
   ```bash
   sudo apt install ffmpeg        # Debian / Ubuntu
   brew install ffmpeg            # macOS
   winget install Gyan.FFmpeg     # Windows
   ```
2. **In this project's `bin/` folder** — drop `ffmpeg` (and `ffprobe`) there and the app
   picks them up with no system install. This is also what gets bundled into a build.
   `bin/` is gitignored, so the binaries never end up in the repository.

The status bar tells you which state you are in on every launch.

---

## Using it

**A single video** — paste a URL, optionally hit *Fetch info* to confirm it is the right
video, pick a quality and folder, then *Download*.

**A playlist** — paste a playlist URL and hit *Fetch playlist*. Every video appears in the
queue. Untick anything you do not want, set **Parallel downloads**, then *Download selected*.

Right-click any row in the queue to cancel just that video, copy its URL, open it in a
browser, or copy the error if it failed.

### Choosing a parallel limit

3 is a sensible default. Higher is faster on a fast connection, but YouTube will start
throttling or rejecting requests if you push it, and failures cost more time than the extra
parallelism saves. If you see videos failing in bursts, lower it.

### Keyboard shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+D` / `Ctrl+P` | Switch to the Single Video / Playlist tab |
| `Ctrl+L` | Show or hide the activity log |
| `Ctrl+T` | Toggle dark / light theme |
| `Ctrl+Q` | Quit |

### Cancelled downloads

Cancelling leaves yt-dlp's `.part` files in the download folder on purpose — resuming picks
up where it stopped. Delete them by hand if you do not intend to resume.

---

## Building a standalone executable

```bash
pip install pyinstaller
# put ffmpeg (and ffprobe) in bin/ first if you want them bundled
pyinstaller youtube-downloader-pro.spec
```

The result lands in `dist/youtube-downloader-pro/`. Anything in `bin/` is copied in
alongside it, so the build runs on a machine with no Python and no ffmpeg.

---

## Project layout

```
ytdpro/
├── app.py                 Entry point: QApplication setup
├── settings.py            Persisted preferences (QSettings)
├── core/                  No Qt imports — usable from a script or a test
│   ├── engine.py          yt-dlp wrapper: metadata, download, ffmpeg discovery
│   ├── formats.py         Quality presets and their format selectors
│   ├── tasks.py           DownloadTask / Progress / TaskStatus + formatting
│   └── workers.py         QRunnable workers and the parallel DownloadPool
└── ui/
    ├── main_window.py     Shell: header, tabs, activity log, status bar
    ├── single_tab.py      Single video tab
    ├── playlist_tab.py    Playlist tab
    ├── playlist_model.py  Queue table model + progress-bar delegate
    ├── theme.py           Palettes and the generated stylesheet
    └── common.py          Shared widgets (Card, StatRow)
```

**How the threading works.** Every blocking yt-dlp call runs in a `QRunnable` on a
`QThreadPool`; results come back as Qt signals, which are delivered on the GUI thread, so no
widget is ever touched from a worker. The "parallel downloads" spinner is wired straight to
`QThreadPool.setMaxThreadCount()` — submitted work beyond that limit queues instead of
running. Cancellation is a `threading.Event` per task that the yt-dlp progress hook checks
on every callback.

`core/` deliberately imports no Qt, so the download engine can be driven from a plain script:

```python
from pathlib import Path
from ytdpro.core.engine import download, fetch_playlist
from ytdpro.core.formats import preset_by_label

title, tasks = fetch_playlist("https://www.youtube.com/playlist?list=…")
download(tasks[0], Path("~/Downloads").expanduser(), preset_by_label("1080p (Full HD)"))
```

## Tests

```bash
pip install pytest
python -m pytest
```

Covers the pure logic — format selection and its ffmpeg fallback, byte/duration/speed
formatting, task state, error translation and folder-name sanitisation. No network needed.

---

## History

This started life as a college project: a single-file Tkinter GUI over `pytube`
(`ytvd.py`, credited to Aditya Bagad), later reworked into a `ttkbootstrap` app whose
playlist tab never got finished. Version 2 is a ground-up rewrite on Qt, and the playlist
feature is the part that finally landed.

## Legal

For downloading content you have the right to download — your own uploads, Creative Commons
material, or anything the copyright holder permits. Downloading copyrighted video may breach
YouTube's Terms of Service. That is on you.

## License

MIT — see [LICENSE](LICENSE).
