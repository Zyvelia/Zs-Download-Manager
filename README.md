# NEXUS Download Manager

A desktop transfer manager built with Python, Qt and libtorrent. It supports HTTP(S), torrent files and magnet links in a unified dark neon dashboard.

## Install and run

Python 3.10–3.13 recommended; availability of libtorrent wheels varies by platform and Python version. On Linux, Qt may require the platform's X11/Wayland system libraries. In a terminal in this directory:

```sh
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate
python -m pip install -r requirements.txt
python main.py
```

If a libtorrent wheel is unavailable, install PySide6 alone and run the application for HTTP transfers. Torrent actions will explain that libtorrent is missing. Consult your platform's libtorrent packaging instructions to enable them.

## Using NEXUS

Choose a destination in Settings, then paste an HTTP(S) URL or magnet URI and select **Add transfer**. Use **Open .torrent** for a torrent file. Dashboard shows aggregate rates, active transfers and completed transfers. Downloads and Torrents filter the same list. Each card shows status, progress, rates, transferred bytes, location and controls. Open launches a finished file or torrent directory with the system default application; Folder opens its containing folder. Torrent cancel and remove preserve downloaded data. HTTP cancellation removes its partial file; removing a paused/failed HTTP transfer leaves its partial file on disk.

## How transfers work

HTTP transfers use a Qt worker thread per transfer. Data streams to a `.part` file in the destination; completion uses an atomic hard link to a unique final name so an existing file is never overwritten. Pausing keeps the partial file. Resume uses HTTP Range with a server validator; if the server cannot safely resume, the download restarts from zero. Servers that omit a content length show an indeterminate progress bar. A timeout or network failure appears on the card and can be retried with Resume.

Libtorrent handles peer networking in its own threads, with its state polled by a Qt timer. Each new torrent gets its own uniquely named `Torrent transfer` directory, avoiding collisions with existing files. Torrents can be paused, resumed, canceled or removed; seeding contributes to upload rate. Individual torrent files can be opened through the system file manager.

Settings persist via Qt's platform settings. The transfer list and resume metadata do **not** persist between application launches. Partial HTTP files and torrent data are retained on shutdown, but are not automatically reattached. Torrent data remains in its isolated folder while incomplete, so inspect the card's status before treating it as complete. Cancel/remove does not delete torrent data. The app does not support queue limits, authentication management, HTTP upload, scheduling, bandwidth limits, or automatic cleanup of orphaned partial files. Some filesystems do not support hard links; in that case HTTP completion reports an error and retains the partial file. Shutdown waits for HTTP workers, and can take up to the network timeout for a stalled connection.

## Structure

- `main.py` — application entry point
- `neon/ui.py` — window, dashboard and controls
- `neon/engine.py` — HTTP worker, torrent integration and formatting
- `assets/logo.svg` — original scalable logo and window icon
- `tests/smoke.py` — local HTTP and libtorrent API smoke tests

Run the smoke test from the project directory with `python -m tests.smoke`. It uses a local HTTP server and creates a temporary torrent; it does not test transfers from real torrent peers.

## Build the Windows executable and installer

On 64-bit Windows, install Python 3.12 (including the `py` launcher) and [Inno Setup 6](https://jrsoftware.org/isinfo.php). Internet access is needed to install Python packages. From a Command Prompt in the project folder, run:

```bat
build_windows.bat
```

The script creates a separate `.venv-build`, installs the runtime dependencies and PyInstaller, builds a windowed executable with its required runtime files, then invokes Inno Setup. The portable application folder is `dist\NexusDownloadManager` (keep its files together); the installer is `installer-output\NexusDownloadManager-Setup.exe`. The installer installs per user, adds a Start menu shortcut, and offers an optional desktop shortcut. Both output files are unsigned. This must be built on Windows; PyInstaller does not cross-compile from Linux or macOS. A missing compiler or failed packaging step makes the script return a nonzero exit code.
