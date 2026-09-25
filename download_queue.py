import os
import queue
import re
import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

from downloader_engine import DownloaderEngine


class DownloadTask:
    def __init__(
        self,
        url: str,
        title: str = "Media File",
        format_type: str = "video",
        quality: str = "best",
        audio_codec: str = "mp3",
        audio_quality: str = "320",
        embed_thumbnail: bool = True,
        add_metadata: bool = True,
        download_subtitles: bool = False,
        subtitles_lang: str = "en",
        embed_subtitles: bool = True,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        rate_limit_bytes: Optional[int] = None,
        output_dir: str = "",
        browser_cookies: Optional[str] = None,
        cookie_file: Optional[str] = None,
        thumbnail: Optional[str] = None,
    ):
        self.id = str(uuid.uuid4())[:8]
        self.url = url
        self.title = title
        self.format_type = format_type
        self.quality = quality
        self.audio_codec = audio_codec
        self.audio_quality = audio_quality
        self.embed_thumbnail = embed_thumbnail
        self.add_metadata = add_metadata
        self.download_subtitles = download_subtitles
        self.subtitles_lang = subtitles_lang
        self.embed_subtitles = embed_subtitles
        self.start_time = start_time
        self.end_time = end_time
        self.rate_limit_bytes = rate_limit_bytes
        self.output_dir = output_dir
        self.browser_cookies = browser_cookies
        self.cookie_file = cookie_file
        self.thumbnail = thumbnail

        self.status = "queued"  # queued, downloading, completed, failed, canceled
        self.progress = 0.0
        self.speed = "--"
        self.eta = "--:--"
        self.size_info = "0 MB / 0 MB"
        self.error_msg: Optional[str] = None
        self.saved_path: Optional[str] = None
        self.created_at = time.time()

    def get_badge_text(self) -> str:
        if self.format_type == "audio":
            return f"[{self.audio_codec.upper()} {self.audio_quality}k]"
        clip = " [Clip]" if (self.start_time or self.end_time) else ""
        return f"[MP4 {self.quality}{clip}]"


class QueueManager:
    def __init__(self, max_concurrent: int = 2):
        self.engine = DownloaderEngine()
        self.max_concurrent = max_concurrent
        self.tasks: Dict[str, DownloadTask] = {}
        self.task_order: List[str] = []

        self._active_workers = 0
        self._lock = threading.Lock()
        self._is_running = True

        self.on_task_updated: Optional[Callable[[DownloadTask], None]] = None
        self.on_task_completed: Optional[Callable[[DownloadTask], None]] = None

        self._worker_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self._worker_thread.start()

    def add_task(self, task: DownloadTask) -> DownloadTask:
        with self._lock:
            self.tasks[task.id] = task
            self.task_order.append(task.id)

        if self.on_task_updated:
            self.on_task_updated(task)
        return task

    def add_batch(
        self,
        urls: List[str],
        format_type: str = "video",
        quality: str = "best",
        audio_codec: str = "mp3",
        audio_quality: str = "320",
        embed_thumbnail: bool = True,
        add_metadata: bool = True,
        download_subtitles: bool = False,
        subtitles_lang: str = "en",
        output_dir: str = "",
        browser_cookies: Optional[str] = None,
        cookie_file: Optional[str] = None,
    ) -> List[DownloadTask]:
        added = []
        for url in urls:
            u = url.strip()
            if u:
                task = DownloadTask(
                    url=u,
                    title="Analyzing URL...",
                    format_type=format_type,
                    quality=quality,
                    audio_codec=audio_codec,
                    audio_quality=audio_quality,
                    embed_thumbnail=embed_thumbnail,
                    add_metadata=add_metadata,
                    download_subtitles=download_subtitles,
                    subtitles_lang=subtitles_lang,
                    output_dir=output_dir,
                    browser_cookies=browser_cookies,
                    cookie_file=cookie_file,
                )
                self.add_task(task)
                added.append(task)
        return added

    def cancel_task(self, task_id: str):
        with self._lock:
            task = self.tasks.get(task_id)
            if task and task.status in ("queued", "downloading"):
                task.status = "canceled"
                task.error_msg = "Download canceled by user."
                if self.on_task_updated:
                    self.on_task_updated(task)

    def clear_completed(self):
        with self._lock:
            to_remove = [tid for tid, t in self.tasks.items() if t.status in ("completed", "failed", "canceled")]
            for tid in to_remove:
                del self.tasks[tid]
                if tid in self.task_order:
                    self.task_order.remove(tid)

    def get_all_tasks(self) -> List[DownloadTask]:
        with self._lock:
            return [self.tasks[tid] for tid in self.task_order if tid in self.tasks]

    def _scheduler_loop(self):
        while self._is_running:
            task_to_run = None
            with self._lock:
                if self._active_workers < self.max_concurrent:
                    for tid in self.task_order:
                        t = self.tasks.get(tid)
                        if t and t.status == "queued":
                            t.status = "downloading"
                            task_to_run = t
                            self._active_workers += 1
                            break

            if task_to_run:
                threading.Thread(
                    target=self._execute_download,
                    args=(task_to_run,),
                    daemon=True
                ).start()
            else:
                time.sleep(0.3)

    def _execute_download(self, task: DownloadTask):
        if self.on_task_updated:
            self.on_task_updated(task)

        if task.title in ("Media File", "Analyzing URL..."):
            try:
                meta = self.engine.extract_metadata(
                    url=task.url,
                    browser_cookies=task.browser_cookies,
                    cookie_file=task.cookie_file,
                )
                if meta and meta.get("title"):
                    task.title = meta.get("title", task.title)
                    task.thumbnail = meta.get("thumbnail")
                    if self.on_task_updated:
                        self.on_task_updated(task)
            except Exception:
                pass

        if task.status == "canceled":
            with self._lock:
                self._active_workers -= 1
            return

        def task_progress_hook(d: Dict[str, Any]):
            if task.status == "canceled":
                return
            status = d.get("status")
            if status == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                downloaded = d.get("downloaded_bytes") or 0
                ratio = (downloaded / total) if total > 0 else 0.0

                raw_speed = d.get("_speed_str", "0 B/s")
                raw_eta = d.get("_eta_str", "--:--")
                task.speed = re.sub(r'\x1b\[[0-9;]*m', '', raw_speed).strip()
                task.eta = re.sub(r'\x1b\[[0-9;]*m', '', raw_eta).strip()

                tot_mb = total / (1024 * 1024) if total > 0 else 0.0
                dl_mb = downloaded / (1024 * 1024) if downloaded > 0 else 0.0
                percent_str = f"{ratio * 100:.1f}%" if total > 0 else "..."
                task.size_info = f"{dl_mb:.1f} MB / {tot_mb:.1f} MB ({percent_str})"
                task.progress = ratio

                if self.on_task_updated:
                    self.on_task_updated(task)

            elif status == "finished":
                task.progress = 1.0
                task.speed = "Tagging..."
                task.eta = "Finalizing"
                if self.on_task_updated:
                    self.on_task_updated(task)

        try:
            saved_file = self.engine.download_media(
                url=task.url,
                output_dir=task.output_dir,
                format_type=task.format_type,
                quality=task.quality,
                audio_codec=task.audio_codec,
                audio_quality=task.audio_quality,
                embed_thumbnail=task.embed_thumbnail,
                add_metadata=task.add_metadata,
                download_subtitles=task.download_subtitles,
                subtitles_lang=task.subtitles_lang,
                embed_subtitles=task.embed_subtitles,
                start_time=task.start_time,
                end_time=task.end_time,
                rate_limit_bytes=task.rate_limit_bytes,
                browser_cookies=task.browser_cookies,
                cookie_file=task.cookie_file,
                progress_callback=task_progress_hook,
            )
            task.saved_path = saved_file
            task.status = "completed"
            task.progress = 1.0
            task.eta = "Done"
            task.speed = "Complete"

            if self.on_task_updated:
                self.on_task_updated(task)
            if self.on_task_completed:
                self.on_task_completed(task)

        except Exception as e:
            if task.status != "canceled":
                task.status = "failed"
                task.error_msg = str(e)
                if self.on_task_updated:
                    self.on_task_updated(task)
        finally:
            with self._lock:
                self._active_workers -= 1
