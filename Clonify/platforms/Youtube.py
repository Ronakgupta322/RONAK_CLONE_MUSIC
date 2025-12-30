import asyncio
import glob
import json
import os
import random
import re
import requests
import yt_dlp

from typing import Union
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from youtubesearchpython import VideosSearch
from youtubesearchpython.__future__ import CustomSearch

from Clonify import LOGGER
from Clonify.utils.formatters import time_to_seconds
from config import YT_API_KEY, YTPROXY_URL as YTPROXY

logger = LOGGER(__name__)


# ================= COOKIE HANDLER =================
def cookie_txt_file():
    try:
        folder = f"{os.getcwd()}/cookies"
        txt_files = glob.glob(os.path.join(folder, "*.txt"))
        return random.choice(txt_files) if txt_files else None
    except:
        return None


# ================= SHELL =================
async def shell_cmd(cmd):
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    return out.decode() if out else err.decode()


# ================= YOUTUBE API =================
class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.listbase = "https://youtube.com/playlist?list="
        self.regex = r"(youtube\.com|youtu\.be)"

    # ---------- INTERNAL SEARCH ----------
    async def _search(self, query: str, limit=10):
        search = VideosSearch(query, limit=limit)
        data = await search.next()
        results = []

        for r in data.get("result", []):
            dur = r.get("duration")
            if not dur:
                continue

            try:
                sec = time_to_seconds(dur)
                if sec <= 3600:
                    results.append(r)
            except:
                continue

        if results:
            return results[0]

        # fallback
        custom = CustomSearch(query, limit=1)
        res = await custom.next()
        return res["result"][0] if res.get("result") else None

    # ---------- URL DETECT ----------
    async def exists(self, link: str):
        return bool(re.search(self.regex, link))

    # ---------- GET URL FROM MESSAGE ----------
    async def url(self, message: Message):
        msgs = [message, message.reply_to_message] if message.reply_to_message else [message]

        for msg in msgs:
            if not msg:
                continue
            entities = msg.entities or msg.caption_entities
            text = msg.text or msg.caption
            if not entities or not text:
                continue

            for e in entities:
                if e.type == MessageEntityType.URL:
                    return text[e.offset : e.offset + e.length]
                if e.type == MessageEntityType.TEXT_LINK:
                    return e.url
        return None

    # ---------- DETAILS ----------
    async def details(self, link: str):
        result = await self._search(link)
        if not result:
            raise ValueError("No video found")

        return (
            result["title"],
            result["duration"],
            time_to_seconds(result["duration"]),
            result["thumbnails"][0]["url"].split("?")[0],
            result["id"],
        )

    async def title(self, link):
        return (await self.details(link))[0]

    async def duration(self, link):
        return (await self.details(link))[1]

    async def thumbnail(self, link):
        return (await self.details(link))[3]

    # ---------- STREAM URL ----------
    async def video(self, link):
        proc = await asyncio.create_subprocess_exec(
            "yt-dlp",
            "--cookies", cookie_txt_file() or "",
            "-f", "best[height<=720]",
            "-g", link,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await proc.communicate()
        return (1, out.decode().strip()) if out else (0, err.decode())

    # ---------- PLAYLIST ----------
    async def playlist(self, link, limit=10):
        cmd = f"yt-dlp -i --get-id --flat-playlist --playlist-end {limit} {link}"
        data = await shell_cmd(cmd)
        return [i for i in data.split("\n") if i]

    # ---------- AUDIO DOWNLOAD ----------
    async def download_audio(self, vid_id):
        if not YT_API_KEY or not YTPROXY:
            raise ValueError("YT API config missing")

        headers = {"x-api-key": YT_API_KEY}
        filepath = f"downloads/{vid_id}.mp3"

        if os.path.exists(filepath):
            return filepath

        session = requests.Session()
        session.mount("https://", HTTPAdapter(max_retries=Retry(3)))

        r = session.get(f"{YTPROXY}/info/{vid_id}", headers=headers)
        data = r.json()

        if data.get("status") != "success":
            raise ValueError("API error")

        audio_url = data["audio_url"]

        with session.get(audio_url, stream=True) as resp:
            with open(filepath, "wb") as f:
                for chunk in resp.iter_content(1024 * 512):
                    f.write(chunk)

        return filepath
