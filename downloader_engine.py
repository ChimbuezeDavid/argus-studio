import os
import re
from typing import Any, Callable, Dict, List, Optional
import yt_dlp
from yt_dlp.utils import download_range_func


def parse_time_to_seconds(time_str: Optional[str]) -> Optional[int]:
    """Parse time string like '01:30' or '01:15:20' or '90' into seconds."""
    if not time_str or not time_str.strip():
        return None
    parts = time_str.strip().split(":")
    try:
        parts = [int(p) for p in parts]
        if len(parts) == 1:
            return parts[0]
        elif len(parts) == 2:
            return parts[0] * 60 + parts[1]
        elif len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
    except Exception:
        return None
    return None


class DownloaderEngine:
    def __init__(self):
        pass

    def _build_ydl_opts(
        self,
        browser_cookies: Optional[str] = None,
        cookie_file: Optional[str] = None,
        base_opts: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        opts = {
            'quiet': True,
            'no_warnings': True,
            'socket_timeout': 20,
            # Windows file locking defense: write directly to target, do not create .part file
            'nopart': True,
            'file_access_retries': 10,
            'windowsfilenames': True,
            # Solve YouTube JS player challenges via Node.js runtime + EJS
            'js_runtimes': {'node': {}},
            'remote_components': {'ejs:github'},
        }
        if base_opts:
            opts.update(base_opts)

        # Cookie configuration
        if cookie_file and os.path.exists(cookie_file):
            opts['cookiefile'] = cookie_file
        elif browser_cookies and browser_cookies.lower() not in ("none", ""):
            opts['cookiesfrombrowser'] = (browser_cookies.lower(),)

        return opts

    def _is_cookie_lock_error(self, e: Exception) -> bool:
        msg = str(e)
        return (
            ("Could not copy" in msg and "cookie" in msg) or
            ("Permission denied" in msg and "Cookies" in msg) or
            ("cookie database" in msg)
        )

    def _handle_exception(self, e: Exception) -> str:
        msg = str(e)
        if self._is_cookie_lock_error(e):
            return (
                "Browser Cookie Database Locked:\n\n"
                "The selected browser is actively running and has locked its cookie database file.\n\n"
                "Solutions:\n"
                "1. If this video is public, change 'Auth / Browser State' to 'None'.\n"
                "2. Completely close your browser (including background tray icons) and try again.\n"
                "3. Alternatively, export your cookies to a 'cookies.txt' file and load it."
            )
        if "WinError 32" in msg or "used by another process" in msg:
            return (
                "Windows File Lock Error [WinError 32]:\n\n"
                "A Windows process held a lock on the file. Direct file writing has been enabled to prevent collisions."
            )
        return msg

    def extract_metadata(
        self,
        url: str,
        browser_cookies: Optional[str] = None,
        cookie_file: Optional[str] = None
    ) -> Dict[str, Any]:
        """Extract metadata without downloading."""
        ydl_opts = self._build_ydl_opts(
            browser_cookies=browser_cookies,
            cookie_file=cookie_file,
            base_opts={
                'skip_download': True,
                'extract_flat': 'in_playlist',
            }
        )

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                raw_info = ydl.extract_info(url, download=False)
                return ydl.sanitize_info(raw_info)
        except Exception as e:
            if browser_cookies and self._is_cookie_lock_error(e):
                try:
                    fallback_opts = self._build_ydl_opts(
                        browser_cookies=None,
                        cookie_file=None,
                        base_opts={
                            'skip_download': True,
                            'extract_flat': 'in_playlist',
                        }
                    )
                    with yt_dlp.YoutubeDL(fallback_opts) as ydl:
                        raw_info = ydl.extract_info(url, download=False)
                        return ydl.sanitize_info(raw_info)
                except Exception:
                    pass

            friendly_err = self._handle_exception(e)
            raise RuntimeError(friendly_err) from e

    def extract_playlist_entries(
        self,
        url: str,
        browser_cookies: Optional[str] = None,
        cookie_file: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Extract flat playlist / channel items for interactive picker."""
        ydl_opts = self._build_ydl_opts(
            browser_cookies=browser_cookies,
            cookie_file=cookie_file,
            base_opts={
                'skip_download': True,
                'extract_flat': True,
            }
        )
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            entries = info.get('entries', [])
            results = []
            for idx, entry in enumerate(entries):
                if entry:
                    entry_url = entry.get('url')
                    if entry_url and not entry_url.startswith('http'):
                        entry_url = f"https://www.youtube.com/watch?v={entry.get('id', '')}"
                    results.append({
                        'index': idx + 1,
                        'id': entry.get('id'),
                        'title': entry.get('title') or f"Video {idx + 1}",
                        'url': entry_url or url,
                        'duration': entry.get('duration'),
                        'uploader': entry.get('uploader') or info.get('uploader') or "Unknown",
                    })
            return results

    def download_media(
        self,
        url: str,
        output_dir: str,
        format_type: str = "video",        # "video" or "audio"
        quality: str = "best",              # "best", "2160", "1440", "1080", "720", "480", "360"
        audio_codec: str = "mp3",           # "mp3", "m4a", "flac", "wav"
        audio_quality: str = "320",         # "320", "192", "0" (lossless)
        embed_thumbnail: bool = True,
        add_metadata: bool = True,
        download_subtitles: bool = False,
        subtitles_lang: str = "en",
        embed_subtitles: bool = True,
        start_time: Optional[str] = None,   # Timestamp clipper "00:01:30"
        end_time: Optional[str] = None,     # Timestamp clipper "00:03:45"
        rate_limit_bytes: Optional[int] = None, # Bandwidth limiter
        browser_cookies: Optional[str] = None,
        cookie_file: Optional[str] = None,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> Optional[str]:
        """Download media with rich options and live progress notifications."""
        downloaded_file: Optional[str] = None

        def yt_progress_hook(d: Dict[str, Any]):
            nonlocal downloaded_file
            if d.get("status") == "finished":
                filename = d.get("filename")
                if filename:
                    downloaded_file = filename
            if progress_callback:
                progress_callback(d)

        def yt_postprocessor_hook(d: Dict[str, Any]):
            nonlocal downloaded_file
            if d.get("status") == "finished":
                info = d.get("info_dict", {})
                fp = info.get("filepath") or d.get("filename")
                if fp:
                    downloaded_file = fp

        base_opts: Dict[str, Any] = {
            'outtmpl': os.path.join(output_dir, '%(title).140s [%(id)s].%(ext)s'),
            'progress_hooks': [yt_progress_hook],
            'postprocessor_hooks': [yt_postprocessor_hook],
            'windowsfilenames': True,
            'nopart': True,
            'file_access_retries': 10,
        }

        # Bandwidth Rate Limiter
        if rate_limit_bytes and rate_limit_bytes > 0:
            base_opts['ratelimit'] = rate_limit_bytes

        # Timestamp / Section Clipping
        s_sec = parse_time_to_seconds(start_time)
        e_sec = parse_time_to_seconds(end_time)
        if s_sec is not None or e_sec is not None:
            s_val = s_sec if s_sec is not None else 0
            e_val = e_sec if e_sec is not None else float('inf')
            base_opts['download_ranges'] = download_range_func(None, [(s_val, e_val)])
            base_opts['force_keyframes_at_cuts'] = True

        # Subtitles configuration
        if download_subtitles:
            base_opts.update({
                'writesubtitles': True,
                'writeautomaticsub': True,
                'subtitleslangs': [subtitles_lang] if subtitles_lang != "all" else ["all"],
            })

        postprocessors = []

        if format_type == "audio":
            base_opts['format'] = 'bestaudio/best'
            # Audio Extraction
            postprocessors.append({
                'key': 'FFmpegExtractAudio',
                'preferredcodec': audio_codec,
                'preferredquality': audio_quality,
            })
            if add_metadata:
                postprocessors.append({'key': 'FFmpegMetadata', 'add_metadata': True})
            if embed_thumbnail and audio_codec in ('mp3', 'm4a'):
                base_opts['writethumbnail'] = True
                postprocessors.append({'key': 'EmbedThumbnail', 'already_have_thumbnail': False})
        else:
            # Video configuration
            if quality == "best":
                base_opts['format'] = 'bestvideo+bestaudio/best'
            else:
                height = re.sub(r'\D', '', quality)
                if height:
                    base_opts['format'] = (
                        f'bestvideo[height<={height}]+bestaudio/best[height<={height}]/best'
                    )
                else:
                    base_opts['format'] = 'bestvideo+bestaudio/best'

            base_opts['merge_output_format'] = 'mp4'

            if add_metadata:
                postprocessors.append({'key': 'FFmpegMetadata', 'add_metadata': True})
            if download_subtitles and embed_subtitles:
                postprocessors.append({'key': 'FFmpegEmbedSubtitle'})

        if postprocessors:
            base_opts['postprocessors'] = postprocessors

        ydl_opts = self._build_ydl_opts(
            browser_cookies=browser_cookies,
            cookie_file=cookie_file,
            base_opts=base_opts
        )

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if not downloaded_file and info:
                    downloaded_file = ydl.prepare_filename(info)
                    if format_type == "audio":
                        base, _ = os.path.splitext(downloaded_file)
                        downloaded_file = f"{base}.{audio_codec}"
                return downloaded_file
        except Exception as e:
            if browser_cookies and self._is_cookie_lock_error(e):
                try:
                    fallback_opts = self._build_ydl_opts(
                        browser_cookies=None,
                        cookie_file=None,
                        base_opts=base_opts
                    )
                    with yt_dlp.YoutubeDL(fallback_opts) as ydl:
                        info = ydl.extract_info(url, download=True)
                        if not downloaded_file and info:
                            downloaded_file = ydl.prepare_filename(info)
                            if format_type == "audio":
                                base, _ = os.path.splitext(downloaded_file)
                                downloaded_file = f"{base}.{audio_codec}"
                        return downloaded_file
                except Exception:
                    pass

            friendly_err = self._handle_exception(e)
            raise RuntimeError(friendly_err) from e
