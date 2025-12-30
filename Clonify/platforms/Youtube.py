import asyncio
import os
import re
import yt_dlp
import requests

from typing import Union
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message

from youtubesearchpython import VideosSearch
from youtubesearchpython.__future__ import CustomSearch

from Clonify import LOGGER
from Clonify.utils.formatters import time_to_seconds

# ===== SAFE CONFIG IMPORT =====
try:
    from config import YT_API_KEY, YTPROXY_URL as YTPROXY
except:
    YT_API_KEY = "xbit_M79PCh3BWqCHuXxDagWV5jfNrZBKjd7p"
    YTPROXY = "https://tgapi.xbitcode.com"

logger = LOGGER(__name__)


# ============================
class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = r"(youtube\.com|youtu\.be)"

    # ---------- URL CHECK ----------
    async def exists(self, link: str):
        return bool(link and re.search(self.regex, link))

    # ---------- GET URL FROM MESSAGE ----------
    async def url(self, message: Message):
        msgs = [message, message.reply_to_message] if message.reply_to_message else [message]

        for msg in msgs:
            if not msg:
                continue
            text = msg.text or msg.caption
            entities = msg.entities or msg.caption_entities
            if not text or not entities:
                continue

            for e in entities:
                if e.type == MessageEntityType.URL:
                    return text[e.offset : e.offset + e.length]
                if e.type == MessageEntityType.TEXT_LINK:
                    return e.url
        return None

    # ---------- SAFE SEARCH ----------
    async def _safe_search(self, query: str):
        if not query:
            return None

        try:
            search = VideosSearch(query, limit=5)
            data = await search.next()
            results = data.get("result", [])

            for r in results:
                dur = r.get("duration")
                if not dur:
                    continue
                try:
                    if time_to_seconds(dur) <= 3600:
                        return r
                except:
                    continue

            # fallback
            custom = CustomSearch(query, limit=1)
            res = await custom.next()
            if res.get("result"):
                return res["result"][0]

        except Exception as e:
            logger.error(f"YouTube search error: {e}")

        return None

    # ---------- DETAILS ----------
    async def details(self, query: str):
        result = await self._safe_search(query)
        if not result:
            raise ValueError("failed to process query")

        return (
            result["title"],
            result.get("duration", "0:00"),
            time_to_seconds(result.get("duration", "0:00")),
            result["thumbnails"][0]["url"].split("?")[0],
            result["id"],
        )

    # ---------- STREAM ----------
    async def video(self, query: str):
        try:
            proc = await asyncio.create_subprocess_exec(
                "yt-dlp",
                "-f", "best[height<=720]",
                "-g", query,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            out, err = await proc.communicate()
            if out:
                return 1, out.decode().strip()
            return 0, err.decode()
        except Exception as e:
            return 0, str(e)

    # ---------- AUDIO DOWNLOAD (OPTIONAL API) ----------
    async def download_audio(self, vid_id):
        if not YT_API_KEY or not YTPROXY:
            raise ValueError("Audio API not configured")

        headers = {"x-api-key": YT_API_KEY}
        path = f"downloads/{vid_id}.mp3"
        os.makedirs("downloads", exist_ok=True)

        if os.path.exists(path):
            return path

        r = requests.get(f"{YTPROXY}/info/{vid_id}", headers=headers, timeout=30)
        data = r.json()

        if data.get("status") != "success":
            raise ValueError("API failed")

        audio_url = data["audio_url"]

        with requests.get(audio_url, stream=True) as resp:
            with open(path, "wb") as f:
                for chunk in resp.iter_content(1024 * 512):
                    f.write(chunk)

        return path
