import io
import json
import os
import re
import subprocess
import threading
import time
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Any, Dict, List, Optional

import customtkinter as ctk
from PIL import Image
import requests

from downloader_engine import DownloaderEngine, parse_time_to_seconds
from download_queue import DownloadTask, QueueManager

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

DATA_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "ArgusStudio")
os.makedirs(DATA_DIR, exist_ok=True)
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
LIBRARY_FILE = os.path.join(DATA_DIR, "library.json")

# Migrate existing local files if present
_old_dir = os.path.dirname(os.path.abspath(__file__))
if os.path.exists(os.path.join(_old_dir, "library.json")) and not os.path.exists(LIBRARY_FILE):
    try:
        import shutil
        shutil.copy(os.path.join(_old_dir, "library.json"), LIBRARY_FILE)
    except Exception:
        pass


def load_library() -> List[Dict[str, Any]]:
    if os.path.exists(LIBRARY_FILE):
        try:
            with open(LIBRARY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_library(items: List[Dict[str, Any]]):
    try:
        with open(LIBRARY_FILE, "w", encoding="utf-8") as f:
            json.dump(items, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def load_config() -> Dict[str, Any]:
    default_dir = os.path.join(os.path.expanduser("~"), "Downloads")
    default_cfg = {
        "download_dir": default_dir,
        "default_format": "Video (MP4)",
        "default_quality": "best",
        "auth_mode": "None (Public Videos)",
        "max_concurrent": 2,
        "speed_limit": "Unlimited",
        "clipboard_monitor": True,
        "audio_codec": "mp3",
        "audio_quality": "320",
        "embed_thumbnail": True,
        "embed_metadata": True,
        "download_subtitles": False,
        "subtitle_lang": "en",
        "embed_subtitles": True
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                default_cfg.update(cfg)
        except Exception:
            pass
    return default_cfg


def save_config(cfg: Dict[str, Any]):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass


def get_resource_path(relative_path: str) -> str:
    """Get absolute path to resource, works for dev and PyInstaller."""
    try:
        import sys
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


class ArgusStudioApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Clean, uncluttered title
        self.title("Argus Studio")
        self.geometry("1120x800")
        self.minsize(1020, 720)

        # Official App Icon
        icon_path = get_resource_path("app_icon.ico")
        if os.path.exists(icon_path):
            try:
                self.iconbitmap(icon_path)
            except Exception:
                pass

        # Config & Engine
        self.config_data = load_config()
        self.library_items = load_library()
        self.engine = DownloaderEngine()

        max_workers = int(self.config_data.get("max_concurrent", 2))
        self.queue_mgr = QueueManager(max_concurrent=max_workers)
        self.queue_mgr.on_task_updated = self._on_queue_task_updated
        self.queue_mgr.on_task_completed = self._on_queue_task_completed

        # Current Downloader UI State
        self.current_metadata: Optional[Dict[str, Any]] = None
        self.selected_quality = "best"
        self.selected_format_type = "video"
        self.custom_cookie_path: Optional[str] = None
        self.last_clipboard_text = ""

        # UI Maps
        self.queue_widgets: Dict[str, Dict[str, Any]] = {}

        self._build_layout()
        self._show_tab("downloader")

        # Smart Clipboard Monitor Thread
        if self.config_data.get("clipboard_monitor", True):
            threading.Thread(target=self._clipboard_watcher_loop, daemon=True).start()

    # ================= LAYOUT BUILDER ================= #

    def _build_layout(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # 1. Left Sidebar
        self.sidebar = ctk.CTkFrame(self, width=220, corner_radius=0, fg_color="#12151d")
        self.sidebar.grid(row=0, column=0, sticky="nsew")

        self.brand_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.brand_frame.pack(fill="x", padx=18, pady=(24, 20))

        self.brand_icon = ctk.CTkLabel(self.brand_frame, text="⚡", font=ctk.CTkFont(size=24))
        self.brand_icon.pack(side="left", padx=(0, 8))

        self.brand_title = ctk.CTkLabel(self.brand_frame, text="Argus Studio", font=ctk.CTkFont(size=18, weight="bold"))
        self.brand_title.pack(side="left")

        # Nav Buttons
        self.nav_btns = {}
        nav_items = [
            ("downloader", "📥  Downloader"),
            ("queue", "📋  Queue (0)"),
            ("library", "📁  Library"),
            ("settings", "⚙️  Settings")
        ]

        for key, label in nav_items:
            btn = ctk.CTkButton(
                self.sidebar,
                text=label,
                anchor="w",
                height=42,
                corner_radius=8,
                font=ctk.CTkFont(size=13, weight="bold"),
                fg_color="transparent",
                hover_color="#1e2433",
                command=lambda k=key: self._show_tab(k)
            )
            btn.pack(fill="x", padx=14, pady=4)
            self.nav_btns[key] = btn

        # Sidebar Footer
        self.sidebar_footer = ctk.CTkFrame(self.sidebar, fg_color="#0c0e14", corner_radius=8)
        self.sidebar_footer.pack(side="bottom", fill="x", padx=14, pady=16)

        self.engine_dot = ctk.CTkLabel(
            self.sidebar_footer,
            text=f"● Engine Active ({self.config_data.get('max_concurrent', 2)} slots)",
            font=ctk.CTkFont(size=11),
            text_color="#10b981"
        )
        self.engine_dot.pack(padx=10, pady=8)

        # 2. Main Content Area
        self.main_container = ctk.CTkFrame(self, fg_color="#090a0f", corner_radius=0)
        self.main_container.grid(row=0, column=1, sticky="nsew")
        self.main_container.grid_rowconfigure(2, weight=1)
        self.main_container.grid_columnconfigure(0, weight=1)

        # Top Header Bar
        self.header_frame = ctk.CTkFrame(self.main_container, height=52, fg_color="#0f1118", corner_radius=0)
        self.header_frame.grid(row=0, column=0, sticky="ew")

        self.header_title = ctk.CTkLabel(self.header_frame, text="Media Downloader", font=ctk.CTkFont(size=16, weight="bold"))
        self.header_title.pack(side="left", padx=24, pady=14)

        # Clipboard Auto-Detect Toast Banner (Hidden by default)
        self.clip_banner = ctk.CTkFrame(self.main_container, fg_color="#1e3a8a", corner_radius=8)
        self.clip_banner_label = ctk.CTkLabel(
            self.clip_banner,
            text="📋 Media link detected in clipboard! Click to Load",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#93c5fd"
        )
        self.clip_banner_label.pack(side="left", padx=14, pady=6)

        self.clip_load_btn = ctk.CTkButton(
            self.clip_banner,
            text="Load Link",
            width=80,
            height=26,
            corner_radius=6,
            fg_color="#2563eb",
            hover_color="#1d4ed8",
            command=self._load_detected_clipboard
        )
        self.clip_load_btn.pack(side="right", padx=10, pady=6)

        # View Panels
        self.view_downloader = ctk.CTkScrollableFrame(self.main_container, fg_color="transparent")
        self.view_queue = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.view_library = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.view_settings = ctk.CTkScrollableFrame(self.main_container, fg_color="transparent")

        self._build_downloader_view()
        self._build_queue_view()
        self._build_library_view()
        self._build_settings_view()

    def _show_tab(self, tab_key: str):
        self.view_downloader.grid_forget()
        self.view_queue.grid_forget()
        self.view_library.grid_forget()
        self.view_settings.grid_forget()

        for k, btn in self.nav_btns.items():
            if k == tab_key:
                btn.configure(fg_color="#2563eb", hover_color="#1d4ed8")
            else:
                btn.configure(fg_color="transparent", hover_color="#1e2433")

        if tab_key == "downloader":
            self.header_title.configure(text="Media Downloader")
            self.view_downloader.grid(row=2, column=0, sticky="nsew", padx=20, pady=12)
        elif tab_key == "queue":
            self.header_title.configure(text="Download Queue")
            self.view_queue.grid(row=2, column=0, sticky="nsew", padx=20, pady=12)
            self._render_queue_list()
        elif tab_key == "library":
            self.header_title.configure(text="Media Library")
            self.view_library.grid(row=2, column=0, sticky="nsew", padx=20, pady=12)
            self._refresh_library_ui()
        elif tab_key == "settings":
            self.header_title.configure(text="Settings")
            self.view_settings.grid(row=2, column=0, sticky="nsew", padx=20, pady=12)

    # ================= 1. DOWNLOADER VIEW ================= #

    def _build_downloader_view(self):
        # 1. URL & Quick Actions Card
        input_card = ctk.CTkFrame(self.view_downloader, fg_color="#131722", corner_radius=10)
        input_card.pack(fill="x", pady=(0, 10))

        url_row = ctk.CTkFrame(input_card, fg_color="transparent")
        url_row.pack(fill="x", padx=16, pady=(14, 8))

        self.url_entry = ctk.CTkEntry(
            url_row,
            placeholder_text="Enter YouTube, Vimeo, Playlist, or media URL...",
            height=40,
            corner_radius=8,
            font=ctk.CTkFont(size=13)
        )
        self.url_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkButton(url_row, text="Paste", width=65, height=40, corner_radius=8, fg_color="#1f2937", hover_color="#374151", command=self._paste_url).pack(side="left", padx=(0, 6))
        ctk.CTkButton(url_row, text="📑 Batch URLs", width=105, height=40, corner_radius=8, fg_color="#374151", hover_color="#4b5563", command=self._open_batch_modal).pack(side="left", padx=(0, 6))
        ctk.CTkButton(url_row, text="📂 Playlist", width=90, height=40, corner_radius=8, fg_color="#4f46e5", hover_color="#4338ca", command=self._open_playlist_inspector).pack(side="left", padx=(0, 6))

        self.fetch_btn = ctk.CTkButton(url_row, text="Fetch Media", width=110, height=40, corner_radius=8, font=ctk.CTkFont(weight="bold"), fg_color="#2563eb", hover_color="#1d4ed8", command=self._start_fetch_metadata)
        self.fetch_btn.pack(side="right")

        # Auth & Speed Limit Row
        auth_row = ctk.CTkFrame(input_card, fg_color="transparent")
        auth_row.pack(fill="x", padx=16, pady=(0, 12))

        ctk.CTkLabel(auth_row, text="Session Auth:", font=ctk.CTkFont(size=12, weight="bold"), text_color="gray70").pack(side="left", padx=(0, 8))
        self.cookie_selector = ctk.CTkComboBox(auth_row, values=["None (Public Videos)", "Browser: Chrome", "Browser: Edge", "Browser: Brave", "Browser: Firefox", "Custom cookies.txt File"], height=30, width=190, corner_radius=6, command=self._on_auth_selection_changed)
        self.cookie_selector.set(self.config_data.get("auth_mode", "None (Public Videos)"))
        self.cookie_selector.pack(side="left")

        self.cookie_file_frame = ctk.CTkFrame(auth_row, fg_color="transparent")
        self.cookie_file_entry = ctk.CTkEntry(self.cookie_file_frame, height=30, width=180)
        self.cookie_file_entry.pack(side="left", padx=(8, 4))
        ctk.CTkButton(self.cookie_file_frame, text="Browse", width=60, height=30, command=self._browse_cookie_file).pack(side="left")

        # Speed limit quick selector
        ctk.CTkLabel(auth_row, text="Speed Limit:", font=ctk.CTkFont(size=12, weight="bold"), text_color="gray70").pack(side="left", padx=(20, 8))
        self.speed_combo = ctk.CTkComboBox(auth_row, values=["Unlimited", "1 MB/s", "2 MB/s", "5 MB/s", "10 MB/s"], height=30, width=120)
        self.speed_combo.set(self.config_data.get("speed_limit", "Unlimited"))
        self.speed_combo.pack(side="left")

        # 2. Media Preview Card
        self.preview_card = ctk.CTkFrame(self.view_downloader, fg_color="#131722", corner_radius=10)
        self.preview_card.pack(fill="x", pady=5)

        preview_grid = ctk.CTkFrame(self.preview_card, fg_color="transparent")
        preview_grid.pack(fill="x", padx=16, pady=16)
        preview_grid.grid_columnconfigure(1, weight=1)

        self.thumb_container = ctk.CTkFrame(preview_grid, width=220, height=124, fg_color="#0a0c10", corner_radius=8)
        self.thumb_container.grid(row=0, column=0, rowspan=4, padx=(0, 16), sticky="nw")
        self.thumb_container.pack_propagate(False)

        self.thumb_label = ctk.CTkLabel(self.thumb_container, text="[ No Media Loaded ]", font=ctk.CTkFont(size=12), text_color="gray50")
        self.thumb_label.pack(expand=True)

        self.meta_title = ctk.CTkLabel(preview_grid, text="Paste a URL above and click 'Fetch Media'", font=ctk.CTkFont(size=14, weight="bold"), wraplength=520, justify="left", anchor="w")
        self.meta_title.grid(row=0, column=1, sticky="w", pady=(0, 4))

        self.meta_channel = ctk.CTkLabel(preview_grid, text="Channel / Author: -", font=ctk.CTkFont(size=12), text_color="gray70", anchor="w")
        self.meta_channel.grid(row=1, column=1, sticky="w", pady=2)

        self.meta_stats = ctk.CTkLabel(preview_grid, text="Duration: -  •  Views: -", font=ctk.CTkFont(size=12), text_color="gray70", anchor="w")
        self.meta_stats.grid(row=2, column=1, sticky="w", pady=2)

        # Resolution Pills
        self.pills_container = ctk.CTkFrame(preview_grid, fg_color="transparent")
        self.pills_container.grid(row=3, column=1, sticky="w", pady=(8, 0))

        ctk.CTkLabel(self.pills_container, text="Format / Quality:", font=ctk.CTkFont(size=12, weight="bold"), text_color="gray70").pack(side="left", padx=(0, 8))
        self.pill_buttons: List[ctk.CTkButton] = []
        self._populate_default_pills()

        # 3. Audio & Tagging / Subtitles / Timestamp Clipper Accordion
        advanced_card = ctk.CTkFrame(self.view_downloader, fg_color="#131722", corner_radius=10)
        advanced_card.pack(fill="x", pady=6)

        adv_inner = ctk.CTkFrame(advanced_card, fg_color="transparent")
        adv_inner.pack(fill="x", padx=16, pady=12)

        # Row A: Audio Format & ID3 Tags
        row_a = ctk.CTkFrame(adv_inner, fg_color="transparent")
        row_a.pack(fill="x", pady=4)

        ctk.CTkLabel(row_a, text="🎵 Audio Options:", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left", padx=(0, 10))
        self.audio_codec_combo = ctk.CTkComboBox(row_a, values=["MP3 (320 kbps)", "MP3 (192 kbps)", "M4A (AAC)", "FLAC (Lossless)", "WAV"], width=150, height=28)
        self.audio_codec_combo.set("MP3 (320 kbps)")
        self.audio_codec_combo.pack(side="left", padx=(0, 12))

        self.tag_id3_switch = ctk.CTkCheckBox(row_a, text="Embed Album Art & ID3 Metadata", font=ctk.CTkFont(size=12))
        self.tag_id3_switch.select()
        self.tag_id3_switch.pack(side="left", padx=10)

        # Row B: Subtitles & Closed Captions
        row_b = ctk.CTkFrame(adv_inner, fg_color="transparent")
        row_b.pack(fill="x", pady=6)

        ctk.CTkLabel(row_b, text="💬 Subtitles (CC):", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left", padx=(0, 10))
        self.sub_switch = ctk.CTkCheckBox(row_b, text="Download Subtitles", font=ctk.CTkFont(size=12))
        self.sub_switch.pack(side="left", padx=(0, 12))

        self.sub_lang_combo = ctk.CTkComboBox(row_b, values=["en (English)", "es (Spanish)", "fr (French)", "de (German)", "all (All Available)"], width=140, height=28)
        self.sub_lang_combo.set("en (English)")
        self.sub_lang_combo.pack(side="left", padx=(0, 12))

        self.sub_embed_switch = ctk.CTkCheckBox(row_b, text="Embed into MP4", font=ctk.CTkFont(size=12))
        self.sub_embed_switch.select()
        self.sub_embed_switch.pack(side="left")

        # Row C: Timestamp / Section Clipper
        row_c = ctk.CTkFrame(adv_inner, fg_color="transparent")
        row_c.pack(fill="x", pady=6)

        self.clip_switch = ctk.CTkCheckBox(row_c, text="✂️ Clip Section (Timestamps)", font=ctk.CTkFont(size=12, weight="bold"))
        self.clip_switch.pack(side="left", padx=(0, 12))

        ctk.CTkLabel(row_c, text="Start:", font=ctk.CTkFont(size=11), text_color="gray70").pack(side="left", padx=(4, 4))
        self.clip_start_entry = ctk.CTkEntry(row_c, width=70, height=26, placeholder_text="00:01:30")
        self.clip_start_entry.pack(side="left", padx=(0, 12))

        ctk.CTkLabel(row_c, text="End:", font=ctk.CTkFont(size=11), text_color="gray70").pack(side="left", padx=(4, 4))
        self.clip_end_entry = ctk.CTkEntry(row_c, width=70, height=26, placeholder_text="00:03:45")
        self.clip_end_entry.pack(side="left")

        # 4. Action Bar
        action_card = ctk.CTkFrame(self.view_downloader, fg_color="#131722", corner_radius=10)
        action_card.pack(fill="x", pady=10)

        action_box = ctk.CTkFrame(action_card, fg_color="transparent")
        action_box.pack(fill="x", padx=16, pady=16)

        self.status_line = ctk.CTkLabel(action_box, text="Ready. Fetch media above or add to the background queue.", font=ctk.CTkFont(size=12), text_color="gray70")
        self.status_line.pack(anchor="w", pady=(0, 10))

        btn_row = ctk.CTkFrame(action_box, fg_color="transparent")
        btn_row.pack(fill="x")

        self.add_queue_btn = ctk.CTkButton(
            btn_row,
            text="➕  Add to Download Queue",
            height=44,
            corner_radius=8,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#2563eb",
            hover_color="#1d4ed8",
            command=self._queue_current_media
        )
        self.add_queue_btn.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.quick_download_btn = ctk.CTkButton(
            btn_row,
            text="⬇  Download Now & Open Queue",
            height=44,
            corner_radius=8,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#10b981",
            hover_color="#059669",
            command=lambda: self._queue_current_media(jump_to_queue=True)
        )
        self.quick_download_btn.pack(side="left", fill="x", expand=True)

    # Resolution Pills
    def _populate_default_pills(self):
        for btn in self.pill_buttons:
            btn.destroy()
        self.pill_buttons.clear()

        defaults = [
            ("Best", "best", "video"),
            ("1080p", "1080", "video"),
            ("720p", "720", "video"),
            ("Audio MP3", "best", "audio")
        ]
        for label, q_val, f_type in defaults:
            btn = ctk.CTkButton(
                self.pills_container,
                text=label,
                width=72,
                height=28,
                corner_radius=14,
                font=ctk.CTkFont(size=11, weight="bold"),
                fg_color="#2563eb" if (q_val == self.selected_quality and f_type == self.selected_format_type) else "#1f2937",
                hover_color="#1d4ed8",
                command=lambda q=q_val, f=f_type, l=label: self._select_pill(q, f, l)
            )
            btn.pack(side="left", padx=3)
            self.pill_buttons.append(btn)

    def _populate_dynamic_pills(self, formats: List[Dict[str, Any]]):
        for btn in self.pill_buttons:
            btn.destroy()
        self.pill_buttons.clear()

        heights = sorted(list({f.get("height") for f in formats if f.get("height")}), reverse=True)
        pill_items = [("Auto (Best)", "best", "video")]

        for h in heights[:4]:
            label = f"{h}p"
            if h == 2160:
                label = "4K (2160p)"
            elif h == 1440:
                label = "2K (1440p)"
            pill_items.append((label, str(h), "video"))

        pill_items.append(("Audio MP3", "best", "audio"))

        for label, q_val, f_type in pill_items:
            btn = ctk.CTkButton(
                self.pills_container,
                text=label,
                height=28,
                corner_radius=14,
                font=ctk.CTkFont(size=11, weight="bold"),
                fg_color="#2563eb" if (q_val == self.selected_quality and f_type == self.selected_format_type) else "#1f2937",
                hover_color="#1d4ed8",
                command=lambda q=q_val, f=f_type, l=label: self._select_pill(q, f, l)
            )
            btn.pack(side="left", padx=3)
            self.pill_buttons.append(btn)

    def _select_pill(self, quality: str, format_type: str, label: str):
        self.selected_quality = quality
        self.selected_format_type = format_type
        for btn in self.pill_buttons:
            if btn.cget("text") == label:
                btn.configure(fg_color="#2563eb")
            else:
                btn.configure(fg_color="#1f2937")
        self.status_line.configure(text=f"Selected format: {label}")

    def _paste_url(self):
        try:
            val = self.clipboard_get()
            self.url_entry.delete(0, "end")
            self.url_entry.insert(0, val.strip())
        except Exception:
            pass

    def _on_auth_selection_changed(self, choice: str):
        if "cookies.txt" in choice:
            self.cookie_file_frame.pack(side="left", padx=(8, 0))
        else:
            self.cookie_file_frame.pack_forget()

    def _browse_cookie_file(self):
        fp = filedialog.askopenfilename(title="Select Netscape cookies.txt file", filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if fp:
            self.custom_cookie_path = fp
            self.cookie_file_entry.delete(0, "end")
            self.cookie_file_entry.insert(0, fp)

    def _get_auth_params(self):
        choice = self.cookie_selector.get()
        browser_val = None
        cookie_file = None
        if "None" in choice:
            pass
        elif "cookies.txt" in choice:
            cookie_file = self.cookie_file_entry.get().strip() or self.custom_cookie_path
        elif "Chrome" in choice:
            browser_val = "chrome"
        elif "Edge" in choice:
            browser_val = "edge"
        elif "Brave" in choice:
            browser_val = "brave"
        elif "Firefox" in choice:
            browser_val = "firefox"
        return browser_val, cookie_file

    def _get_rate_limit(self) -> Optional[int]:
        val = self.speed_combo.get()
        if "1 MB" in val:
            return 1 * 1024 * 1024
        elif "2 MB" in val:
            return 2 * 1024 * 1024
        elif "5 MB" in val:
            return 5 * 1024 * 1024
        elif "10 MB" in val:
            return 10 * 1024 * 1024
        return None

    def _get_audio_settings(self):
        raw = self.audio_codec_combo.get().lower()
        if "320" in raw:
            return "mp3", "320"
        elif "192" in raw:
            return "mp3", "192"
        elif "m4a" in raw:
            return "m4a", "192"
        elif "flac" in raw:
            return "flac", "0"
        elif "wav" in raw:
            return "wav", "0"
        return "mp3", "320"

    def _start_fetch_metadata(self):
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning("URL Missing", "Please paste a video or media URL first.")
            return

        browser_val, cookie_file = self._get_auth_params()
        self.fetch_btn.configure(state="disabled", text="Analyzing...")
        self.status_line.configure(text="Extracting metadata & formats...")

        threading.Thread(
            target=self._worker_fetch_metadata,
            args=(url, browser_val, cookie_file),
            daemon=True
        ).start()

    def _worker_fetch_metadata(self, url: str, browser: Optional[str], cookie_file: Optional[str]):
        try:
            metadata = self.engine.extract_metadata(url=url, browser_cookies=browser, cookie_file=cookie_file)
            self.after(0, self._on_metadata_success, metadata)
        except Exception as e:
            self.after(0, self._on_metadata_error, str(e))

    def _on_metadata_success(self, metadata: Dict[str, Any]):
        self.current_metadata = metadata
        self.fetch_btn.configure(state="normal", text="Fetch Media")

        title = metadata.get("title", "Untitled Media")
        uploader = metadata.get("uploader") or metadata.get("channel", "Unknown Creator")
        duration = metadata.get("duration")
        m, s = divmod(duration or 0, 60)
        h, m = divmod(m, 60)
        dur_str = f"{h}:{m:02d}:{s:02d}" if h > 0 else f"{m}:{s:02d}"

        views = metadata.get("view_count")
        view_str = f"{views:,} views" if isinstance(views, int) else "N/A"

        self.meta_title.configure(text=title)
        self.meta_channel.configure(text=f"Author: {uploader}")
        self.meta_stats.configure(text=f"Duration: {dur_str}  •  {view_str}")

        formats = metadata.get("formats", [])
        self._populate_dynamic_pills(formats)
        self.status_line.configure(text="Metadata retrieved! Click 'Add to Queue' or 'Download Now'.")

        thumb_url = metadata.get("thumbnail")
        if thumb_url:
            threading.Thread(target=self._load_thumbnail, args=(thumb_url,), daemon=True).start()

    def _load_thumbnail(self, url: str):
        try:
            resp = requests.get(url, timeout=6)
            if resp.status_code == 200:
                img_data = resp.content
                image = Image.open(io.BytesIO(img_data))
                ctk_img = ctk.CTkImage(light_image=image, dark_image=image, size=(220, 124))
                self.after(0, lambda: self.thumb_label.configure(image=ctk_img, text=""))
        except Exception:
            pass

    def _on_metadata_error(self, err_msg: str):
        self.fetch_btn.configure(state="normal", text="Fetch Media")
        self.status_line.configure(text="Failed to retrieve metadata.")
        messagebox.showerror("Metadata Error", err_msg)

    def _queue_current_media(self, jump_to_queue: bool = False):
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning("URL Missing", "Please enter a valid media URL.")
            return

        title = self.current_metadata.get("title", "Media Download") if self.current_metadata else "Media Download"
        thumb = self.current_metadata.get("thumbnail") if self.current_metadata else None
        output_dir = self.config_data.get("download_dir", os.path.join(os.path.expanduser("~"), "Downloads"))
        browser_val, cookie_file = self._get_auth_params()

        # Advanced options
        codec, a_qual = self._get_audio_settings()
        tag_meta = bool(self.tag_id3_switch.get())
        sub_enabled = bool(self.sub_switch.get())
        sub_lang = self.sub_lang_combo.get().split()[0]
        sub_embed = bool(self.sub_embed_switch.get())
        rate_lim = self._get_rate_limit()

        clip_start = self.clip_start_entry.get().strip() if self.clip_switch.get() else None
        clip_end = self.clip_end_entry.get().strip() if self.clip_switch.get() else None

        task = DownloadTask(
            url=url,
            title=title,
            format_type=self.selected_format_type,
            quality=self.selected_quality,
            audio_codec=codec,
            audio_quality=a_qual,
            embed_thumbnail=tag_meta,
            add_metadata=tag_meta,
            download_subtitles=sub_enabled,
            subtitles_lang=sub_lang,
            embed_subtitles=sub_embed,
            start_time=clip_start,
            end_time=clip_end,
            rate_limit_bytes=rate_lim,
            output_dir=output_dir,
            browser_cookies=browser_val,
            cookie_file=cookie_file,
            thumbnail=thumb
        )
        self.queue_mgr.add_task(task)

        self.status_line.configure(text=f"Added to queue: {title}")
        self._update_queue_badge()

        if jump_to_queue:
            self._show_tab("queue")

    # ================= 2. PLAYLIST INSPECTOR MODAL ================= #

    def _open_playlist_inspector(self):
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning("URL Missing", "Please enter a playlist or channel URL first.")
            return

        modal = ctk.CTkToplevel(self)
        modal.title("Playlist & Channel Inspector")
        modal.geometry("720x560")
        modal.transient(self)
        modal.grab_set()

        head = ctk.CTkFrame(modal, fg_color="transparent")
        head.pack(fill="x", padx=20, pady=(20, 10))

        title_lbl = ctk.CTkLabel(head, text="Fetching playlist entries...", font=ctk.CTkFont(size=14, weight="bold"))
        title_lbl.pack(side="left")

        # Scrollable checklist
        scroll = ctk.CTkScrollableFrame(modal, fg_color="#0c0e14", corner_radius=10)
        scroll.pack(fill="both", expand=True, padx=20, pady=5)

        # Controls bottom
        ctrl = ctk.CTkFrame(modal, fg_color="transparent")
        ctrl.pack(fill="x", padx=20, pady=15)

        format_seg = ctk.CTkSegmentedButton(ctrl, values=["Video (MP4)", "Audio (MP3)"])
        format_seg.set("Video (MP4)")
        format_seg.pack(side="left", padx=(0, 10))

        num_switch = ctk.CTkCheckBox(ctrl, text="Prefix Track # (01, 02...)", font=ctk.CTkFont(size=12))
        num_switch.select()
        num_switch.pack(side="left", padx=10)

        queue_btn = ctk.CTkButton(ctrl, text="Queue Selected (0)", font=ctk.CTkFont(weight="bold"), fg_color="#10b981", hover_color="#059669")
        queue_btn.pack(side="right")

        checkbox_vars = {}

        def _on_fetched(entries: List[Dict[str, Any]]):
            title_lbl.configure(text=f"Found {len(entries)} items in playlist")
            for e in entries:
                var = ctk.BooleanVar(value=True)
                idx = e.get('index', 1)
                t_str = e.get('title', 'Video')
                dur = e.get('duration')
                d_str = f" ({dur//60}:{dur%60:02d})" if dur else ""

                cb = ctk.CTkCheckBox(scroll, text=f"#{idx:02d}  {t_str}{d_str}", variable=var, font=ctk.CTkFont(size=12))
                cb.pack(anchor="w", padx=10, pady=4)
                checkbox_vars[e['url']] = (var, f"{idx:02d} - {t_str}")

            queue_btn.configure(text=f"Queue Selected ({len(entries)})", command=lambda: _do_queue_selected(entries))

        def _do_queue_selected(entries: List[Dict[str, Any]]):
            f_type = "audio" if "Audio" in format_seg.get() else "video"
            output_dir = self.config_data.get("download_dir", os.path.join(os.path.expanduser("~"), "Downloads"))
            browser_val, cookie_file = self._get_auth_params()
            use_prefix = bool(num_switch.get())

            count = 0
            for e in entries:
                var, prefixed_title = checkbox_vars.get(e['url'], (None, None))
                if var and var.get():
                    final_title = prefixed_title if use_prefix else e.get('title', 'Media')
                    task = DownloadTask(
                        url=e['url'],
                        title=final_title,
                        format_type=f_type,
                        quality="best",
                        output_dir=output_dir,
                        browser_cookies=browser_val,
                        cookie_file=cookie_file
                    )
                    self.queue_mgr.add_task(task)
                    count += 1

            modal.destroy()
            self._update_queue_badge()
            self._show_tab("queue")

        def _worker_fetch():
            browser_val, cookie_file = self._get_auth_params()
            try:
                entries = self.engine.extract_playlist_entries(url, browser_cookies=browser_val, cookie_file=cookie_file)
                self.after(0, _on_fetched, entries)
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Playlist Error", str(e), parent=modal))

        threading.Thread(target=_worker_fetch, daemon=True).start()

    # ================= 3. BATCH URL MODAL ================= #

    def _open_batch_modal(self):
        modal = ctk.CTkToplevel(self)
        modal.title("Batch URL Importer")
        modal.geometry("580x480")
        modal.transient(self)
        modal.grab_set()

        ctk.CTkLabel(modal, text="Paste Multiple URLs (One per line)", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=20, pady=(20, 5))

        txt = ctk.CTkTextbox(modal, height=220)
        txt.pack(fill="both", expand=True, padx=20, pady=5)
        txt.insert("0.0", "# Paste video links below:\n")

        opts_frame = ctk.CTkFrame(modal, fg_color="transparent")
        opts_frame.pack(fill="x", padx=20, pady=10)

        ctk.CTkLabel(opts_frame, text="Format:", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left", padx=(0, 8))
        format_seg = ctk.CTkSegmentedButton(opts_frame, values=["Video (MP4)", "Audio (MP3)"])
        format_seg.set("Video (MP4)")
        format_seg.pack(side="left")

        def _do_batch_add():
            raw_text = txt.get("0.0", "end")
            lines = [l.strip() for l in raw_text.splitlines() if l.strip() and not l.strip().startswith("#")]
            if not lines:
                messagebox.showwarning("No URLs", "Please paste at least one valid URL.", parent=modal)
                return

            f_type = "audio" if "Audio" in format_seg.get() else "video"
            output_dir = self.config_data.get("download_dir", os.path.join(os.path.expanduser("~"), "Downloads"))
            browser_val, cookie_file = self._get_auth_params()

            self.queue_mgr.add_batch(
                urls=lines,
                format_type=f_type,
                quality="best",
                output_dir=output_dir,
                browser_cookies=browser_val,
                cookie_file=cookie_file
            )
            modal.destroy()
            self._update_queue_badge()
            self._show_tab("queue")

        ctk.CTkButton(modal, text="Queue All URLs", height=38, font=ctk.CTkFont(weight="bold"), fg_color="#10b981", hover_color="#059669", command=_do_batch_add).pack(fill="x", padx=20, pady=(0, 20))

    # ================= 4. QUEUE VIEW ================= #

    def _build_queue_view(self):
        self.view_queue.grid_columnconfigure(0, weight=1)
        self.view_queue.grid_rowconfigure(1, weight=1)

        bar = ctk.CTkFrame(self.view_queue, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 10))

        self.queue_stats_label = ctk.CTkLabel(bar, text="Queue: 0 tasks", font=ctk.CTkFont(size=13, weight="bold"))
        self.queue_stats_label.pack(side="left")

        ctk.CTkButton(bar, text="Clear Finished", width=120, height=32, fg_color="#1f2937", hover_color="#374151", command=self._clear_finished_queue).pack(side="right")

        self.queue_scroll = ctk.CTkScrollableFrame(self.view_queue, fg_color="#0c0e14", corner_radius=10)
        self.queue_scroll.grid(row=1, column=0, sticky="nsew")

    def _clear_finished_queue(self):
        self.queue_mgr.clear_completed()
        self._render_queue_list()
        self._update_queue_badge()

    def _render_queue_list(self):
        tasks = self.queue_mgr.get_all_tasks()
        active = sum(1 for t in tasks if t.status in ("queued", "downloading"))
        finished = sum(1 for t in tasks if t.status in ("completed", "failed", "canceled"))

        self.queue_stats_label.configure(text=f"Active: {active}  •  Finished: {finished}  •  Total: {len(tasks)}")

        for child in self.queue_scroll.winfo_children():
            child.destroy()
        self.queue_widgets.clear()

        if not tasks:
            empty = ctk.CTkLabel(
                self.queue_scroll,
                text="Download queue is empty.\nAdd single URLs from the Downloader tab, use 'Batch URLs', or 'Playlist'.",
                font=ctk.CTkFont(size=13),
                text_color="gray50",
                justify="center"
            )
            empty.pack(pady=60)
            return

        for task in tasks:
            self._create_task_card(task)

    def _create_task_card(self, task: DownloadTask):
        card = ctk.CTkFrame(self.queue_scroll, fg_color="#131722", corner_radius=8)
        card.pack(fill="x", padx=10, pady=5)

        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(10, 4))

        title_lbl = ctk.CTkLabel(top, text=task.title, font=ctk.CTkFont(size=13, weight="bold"), anchor="w", wraplength=520)
        title_lbl.pack(side="left", fill="x", expand=True)

        fmt_lbl = ctk.CTkLabel(top, text=task.get_badge_text(), font=ctk.CTkFont(size=11, weight="bold"), text_color="#38bdf8")
        fmt_lbl.pack(side="left", padx=8)

        status_lbl = ctk.CTkLabel(top, text=task.status.upper(), font=ctk.CTkFont(size=11, weight="bold"), text_color=self._get_status_color(task.status))
        status_lbl.pack(side="right")

        pbar = ctk.CTkProgressBar(card, height=8, corner_radius=4, progress_color="#10b981")
        pbar.pack(fill="x", padx=14, pady=4)
        pbar.set(task.progress)

        bot = ctk.CTkFrame(card, fg_color="transparent")
        bot.pack(fill="x", padx=14, pady=(2, 10))

        info_lbl = ctk.CTkLabel(bot, text=f"{task.speed}  •  {task.size_info}  •  {task.eta}", font=ctk.CTkFont(size=11), text_color="gray60")
        info_lbl.pack(side="left")

        if task.status in ("queued", "downloading"):
            cancel_btn = ctk.CTkButton(bot, text="✕ Cancel", width=65, height=24, corner_radius=4, fg_color="#374151", hover_color="#4b5563", command=lambda tid=task.id: self._cancel_task(tid))
            cancel_btn.pack(side="right")
        elif task.status == "completed":
            open_btn = ctk.CTkButton(bot, text="▶ Play", width=60, height=24, corner_radius=4, fg_color="#10b981", hover_color="#059669", command=lambda p=task.saved_path: self._play_media(p))
            open_btn.pack(side="right", padx=(4, 0))

        self.queue_widgets[task.id] = {
            "title": title_lbl,
            "status": status_lbl,
            "pbar": pbar,
            "info": info_lbl
        }

    def _get_status_color(self, status: str) -> str:
        if status == "downloading":
            return "#38bdf8"
        elif status == "completed":
            return "#10b981"
        elif status == "failed":
            return "#ef4444"
        elif status == "canceled":
            return "#6b7280"
        return "#f59e0b"

    def _cancel_task(self, task_id: str):
        self.queue_mgr.cancel_task(task_id)

    def _on_queue_task_updated(self, task: DownloadTask):
        self.after(0, self._apply_task_update_to_ui, task)

    def _apply_task_update_to_ui(self, task: DownloadTask):
        self._update_queue_badge()
        w = self.queue_widgets.get(task.id)
        if w:
            w["title"].configure(text=task.title)
            w["status"].configure(text=task.status.upper(), text_color=self._get_status_color(task.status))
            w["pbar"].set(task.progress)
            w["info"].configure(text=f"{task.speed}  •  {task.size_info}  •  {task.eta}")

    def _on_queue_task_completed(self, task: DownloadTask):
        self.after(0, self._record_completed_task_to_library, task)

    def _record_completed_task_to_library(self, task: DownloadTask):
        file_size_str = "Completed"
        if task.saved_path and os.path.exists(task.saved_path):
            sz = os.path.getsize(task.saved_path) / (1024 * 1024)
            file_size_str = f"{sz:.1f} MB"

        entry = {
            "title": task.title,
            "format": task.format_type.upper(),
            "quality": task.quality,
            "size": file_size_str,
            "path": task.saved_path or self.config_data.get("download_dir", ""),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M")
        }
        self.library_items.insert(0, entry)
        save_library(self.library_items)

    def _update_queue_badge(self):
        tasks = self.queue_mgr.get_all_tasks()
        active = sum(1 for t in tasks if t.status in ("queued", "downloading"))
        q_btn = self.nav_btns.get("queue")
        if q_btn:
            q_btn.configure(text=f"📋  Queue ({active})")

    # ================= 5. SMART CLIPBOARD WATCHER ================= #

    def _clipboard_watcher_loop(self):
        video_regex = re.compile(r'(https?://(?:www\.|m\.)?(?:youtube\.com|youtu\.be|vimeo\.com|twitter\.com|x\.com|tiktok\.com|instagram\.com)/\S+)', re.IGNORECASE)
        while True:
            try:
                clip = self.clipboard_get().strip()
                if clip and clip != self.last_clipboard_text:
                    self.last_clipboard_text = clip
                    if video_regex.search(clip):
                        self.after(0, self._show_clipboard_banner, clip)
            except Exception:
                pass
            time.sleep(1.5)

    def _show_clipboard_banner(self, url: str):
        self.clip_banner.grid(row=1, column=0, sticky="ew", padx=20, pady=(6, 0))
        self.detected_url = url

    def _load_detected_clipboard(self):
        if hasattr(self, 'detected_url') and self.detected_url:
            self.url_entry.delete(0, "end")
            self.url_entry.insert(0, self.detected_url)
            self._show_tab("downloader")
            self._start_fetch_metadata()
        self.clip_banner.grid_forget()

    # ================= 6. LIBRARY & PREVIEW ================= #

    def _build_library_view(self):
        self.view_library.grid_columnconfigure(0, weight=1)
        self.view_library.grid_rowconfigure(1, weight=1)

        bar = ctk.CTkFrame(self.view_library, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 10))

        self.lib_count_label = ctk.CTkLabel(bar, text=f"Total Downloads: {len(self.library_items)}", font=ctk.CTkFont(size=13, weight="bold"))
        self.lib_count_label.pack(side="left")

        ctk.CTkButton(bar, text="🗑️ Clear Library", width=120, height=32, fg_color="#dc2626", hover_color="#b91c1c", command=self._clear_library_prompt).pack(side="right", padx=(8, 0))
        ctk.CTkButton(bar, text="📂 Open Download Folder", width=160, height=32, fg_color="#1f2937", hover_color="#374151", command=self._open_downloads_folder).pack(side="right")

        self.lib_scroll = ctk.CTkScrollableFrame(self.view_library, fg_color="#0c0e14", corner_radius=10)
        self.lib_scroll.grid(row=1, column=0, sticky="nsew")

    def _refresh_library_ui(self):
        self.lib_count_label.configure(text=f"Total Downloads: {len(self.library_items)}")

        for child in self.lib_scroll.winfo_children():
            child.destroy()

        if not self.library_items:
            empty = ctk.CTkLabel(self.lib_scroll, text="No downloads yet. Completed items will appear here.", font=ctk.CTkFont(size=13), text_color="gray50")
            empty.pack(pady=40)
            return

        for item in self.library_items:
            card = ctk.CTkFrame(self.lib_scroll, fg_color="#131722", corner_radius=8)
            card.pack(fill="x", padx=10, pady=5)

            info_frame = ctk.CTkFrame(card, fg_color="transparent")
            info_frame.pack(side="left", fill="both", expand=True, padx=14, pady=10)

            title_lbl = ctk.CTkLabel(info_frame, text=item.get("title", "Media File"), font=ctk.CTkFont(size=13, weight="bold"), anchor="w", wraplength=520)
            title_lbl.pack(anchor="w")

            meta_lbl = ctk.CTkLabel(info_frame, text=f"{item.get('format')} • {item.get('size')} • {item.get('timestamp')}", font=ctk.CTkFont(size=11), text_color="gray60", anchor="w")
            meta_lbl.pack(anchor="w", pady=(2, 0))

            action_frame = ctk.CTkFrame(card, fg_color="transparent")
            action_frame.pack(side="right", padx=12, pady=10)

            file_path = item.get("path", "")
            ctk.CTkButton(action_frame, text="▶ Play", width=65, height=30, corner_radius=6, fg_color="#10b981", hover_color="#059669", command=lambda p=file_path: self._play_media(p)).pack(side="left", padx=4)
            ctk.CTkButton(action_frame, text="📂 Show", width=65, height=30, corner_radius=6, fg_color="#1f2937", hover_color="#374151", command=lambda p=file_path: self._show_in_explorer(p)).pack(side="left", padx=4)
            ctk.CTkButton(action_frame, text="✕", width=32, height=30, corner_radius=6, fg_color="#374151", hover_color="#ef4444", command=lambda itm=item: self._delete_library_item(itm)).pack(side="left", padx=(4, 0))

    def _delete_library_item(self, item: Dict[str, Any]):
        title = item.get("title", "this item")
        if messagebox.askyesno("Remove from Library", f"Remove '{title}' from your library history?"):
            if item in self.library_items:
                self.library_items.remove(item)
                save_library(self.library_items)
                self._refresh_library_ui()

    def _clear_library_prompt(self):
        if not self.library_items:
            messagebox.showinfo("Library Empty", "Your library is already empty.")
            return

        confirm = messagebox.askyesno(
            "Clear Library History",
            f"Are you sure you want to clear all {len(self.library_items)} items from your library history?\n\n(Your downloaded media files on disk will NOT be deleted)."
        )
        if confirm:
            self.library_items.clear()
            save_library(self.library_items)
            self._refresh_library_ui()

    def _play_media(self, path: str):
        if path and os.path.exists(path):
            try:
                os.startfile(path)
            except Exception as e:
                messagebox.showerror("Playback Error", f"Unable to open media player:\n{e}")
        else:
            messagebox.showwarning("File Missing", "The file could not be found at its saved location.")

    def _show_in_explorer(self, path: str):
        if path and os.path.exists(path):
            subprocess.run(f'explorer /select,"{os.path.abspath(path)}"')
        else:
            self._open_downloads_folder()

    def _open_downloads_folder(self):
        d = self.config_data.get("download_dir", os.path.join(os.path.expanduser("~"), "Downloads"))
        if os.path.exists(d):
            os.startfile(d)

    # ================= 7. SETTINGS VIEW ================= #

    def _build_settings_view(self):
        card = ctk.CTkFrame(self.view_settings, fg_color="#131722", corner_radius=10)
        card.pack(fill="x", pady=5)

        # Download Directory
        ctk.CTkLabel(card, text="Default Download Location:", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=16, pady=(16, 4))
        dir_row = ctk.CTkFrame(card, fg_color="transparent")
        dir_row.pack(fill="x", padx=16, pady=(0, 16))

        self.cfg_dir_entry = ctk.CTkEntry(dir_row, height=36)
        self.cfg_dir_entry.insert(0, self.config_data.get("download_dir", ""))
        self.cfg_dir_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(dir_row, text="Change...", width=90, height=36, command=self._change_default_dir).pack(side="right")

        # Concurrency & Smart Features
        feat_card = ctk.CTkFrame(self.view_settings, fg_color="#131722", corner_radius=10)
        feat_card.pack(fill="x", pady=10)

        ctk.CTkLabel(feat_card, text="Performance & Smart Automation", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=16, pady=(16, 8))

        row1 = ctk.CTkFrame(feat_card, fg_color="transparent")
        row1.pack(fill="x", padx=16, pady=6)
        ctk.CTkLabel(row1, text="Max Concurrent Downloads:", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left", padx=(0, 12))
        self.conc_combo = ctk.CTkComboBox(row1, values=["1", "2 (Default)", "3", "4", "5"], width=130, command=self._change_concurrency)
        cur_conc = str(self.config_data.get("max_concurrent", 2))
        self.conc_combo.set(cur_conc if cur_conc != "2" else "2 (Default)")
        self.conc_combo.pack(side="left")

        row2 = ctk.CTkFrame(feat_card, fg_color="transparent")
        row2.pack(fill="x", padx=16, pady=(6, 16))
        self.clip_mon_switch = ctk.CTkCheckBox(row2, text="Smart Clipboard Auto-Detector (Pops up when media link copied)", font=ctk.CTkFont(size=12))
        if self.config_data.get("clipboard_monitor", True):
            self.clip_mon_switch.select()
        self.clip_mon_switch.pack(side="left")



    def _change_default_dir(self):
        sel = filedialog.askdirectory(initialdir=self.config_data.get("download_dir", ""))
        if sel:
            self.config_data["download_dir"] = sel
            save_config(self.config_data)
            self.cfg_dir_entry.delete(0, "end")
            self.cfg_dir_entry.insert(0, sel)

    def _change_concurrency(self, val: str):
        num = int(val.split()[0])
        self.config_data["max_concurrent"] = num
        self.queue_mgr.max_concurrent = num
        save_config(self.config_data)
        self.engine_dot.configure(text=f"● Engine Active ({num} slots)")



if __name__ == "__main__":
    app = ArgusStudioApp()
    app.mainloop()
