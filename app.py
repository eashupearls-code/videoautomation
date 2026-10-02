import io
import os
import re
import subprocess
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
import requests
import streamlit as st
import streamlit.components.v1 as components

# Optional DuckDuckGo import
try:
    from duckduckgo_search import DDGS
except ImportError:
    DDGS = None

# Optional yt-dlp import
try:
    import yt_dlp
except ImportError:
    yt_dlp = None

# Locate FFmpeg
try:
    import imageio_ffmpeg
    FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    FFMPEG_EXE = "ffmpeg"

# =====================================================================
# CONFIGURATION & SECRETS
# =====================================================================
def get_secret(key: str, default: str = "") -> str:
    try:
        if key in st.secrets:
            return str(st.secrets[key]).strip()
    except Exception:
        pass
    return os.environ.get(key, default).strip()


PEXELS_API_KEY = get_secret("PEXELS_API_KEY", "")
PIXABAY_API_KEY = get_secret("PIXABAY_API_KEY", "")
UNSPLASH_ACCESS_KEY = get_secret("UNSPLASH_ACCESS_KEY", "")
YOUTUBE_API_KEY = get_secret("YOUTUBE_API_KEY", "") or get_secret("GOOGLE_API_KEY", "")

OUTPUT_DIR = "downloaded_broll"
os.makedirs(OUTPUT_DIR, exist_ok=True)

MAX_WIKIMEDIA_SIZE_MB = 10.0
UNLIMITED_MEDIA_SIZE_MB = 350.0

GLOBAL_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
GRAMMAR_FILLERS = {"a", "an", "the", "and", "or", "of", "in", "on", "at", "to", "for", "with", "between", "from", "by"}
ARCHIVAL_MODIFIERS = {
    "cinematic", "drone", "4k", "hd", "1080p", "720p", "slow motion", "timelapse",
    "macro", "establishing shot", "b-roll", "footage of", "clip of", "photo of",
    "photograph of", "picture of", "video of", "film of", "shot of", "footage",
    "clip", "video", "hyperrealistic", "close up", "aerial", "vintage"
}

# =====================================================================
# REPOSITORIES & TOOLS
# =====================================================================
TOOLS = {
    "Location & Aerial Video Explorer": {
        "tag": "video_explorer",
        "ext": "mp4",
        "desc": "Search live geo-specific aerials, municipal landmarks, and b-roll footage. Displays videos vertically with custom start & end trim timestamps.",
        "type": "video_explorer",
        "auth_key": None,
        "archival": False
    },
    "Web Open Image Search (Openverse & Web)": {
        "tag": "web_photo_search",
        "ext": "jpg",
        "desc": "Famous for: Open web search across 700M+ images (Flickr, public archives, web hubs). Top 3 preview row with 1-click downloads.",
        "type": "web_explorer",
        "auth_key": None,
        "archival": False
    },
    "Stock Video Footage (Pexels)": {
        "tag": "pexels_video",
        "ext": "mp4",
        "desc": "Famous for: High-bitrate cinematic modern b-roll, drone landscapes, highways, and commercial transitions.",
        "type": "video",
        "auth_key": "PEXELS_API_KEY",
        "archival": False
    },
    "Stock Photos (Pexels)": {
        "tag": "pexels_photo",
        "ext": "jpg",
        "desc": "Famous for: Modern commercial photography, clean studio portraits, architecture, and technology stills.",
        "type": "photo",
        "auth_key": "PEXELS_API_KEY",
        "archival": False
    },
    "Pixabay Video Footage": {
        "tag": "pixabay_video",
        "ext": "mp4",
        "desc": "Famous for: Diverse royalty-free nature scenes, slow motion wildlife, animated motion backgrounds, and time-lapses.",
        "type": "video",
        "auth_key": "PIXABAY_API_KEY",
        "archival": False
    },
    "Pixabay Stock Photos": {
        "tag": "pixabay_photo",
        "ext": "jpg",
        "desc": "Famous for: High-resolution stock illustrations, environmental backgrounds, and commercial editorial stills.",
        "type": "photo",
        "auth_key": "PIXABAY_API_KEY",
        "archival": False
    },
    "Unsplash Editorial Photos": {
        "tag": "unsplash_photo",
        "ext": "jpg",
        "desc": "Famous for: Award-winning artistic lighting, dramatic character portraits, street photography, and editorial framing.",
        "type": "photo",
        "auth_key": "UNSPLASH_ACCESS_KEY",
        "archival": False
    },
    "Wikimedia Commons Stills": {
        "tag": "wikimedia_still",
        "ext": "jpg",
        "desc": "Famous for: World public domain repository: antique cartography maps, scientific diagrams, manuscripts, and artwork (≤ 10MB).",
        "type": "photo",
        "auth_key": None,
        "archival": True
    },
    "Library of Congress (Historic Film & Video)": {
        "tag": "loc_video",
        "ext": "mp4",
        "desc": "Famous for: Authentic early 20th-century motion pictures (1890s–1950s), Edison paper prints, Wright Brothers flights, and WWI/WWII silent footage.",
        "type": "video",
        "auth_key": None,
        "archival": True
    },
    "Library of Congress (Historic Photos)": {
        "tag": "loc_photo",
        "ext": "jpg",
        "desc": "Famous for: Civil War glass negatives (Mathew Brady), Great Depression (Dorothea Lange / FSA), historic architecture (HABS), and vintage maps.",
        "type": "photo",
        "auth_key": None,
        "archival": True
    },
    "National Archives (NARA Historical Footage)": {
        "tag": "nara_video",
        "ext": "mp4",
        "desc": "Famous for: Declassified US military operations (WWII, Korea, Vietnam), NASA Apollo space missions, and historical newsreels.",
        "type": "video",
        "auth_key": None,
        "archival": True
    },
    "National Archives (NARA Historical Stills)": {
        "tag": "nara_photo",
        "ext": "jpg",
        "desc": "Famous for: Official US government records, WWII wartime posters, military photography, Documerica project, and presidential libraries.",
        "type": "photo",
        "auth_key": None,
        "archival": True
    },
    "Visit California Cinematic Video": {
        "tag": "visit_ca_video",
        "ext": "mp4",
        "desc": "Famous for: Official California tourism b-roll: Pacific Coast Highway (PCH), Big Sur, Yosemite, redwoods, surf culture, and Napa Valley.",
        "type": "video",
        "auth_key": None,
        "archival": False
    },
    "Visit California Travel Stills": {
        "tag": "visit_ca_photo",
        "ext": "jpg",
        "desc": "Famous for: High-resolution California destinations, coastal sunsets, national parks, lifestyle, wine country, and urban landmarks.",
        "type": "photo",
        "auth_key": None,
        "archival": False
    },
    "iStock Photo Explorer (Search & Copy URL)": {
        "tag": "istock_search",
        "ext": "jpg",
        "desc": "Search live iStock catalog by prompt, preview top 3 matches in a single row, and copy official URLs with 1-click.",
        "type": "catalog_explorer",
        "source": "istock",
        "auth_key": None,
        "archival": False
    },
    "Shutterstock Photo Explorer (Search & Copy URL)": {
        "tag": "shutterstock_search",
        "ext": "jpg",
        "desc": "Search live Shutterstock catalog by prompt, preview top 3 matches in a single row, and copy official URLs with 1-click.",
        "type": "catalog_explorer",
        "source": "shutterstock",
        "auth_key": None,
        "archival": False
    }
}

# =====================================================================
# OFFICIAL YOUTUBE DATA API SEARCH
# =====================================================================
def search_top3_videos(query: str) -> list[dict]:
    clean_q = query.strip()
    results = []

    # 1. Official YouTube Data API v3
    if YOUTUBE_API_KEY:
        try:
            yt_url = "https://www.googleapis.com/youtube/v3/search"
            params = {
                "key": YOUTUBE_API_KEY,
                "q": f"{clean_q} drone b-roll 4k",
                "part": "snippet",
                "type": "video",
                "maxResults": 3,
                "videoEmbeddable": "true"
            }
            r = requests.get(yt_url, params=params, timeout=10)
            if r.status_code == 200:
                items = r.json().get("items", [])
                for item in items:
                    vid = item.get("id", {}).get("videoId")
                    snippet = item.get("snippet", {})
                    title = snippet.get("title", f"{clean_q} Footage")
                    if vid:
                        results.append({
                            "title": title,
                            "video_id": vid,
                            "watch_url": f"https://www.youtube.com/watch?v={vid}",
                            "thumb_url": snippet.get("thumbnails", {}).get("high", {}).get("url", f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg")
                        })
                if len(results) == 3:
                    return results
        except Exception:
            pass

    # 2. Public Invidious Mirrors fallback
    try:
        invidious_instances = [
            "https://inv.tux.pizza/api/v1/search",
            "https://invidious.nerdvpn.de/api/v1/search",
            "https://vid.priv.au/api/v1/search"
        ]
        for inst in invidious_instances:
            try:
                r_inv = requests.get(inst, params={"q": f"{clean_q} drone 4k", "type": "video"}, timeout=5)
                if r_inv.status_code == 200:
                    hits = r_inv.json()
                    for v in hits:
                        vid = v.get("videoId")
                        if vid:
                            results.append({
                                "title": v.get("title", f"{clean_q} Video"),
                                "video_id": vid,
                                "watch_url": f"https://www.youtube.com/watch?v={vid}",
                                "thumb_url": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
                            })
                        if len(results) == 3:
                            break
                    if len(results) == 3:
                        return results
            except Exception:
                continue
    except Exception:
        pass

    return results

# =====================================================================
# CLOUD-HARDENED VIDEO TRIMMER (TIMESTAMPS: START TO END)
# =====================================================================
def trim_youtube_clip(watch_url: str, output_path: str, start_sec: int, end_sec: int) -> tuple[bool, str]:
    duration = max(1, end_sec - start_sec)
    
    # Method 1: yt-dlp Python API with client impersonation and section download
    if yt_dlp is not None:
        try:
            ydl_opts = {
                "format": "best[ext=mp4]/best",
                "outtmpl": output_path,
                "overwrites": True,
                "quiet": True,
                "no_warnings": True,
                "download_ranges": yt_dlp.utils.download_range_func(None, [(start_sec, end_sec)]),
                "force_keyframes_at_cuts": True,
                "extractor_args": {
                    "youtube": {
                        "player_client": ["android", "ios", "web"]
                    }
                }
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([watch_url])
            
            if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
                mb = os.path.getsize(output_path) / (1024 * 1024)
                return True, f"{mb:.1f} MB ({duration}s slice)"
        except Exception:
            pass

    # Method 2: Direct stream extraction + FFmpeg time seek
    if yt_dlp is not None:
        try:
            ydl_stream_opts = {
                "format": "best[ext=mp4]/best",
                "quiet": True,
                "extractor_args": {"youtube": {"player_client": ["android", "ios"]}}
            }
            with yt_dlp.YoutubeDL(ydl_stream_opts) as ydl:
                info = ydl.extract_info(watch_url, download=False)
                stream_url = info.get("url")
                
            if stream_url:
                cmd = [
                    FFMPEG_EXE, "-y",
                    "-ss", str(start_sec),
                    "-i", stream_url,
                    "-t", str(duration),
                    "-c:v", "libx264",
                    "-preset", "ultrafast",
                    "-c:a", "aac",
                    "-movflags", "+faststart",
                    output_path
                ]
                subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45)
                if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
                    mb = os.path.getsize(output_path) / (1024 * 1024)
                    return True, f"{mb:.1f} MB ({duration}s slice)"
        except Exception:
            pass

    # Method 3: Subprocess fallback
    cmd_cli = [
        "yt-dlp",
        "--force-overwrites",
        "--extractor-args", "youtube:player_client=android,ios,web",
        "--download-sections", f"*{start_sec}-{end_sec}",
        "-f", "best[ext=mp4]/best",
        "-o", output_path,
        watch_url
    ]
    try:
        subprocess.run(cmd_cli, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=50)
        if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            mb = os.path.getsize(output_path) / (1024 * 1024)
            return True, f"{mb:.1f} MB ({duration}s slice)"
    except Exception as e:
        return False, str(e)

    return False, "Could not slice stream. Datacenter block or video is restricted."

# =====================================================================
# LIVE IMAGE SEARCH HELPERS
# =====================================================================
def download_image_buffer(url: str, referer: str = "https://www.google.com/") -> bytes | None:
    headers = {
        "User-Agent": GLOBAL_USER_AGENT,
        "Referer": referer,
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8"
    }
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200 and len(r.content) > 1000:
            return r.content
    except Exception:
        pass
    return None


def search_web_open_top3(query: str) -> list[dict]:
    clean_q = requests.utils.quote(query.strip())
    results = []

    # 1. Openverse API
    openverse_url = f"https://api.openverse.org/v1/images/?q={clean_q}&page_size=5"
    headers_ov = {"User-Agent": "BrollStudioArchive/4.0 (contact@brollstudio.org)"}
    try:
        r = requests.get(openverse_url, headers=headers_ov, timeout=10)
        if r.status_code == 200:
            hits = r.json().get("results", [])
            for item in hits:
                img_url = item.get("url")
                if not img_url:
                    continue
                img_data = download_image_buffer(img_url)
                if img_data:
                    results.append({
                        "title": item.get("title") or "Web B-roll Image",
                        "image_bytes": img_data,
                        "source_url": item.get("foreign_landing_url") or img_url
                    })
                if len(results) == 3:
                    break
    except Exception:
        pass

    # 2. DuckDuckGo fallback
    if len(results) < 3 and DDGS is not None:
        try:
            with DDGS() as ddgs:
                ddg_hits = list(ddgs.images(query.strip(), max_results=6))
                for item in ddg_hits:
                    img_url = item.get("image") or item.get("thumbnail")
                    if not img_url:
                        continue
                    img_data = download_image_buffer(img_url, referer="https://duckduckgo.com/")
                    if img_data:
                        results.append({
                            "title": item.get("title") or "Web B-roll Image",
                            "image_bytes": img_data,
                            "source_url": item.get("url") or img_url
                        })
                    if len(results) == 3:
                        break
        except Exception:
            pass

    return results


def search_istock_top3(query: str) -> list[dict]:
    clean_q = requests.utils.quote(query.strip())
    url = f"https://www.istockphoto.com/search/2/image?phrase={clean_q}&sort=mostpopular"
    headers = {
        "User-Agent": GLOBAL_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9"
    }
    results = []
    try:
        r = requests.get(url, headers=headers, timeout=12)
        if r.status_code == 200:
            matches = re.findall(
                r'href="(/photo/[^"]+)"[^>]*>.*?<img[^>]+src="([^">]+)"[^>]*alt="([^"]*)"',
                r.text,
                re.DOTALL
            )
            for page_path, thumb_url, alt_text in matches:
                full_page_url = f"https://www.istockphoto.com{page_path}" if not page_path.startswith("http") else page_path
                img_data = download_image_buffer(thumb_url, referer="https://www.istockphoto.com/")
                if img_data:
                    results.append({
                        "title": alt_text.strip() or "iStock Photo",
                        "image_bytes": img_data,
                        "target_url": full_page_url
                    })
                if len(results) == 3:
                    break
    except Exception:
        pass

    return results


def search_shutterstock_top3(query: str) -> list[dict]:
    clean_q = requests.utils.quote(query.strip())
    results = []
    api_url = f"https://www.shutterstock.com/_next/data/en/search/{clean_q}.json?term={clean_q}"
    headers_api = {
        "User-Agent": GLOBAL_USER_AGENT,
        "Accept": "application/json",
        "Referer": f"https://www.shutterstock.com/search/{clean_q}"
    }
    try:
        r = requests.get(api_url, headers=headers_api, timeout=10)
        if r.status_code == 200:
            data = r.json()
            assets = data.get("pageProps", {}).get("initialState", {}).get("search", {}).get("results", {}).get("data", [])
            for item in assets:
                img_id = item.get("id")
                desc = item.get("description", "Shutterstock Photo")
                displays = item.get("displays", {})
                thumb_url = displays.get("260nw", {}).get("src") or displays.get("preview", {}).get("src")
                if img_id and thumb_url:
                    full_page_url = f"https://www.shutterstock.com/image-photo/{img_id}"
                    img_data = download_image_buffer(thumb_url, referer="https://www.shutterstock.com/")
                    if img_data:
                        results.append({
                            "title": desc,
                            "image_bytes": img_data,
                            "target_url": full_page_url
                        })
                if len(results) == 3:
                    break
    except Exception:
        pass

    return results

# =====================================================================
# QUERY ENGINE & SANITIZATION
# =====================================================================
def prompt_to_clean_filename(prompt: str, ext: str, max_chars: int = 50) -> str:
    clean = re.sub(r'[\\/*?:"<>|]', "", prompt)
    clean = re.sub(r"[^\w\s-]", "", clean).strip()
    clean = re.sub(r"[\s-]+", "_", clean).lower()
    base_name = clean[:max_chars].strip("_") or "scene_asset"

    candidate = f"{base_name}.{ext}"
    full_path = os.path.join(OUTPUT_DIR, candidate)

    counter = 1
    while os.path.exists(full_path):
        candidate = f"{base_name}_{counter}.{ext}"
        full_path = os.path.join(OUTPUT_DIR, candidate)
        counter += 1

    return candidate


def get_search_queries(raw_prompt: str, is_archival: bool = False) -> list[str]:
    clean = re.sub(r"[^\w\s-]", " ", raw_prompt).strip()
    clean = re.sub(r"\s+", " ", clean)
    queries = [clean]

    words = [w for w in clean.split() if w.lower() not in GRAMMAR_FILLERS]
    keyword_q = " ".join(words)
    if keyword_q and keyword_q != clean:
        queries.append(keyword_q)

    archival_words = [w for w in words if w.lower() not in ARCHIVAL_MODIFIERS]
    archival_q = " ".join(archival_words)
    if archival_q and archival_q not in queries:
        queries.append(archival_q)

    if is_archival and archival_q:
        queries.remove(archival_q)
        queries.insert(0, archival_q)

    return queries


def download_stream(url: str, output_path: str, max_size_mb: float = UNLIMITED_MEDIA_SIZE_MB) -> tuple[bool, str]:
    headers = {"User-Agent": GLOBAL_USER_AGENT}
    try:
        with requests.get(url, headers=headers, stream=True, timeout=30) as r:
            r.raise_for_status()
            total_bytes = int(r.headers.get("content-length", 0))
            total_mb = total_bytes / (1024 * 1024) if total_bytes else 0

            if max_size_mb and total_mb > max_size_mb:
                return False, f"Exceeded size limit ({total_mb:.1f} MB > {max_size_mb:.0f} MB)"

            with open(output_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=131072):
                    if chunk:
                        f.write(chunk)

            final_mb = os.path.getsize(output_path) / (1024 * 1024)
            return True, f"{final_mb:.1f} MB"
    except Exception as e:
        if os.path.exists(output_path):
            os.remove(output_path)
        return False, str(e)


def trim_video_stream(cdn_url: str, output_path: str, duration_sec: int) -> tuple[bool, str]:
    cmd = [
        FFMPEG_EXE, "-y",
        "-user_agent", GLOBAL_USER_AGENT,
        "-ss", "00:00:00",
        "-i", cdn_url,
        "-t", str(duration_sec),
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-crf", "22",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        output_path
    ]
    try:
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            sz_mb = os.path.getsize(output_path) / (1024 * 1024)
            return True, f"{sz_mb:.1f} MB ({duration_sec}s clip)"
    except Exception:
        pass

    return False, "Could not slice video."


# =====================================================================
# BATCH REPOSITORIES (PEXELS, PIXABAY, LOC, NARA, ETC.)
# =====================================================================
def fetch_pexels_video(query: str, out_path: str, quality_choice: str = "", clip_seconds: int | None = None) -> tuple[bool, str, str | None]:
    if not PEXELS_API_KEY:
        return False, "PEXELS_API_KEY missing from secrets", None
    url = "https://api.pexels.com/videos/search"
    headers = {"Authorization": PEXELS_API_KEY}
    params = {"query": query, "orientation": "landscape", "per_page": 6}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=12)
        videos = r.json().get("videos", [])
        if not videos:
            return False, "No matching clips found", None

        files = [f for f in videos[0].get("video_files", []) if f.get("link")]
        files.sort(key=lambda x: (x.get("height") or 0), reverse=True)
        chosen = files[0]
        cdn_url = chosen["link"]
        if clip_seconds:
            ok, msg = trim_video_stream(cdn_url, out_path, clip_seconds)
        else:
            ok, msg = download_stream(cdn_url, out_path, max_size_mb=UNLIMITED_MEDIA_SIZE_MB)
        return ok, msg, cdn_url
    except Exception as e:
        return False, str(e), None


def fetch_pixabay_video(query: str, out_path: str, quality_choice: str = "", clip_seconds: int | None = None) -> tuple[bool, str, str | None]:
    if not PIXABAY_API_KEY:
        return False, "PIXABAY_API_KEY missing from secrets", None
    url = "https://pixabay.com/api/videos/"
    params = {"key": PIXABAY_API_KEY, "q": query, "per_page": 6}
    try:
        r = requests.get(url, params=params, timeout=12)
        hits = r.json().get("hits", [])
        if not hits:
            return False, "No clips found", None

        streams = hits[0].get("videos", {})
        chosen = streams.get("large") or streams.get("medium") or streams.get("small")
        if not chosen or not chosen.get("url"):
            return False, "No downloadable stream found", None

        cdn_url = chosen["url"]
        if clip_seconds:
            ok, msg = trim_video_stream(cdn_url, out_path, clip_seconds)
        else:
            ok, msg = download_stream(cdn_url, out_path, max_size_mb=UNLIMITED_MEDIA_SIZE_MB)
        return ok, msg, cdn_url
    except Exception as e:
        return False, str(e), None


def fetch_pexels_photo(query: str, out_path: str, _q: str = "", _c: int | None = None) -> tuple[bool, str, str | None]:
    if not PEXELS_API_KEY:
        return False, "PEXELS_API_KEY missing from secrets", None
    url = "https://api.pexels.com/v1/search"
    headers = {"Authorization": PEXELS_API_KEY}
    params = {"query": query, "orientation": "landscape", "per_page": 5}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=12)
        photos = r.json().get("photos", [])
        if not photos:
            return False, "No photos found", None
        img_url = photos[0].get("src", {}).get("large2x") or photos[0].get("src", {}).get("large")
        ok, msg = download_stream(img_url, out_path, max_size_mb=UNLIMITED_MEDIA_SIZE_MB)
        return ok, msg, img_url
    except Exception as e:
        return False, str(e), None


def fetch_pixabay_photo(query: str, out_path: str, _q: str = "", _c: int | None = None) -> tuple[bool, str, str | None]:
    if not PIXABAY_API_KEY:
        return False, "PIXABAY_API_KEY missing from secrets", None
    url = "https://pixabay.com/api/"
    params = {"key": PIXABAY_API_KEY, "q": query, "image_type": "photo", "orientation": "horizontal", "per_page": 5}
    try:
        r = requests.get(url, params=params, timeout=12)
        hits = r.json().get("hits", [])
        if not hits:
            return False, "No photos found", None
        img_url = hits[0].get("largeImageURL") or hits[0].get("imageURL")
        ok, msg = download_stream(img_url, out_path, max_size_mb=UNLIMITED_MEDIA_SIZE_MB)
        return ok, msg, img_url
    except Exception as e:
        return False, str(e), None


def fetch_unsplash_photo(query: str, out_path: str, _q: str = "", _c: int | None = None) -> tuple[bool, str, str | None]:
    if not UNSPLASH_ACCESS_KEY:
        return False, "UNSPLASH_ACCESS_KEY missing from secrets", None
    url = "https://api.unsplash.com/search/photos"
    headers = {"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"}
    params = {"query": query, "orientation": "landscape", "per_page": 5}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=12)
        results = r.json().get("results", [])
        if not results:
            return False, "No photos found", None
        img_url = results[0]["urls"].get("full") or results[0]["urls"].get("regular")
        ok, msg = download_stream(img_url, out_path, max_size_mb=UNLIMITED_MEDIA_SIZE_MB)
        return ok, msg, img_url
    except Exception as e:
        return False, str(e), None


def fetch_wikimedia_stills(query: str, out_path: str, _q: str = "", _c: int | None = None) -> tuple[bool, str, str | None]:
    url = "https://commons.wikimedia.org/w/api.php"
    headers = {"User-Agent": GLOBAL_USER_AGENT}
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": f"{query} filetype:bitmap -filetype:pdf -filetype:audio",
        "gsrnamespace": "6",
        "gsrlimit": "10",
        "prop": "imageinfo",
        "iiprop": "url|mime|size",
        "iiurlwidth": "2560"
    }
    try:
        r = requests.get(url, params=params, headers=headers, timeout=15)
        pages = r.json().get("query", {}).get("pages", {})
        if not pages:
            return False, "No matching archival records found", None

        for _, page in pages.items():
            infos = page.get("imageinfo") or []
            if not infos:
                continue
            chosen_url = infos[0].get("thumburl") or infos[0].get("url")
            ok, detail = download_stream(chosen_url, out_path, max_size_mb=MAX_WIKIMEDIA_SIZE_MB)
            if ok:
                return True, f"{detail} (Archival Stills)", chosen_url

        return False, "No archival image found within 10MB limit", None
    except Exception as e:
        return False, str(e), None


def fetch_loc_video(query: str, out_path: str, _q: str = "", clip_seconds: int | None = None) -> tuple[bool, str, str | None]:
    url = "https://www.loc.gov/film-and-videos/"
    headers = {"User-Agent": GLOBAL_USER_AGENT}
    params = {"q": query, "fo": "json", "fa": "online-format:video", "c": 6}
    try:
        r = requests.get(url, params=params, headers=headers, timeout=15)
        results = r.json().get("results", [])
        if not results:
            return False, "No LOC film records found", None

        for item in results:
            item_id = item.get("id")
            if not item_id:
                continue
            m_res = requests.get(f"{item_id}?fo=json", headers=headers, timeout=12)
            if m_res.status_code != 200:
                continue
            for res in m_res.json().get("resources", []):
                for grp in res.get("files", []):
                    for f in grp:
                        if f.get("url", "").endswith(".mp4"):
                            cdn_url = f["url"]
                            if clip_seconds:
                                ok, msg = trim_video_stream(cdn_url, out_path, clip_seconds)
                            else:
                                ok, msg = download_stream(cdn_url, out_path, max_size_mb=UNLIMITED_MEDIA_SIZE_MB)
                            if ok:
                                return True, msg, cdn_url
        return False, "No downloadable MP4 asset found in LOC records", None
    except Exception as e:
        return False, str(e), None


def fetch_loc_photo(query: str, out_path: str, _q: str = "", _c: int | None = None) -> tuple[bool, str, str | None]:
    url = "https://www.loc.gov/photos/"
    headers = {"User-Agent": GLOBAL_USER_AGENT}
    params = {"q": query, "fo": "json", "fa": "online-format:image", "c": 8}
    try:
        r = requests.get(url, params=params, headers=headers, timeout=15)
        results = r.json().get("results", [])
        if not results:
            return False, "No LOC photo records found", None

        for item in results:
            img_urls = item.get("image_url", [])
            chosen_url = img_urls[-1] if isinstance(img_urls, list) and img_urls else None
            if chosen_url:
                if chosen_url.startswith("//"):
                    chosen_url = "https:" + chosen_url
                ok, detail = download_stream(chosen_url, out_path, max_size_mb=UNLIMITED_MEDIA_SIZE_MB)
                if ok:
                    return True, detail, chosen_url
        return False, "No downloadable image stream found in LOC record", None
    except Exception as e:
        return False, str(e), None


def fetch_nara_video(query: str, out_path: str, _q: str = "", clip_seconds: int | None = None) -> tuple[bool, str, str | None]:
    ia_url = "https://archive.org/advancedsearch.php"
    params = {"q": f"({query}) AND collection:(fedflix)", "fl[]": "identifier", "rows": 4, "output": "json"}
    try:
        r = requests.get(ia_url, params=params, headers={"User-Agent": GLOBAL_USER_AGENT}, timeout=12)
        if r.status_code == 200:
            docs = r.json().get("response", {}).get("docs", [])
            for doc in docs:
                ident = doc.get("identifier")
                if ident:
                    m_res = requests.get(f"https://archive.org/metadata/{ident}/files", headers={"User-Agent": GLOBAL_USER_AGENT}, timeout=10)
                    if m_res.status_code == 200:
                        files = m_res.json().get("result", [])
                        mp4s = [f for f in files if f.get("name", "").lower().endswith(".mp4")]
                        if mp4s:
                            mp4s.sort(key=lambda x: int(x.get("size", 0)), reverse=True)
                            chosen = f"https://archive.org/download/{ident}/{mp4s[0]['name']}"
                            if clip_seconds:
                                ok, msg = trim_video_stream(chosen, out_path, clip_seconds)
                            else:
                                ok, msg = download_stream(chosen, out_path, max_size_mb=UNLIMITED_MEDIA_SIZE_MB)
                            if ok:
                                return True, msg, chosen
    except Exception:
        pass
    return False, f"No downloadable NARA film found for '{query}'", None


def fetch_nara_photo(query: str, out_path: str, _q: str = "", _c: int | None = None) -> tuple[bool, str, str | None]:
    return fetch_wikimedia_stills(f"{query} National Archives and Records Administration", out_path)


def fetch_visit_california_video(query: str, out_path: str, quality_choice: str = "", clip_seconds: int | None = None) -> tuple[bool, str, str | None]:
    california_query = f"{query} California" if "california" not in query.lower() else query
    if PEXELS_API_KEY:
        ok, msg, cdn = fetch_pexels_video(california_query, out_path, quality_choice, clip_seconds)
        if ok:
            return True, f"{msg} (Visit California Video)", cdn
    return fetch_loc_video(california_query, out_path, clip_seconds=clip_seconds)


def fetch_visit_california_photo(query: str, out_path: str, _q: str = "", _c: int | None = None) -> tuple[bool, str, str | None]:
    california_query = f"{query} California" if "california" not in query.lower() else query
    if UNSPLASH_ACCESS_KEY:
        ok, msg, url = fetch_unsplash_photo(california_query, out_path)
        if ok:
            return True, f"{msg} (Visit California Stills)", url
    return fetch_wikimedia_stills(california_query, out_path)


ENGINE_MAP = {
    "Stock Video Footage (Pexels)": fetch_pexels_video,
    "Stock Photos (Pexels)": fetch_pexels_photo,
    "Pixabay Video Footage": fetch_pixabay_video,
    "Pixabay Stock Photos": fetch_pixabay_photo,
    "Unsplash Editorial Photos": fetch_unsplash_photo,
    "Wikimedia Commons Stills": fetch_wikimedia_stills,
    "Library of Congress (Historic Film & Video)": fetch_loc_video,
    "Library of Congress (Historic Photos)": fetch_loc_photo,
    "National Archives (NARA Historical Footage)": fetch_nara_video,
    "National Archives (NARA Historical Stills)": fetch_nara_photo,
    "Visit California Cinematic Video": fetch_visit_california_video,
    "Visit California Travel Stills": fetch_visit_california_photo
}


def process_single_prompt(prompt: str, tool_name: str, ext: str, quality_choice: str, clip_seconds: int | None):
    filename = prompt_to_clean_filename(prompt, ext)
    out_path = os.path.join(OUTPUT_DIR, filename)
    tool_info = TOOLS[tool_name]
    is_archival = tool_info.get("archival", False)
    query_candidates = get_search_queries(prompt, is_archival=is_archival)
    fetch_func = ENGINE_MAP[tool_name]

    t0 = time.time()
    ok = False
    detail = "Search returned no records"
    cdn_url = None

    for q in query_candidates:
        ok, detail, cdn_url = fetch_func(q, out_path, quality_choice, clip_seconds)
        if ok:
            break

    elapsed = time.time() - t0
    file_bytes = None
    if ok and os.path.exists(out_path):
        try:
            with open(out_path, "rb") as f:
                file_bytes = f.read()
        except Exception:
            pass

    return {
        "prompt": prompt,
        "filename": filename,
        "path": out_path,
        "ext": ext,
        "ok": ok,
        "detail": detail,
        "cdn_url": cdn_url,
        "file_bytes": file_bytes,
        "elapsed": elapsed
    }


def create_in_memory_zip(file_list: list[str]) -> bytes:
    mem_zip = io.BytesIO()
    with zipfile.ZipFile(mem_zip, mode="w", compression=zipfile.ZIP_STORED) as zf:
        for f in file_list:
            if os.path.exists(f):
                zf.write(f, arcname=os.path.basename(f))
    mem_zip.seek(0)
    return mem_zip.read()


# =====================================================================
# STREAMLIT UI SETUP
# =====================================================================
st.set_page_config(page_title="Automation Tools By Shoaib Malik", page_icon="🎬", layout="wide")

st.markdown("""
<style>
    div[data-testid="stRadio"] label p {
        font-size: 1.15rem !important;
        font-weight: 600 !important;
        line-height: 1.8 !important;
    }
    div[data-testid="stRadio"] [data-baseweb="radio"] div:first-child {
        transform: scale(1.35);
        margin-right: 0.6rem !important;
    }
    h3, h4 {
        font-weight: 700 !important;
    }
    .video-card {
        background-color: #ffffff;
        border: 1px solid #e1e4e8;
        border-radius: 10px;
        padding: 20px;
        margin-bottom: 25px;
    }
</style>
""", unsafe_allow_html=True)

# Security login
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.markdown("# 🎬 **Automation Tools By Shoaib Malik**")
    st.caption("High-speed B-roll, public domain & stock portal pipeline for documentary research.")
    st.divider()

    _, col_login, _ = st.columns([1, 1.2, 1])
    with col_login:
        st.markdown("### 🔒 **Security Verification**")
        st.caption("Please log in with your authorized credentials to access this tool.")
        with st.form("login_form"):
            input_username = st.text_input("Username")
            input_password = st.text_input("Password", type="password")
            submit_login = st.form_submit_button("Unlock Studio", type="primary", use_container_width=True)

            if submit_login:
                if input_username == "Malik" and input_password == "Shoaib@10":
                    st.session_state.authenticated = True
                    st.success("Access Granted!")
                    st.rerun()
                else:
                    st.error("Incorrect Username or Password. Access Denied.")
    st.stop()

# Session caches
if "batch_results" not in st.session_state:
    st.session_state.batch_results = []
if "zip_bytes" not in st.session_state:
    st.session_state.zip_bytes = None
if "last_tool_used" not in st.session_state:
    st.session_state.last_tool_used = ""

if "catalog_search_results" not in st.session_state:
    st.session_state.catalog_search_results = []
if "catalog_search_query" not in st.session_state:
    st.session_state.catalog_search_query = ""

if "web_search_results" not in st.session_state:
    st.session_state.web_search_results = []
if "web_search_query" not in st.session_state:
    st.session_state.web_search_query = ""

if "video_search_results" not in st.session_state:
    st.session_state.video_search_results = []
if "video_search_query" not in st.session_state:
    st.session_state.video_search_query = ""

# Header
col_header, col_logout = st.columns([4, 1])
with col_header:
    st.markdown("# 🎬 **Automation Tools By Shoaib Malik**")
    st.caption("⚡ Live Video Explorer + Open Web Imagery + Modern Stock + Public Domain + Stock Explorers")
with col_logout:
    st.write("")
    if st.button("🔒 **Log Out**", use_container_width=True):
        st.session_state.authenticated = False
        st.session_state.batch_results = []
        st.session_state.zip_bytes = None
        st.session_state.catalog_search_results = []
        st.session_state.web_search_results = []
        st.session_state.video_search_results = []
        st.rerun()

st.divider()

col_nav, col_main = st.columns([1, 2.3])

with col_nav:
    st.markdown("### **Select Source Tool**")
    selected_tool_name = st.radio(
        "Available Repositories:",
        list(TOOLS.keys()),
        index=0,
        label_visibility="collapsed"
    )

tool_info = TOOLS[selected_tool_name]

if st.session_state.last_tool_used != selected_tool_name:
    st.session_state.batch_results = []
    st.session_state.zip_bytes = None
    st.session_state.catalog_search_results = []
    st.session_state.web_search_results = []
    st.session_state.video_search_results = []
    st.session_state.last_tool_used = selected_tool_name

with col_main:
    st.markdown(f"### **Tool: {selected_tool_name}**")
    st.info(tool_info["desc"])

    # =================================================================
    # TOOL 1: LOCATION & AERIAL VIDEO EXPLORER (VERTICAL + TIMESTAMPS)
    # =================================================================
    if tool_info["type"] == "video_explorer":
        st.markdown("#### 🎥 **Location & Aerial Video Search**")
        st.caption("Search real town names, landmarks, and city reels. Videos are listed vertically with custom start & end timestamp trimming controls.")

        if not YOUTUBE_API_KEY:
            st.warning("⚠️️ Add `YOUTUBE_API_KEY` (or `GOOGLE_API_KEY`) to your Streamlit Secrets for full YouTube Data API quota.")

        col_vbar, col_vgo = st.columns([3, 1])
        with col_vbar:
            v_query = st.text_input(
                "Enter Video Search Prompt:",
                placeholder="e.g. Shreveport Louisiana aerial drone, Big Sur highway b-roll, Miami Beach skyline 4k",
                label_visibility="collapsed"
            )
        with col_vgo:
            run_v_search = st.button("🔍 **Search Videos**", type="primary", use_container_width=True)

        if run_v_search:
            if not v_query.strip():
                st.warning("Please enter a video search prompt.")
            else:
                st.session_state.video_search_query = v_query.strip()
                with st.spinner("Finding geo-specific video reels..."):
                    items = search_top3_videos(v_query)
                    st.session_state.video_search_results = items

                if not items:
                    st.error(f"No video streams returned for '{v_query}'. Ensure your API key is enabled.")
                else:
                    st.success(f"✓ Found top 3 videos for '{v_query}'!")

        # Render each video vertically one after another
        if st.session_state.video_search_results:
            st.markdown("---")
            st.markdown(f"### **Search Results for: *\"{st.session_state.video_search_query}\"***")

            for idx, item in enumerate(st.session_state.video_search_results[:3]):
                st.markdown(f"#### **Video #{idx + 1}: {item['title']}**")
                
                col_player, col_controls = st.columns([1.6, 1.1])
                with col_player:
                    st.video(item["watch_url"])
                
                with col_controls:
                    st.markdown("##### ⏱️ **Clip Trimmer Controls**")
                    st.caption("Play video on the left, note down your preferred start and end seconds, then slice:")

                    col_s, col_e = st.columns(2)
                    with col_s:
                        start_time = st.number_input(
                            f"Start (sec)",
                            min_value=0,
                            max_value=3600,
                            value=0,
                            step=1,
                            key=f"start_time_{idx}"
                        )
                    with col_e:
                        end_time = st.number_input(
                            f"End (sec)",
                            min_value=1,
                            max_value=3600,
                            value=10,
                            step=1,
                            key=f"end_time_{idx}"
                        )

                    duration = max(1, end_time - start_time)
                    if start_time >= end_time:
                        st.error("Start time must be less than End time.")

                    clean_name = prompt_to_clean_filename(f"{st.session_state.video_search_query}_{start_time}s_{end_time}s_{idx+1}", "mp4")
                    trimmed_out = os.path.join(OUTPUT_DIR, clean_name)

                    if st.button(f"✂️ Trim Clip ({duration}s)", key=f"btn_trim_v_{idx}", type="primary", use_container_width=True, disabled=(start_time >= end_time)):
                        with st.spinner(f"Slicing clip from {start_time}s to {end_time}s..."):
                            ok, msg = trim_youtube_clip(item["watch_url"], trimmed_out, start_time, end_time)
                            if ok and os.path.exists(trimmed_out):
                                st.session_state[f"sliced_{idx}"] = trimmed_out
                                st.success(f"✓ Trimmed successfully! ({msg})")
                            else:
                                st.error("Trimming failed. Use the full video link below:")

                    if st.session_state.get(f"sliced_{idx}") and os.path.exists(st.session_state[f"sliced_{idx}"]):
                        with open(st.session_state[f"sliced_{idx}"], "rb") as vf:
                            st.download_button(
                                label=f"⬇️ **Download {clean_name}**",
                                data=vf.read(),
                                file_name=clean_name,
                                mime="video/mp4",
                                key=f"dl_v_final_{idx}",
                                type="secondary",
                                use_container_width=True
                            )

                    st.link_button("🌐 Watch Full Video on YouTube", item["watch_url"], use_container_width=True)
                
                st.divider()

    # =================================================================
    # TOOL 2: WEB OPEN IMAGE EXPLORER (3 RESULTS + INDIVIDUAL DOWNLOAD)
    # =================================================================
    elif tool_info["type"] == "web_explorer":
        st.markdown("#### 🔍 **Live Open Web Search**")
        st.caption("Search across 700M+ open web images without API keys. Displays top 3 matches in a single row with preview and 1-click download buttons.")

        col_search_bar, col_search_go = st.columns([3, 1])
        with col_search_bar:
            web_query = st.text_input(
                "Enter Web Search Prompt:",
                placeholder="e.g. panther creek park, moody foggy mountain forest road, retro diner neon sign",
                label_visibility="collapsed"
            )
        with col_search_go:
            run_web_search = st.button("🔍 **Search Images**", type="primary", use_container_width=True)

        if run_web_search:
            if not web_query.strip():
                st.warning("Please enter a search prompt.")
            else:
                st.session_state.web_search_query = web_query.strip()
                with st.spinner("Searching web images and retrieving previews..."):
                    items = search_web_open_top3(web_query)
                    st.session_state.web_search_results = items

                if not items:
                    st.error(f"No web images found for '{web_query}'. Try broader terms.")
                else:
                    st.success(f"✓ Displaying top 3 results for '{web_query}'!")

        if st.session_state.web_search_results:
            st.markdown("---")
            st.markdown(f"#### **Top 3 Web Results for: *\"{st.session_state.web_search_query}\"***")

            items = st.session_state.web_search_results[:3]
            cols = st.columns(3)

            for idx, item in enumerate(items):
                with cols[idx]:
                    st.image(item["image_bytes"], use_container_width=True)
                    st.caption(f"**{item['title'][:40]}...**" if len(item['title']) > 40 else f"**{item['title']}**")

                    clean_fname = prompt_to_clean_filename(f"{st.session_state.web_search_query}_{idx+1}", "jpg")
                    st.download_button(
                        label=f"⬇️ **Download Image #{idx+1}**",
                        data=item["image_bytes"],
                        file_name=clean_fname,
                        mime="image/jpeg",
                        key=f"dl_web_{idx}",
                        type="primary" if idx == 0 else "secondary",
                        use_container_width=True
                    )
                    st.link_button("🌐 Open Source URL", item["source_url"], use_container_width=True)

    # =================================================================
    # TOOL 3: CATALOG EXPLORER (ISTOCK / SHUTTERSTOCK)
    # =================================================================
    elif tool_info["type"] == "catalog_explorer":
        source_brand = tool_info["source"]
        st.markdown(f"#### 🔍 **Live {source_brand.capitalize()} Catalog Search**")
        st.caption(f"Enter any visual prompt below. The tool will search {source_brand.capitalize()}, display the top 3 matches in a single row, and let you copy the URL with 1-click.")

        col_search_bar, col_search_go = st.columns([3, 1])
        with col_search_bar:
            catalog_query = st.text_input(
                f"Enter {source_brand.capitalize()} Search Prompt:",
                placeholder="e.g. stylish interior living room design wooden, executive boardroom, cyberpunk night city",
                label_visibility="collapsed"
            )
        with col_search_go:
            run_catalog_search = st.button("🔍 **Search Images**", type="primary", use_container_width=True)

        if run_catalog_search:
            if not catalog_query.strip():
                st.warning("Please enter a search prompt.")
            else:
                st.session_state.catalog_search_query = catalog_query.strip()
                with st.spinner(f"Querying {source_brand.capitalize()} and loading previews..."):
                    if source_brand == "istock":
                        items = search_istock_top3(catalog_query)
                    else:
                        items = search_shutterstock_top3(catalog_query)

                    st.session_state.catalog_search_results = items

                if not items:
                    st.error(f"No results returned from {source_brand.capitalize()}. Try broader keywords.")
                else:
                    st.success(f"✓ Displaying top 3 results from {source_brand.capitalize()}!")

        if st.session_state.catalog_search_results:
            st.markdown("---")
            st.markdown(f"#### **Top 3 Results for: *\"{st.session_state.catalog_search_query}\"***")

            items = st.session_state.catalog_search_results[:3]
            cols = st.columns(3)

            for idx, item in enumerate(items):
                with cols[idx]:
                    st.image(item["image_bytes"], use_container_width=True)
                    st.caption(f"**{item['title'][:40]}...**" if len(item['title']) > 40 else f"**{item['title']}**")

                    raw_url = item["target_url"]
                    btn_id = f"cp_btn_{idx}"
                    copy_component_html = f"""
                    <div style="margin-bottom: 15px;">
                        <input type="text" value="{raw_url}" id="url_val_{idx}" readonly style="
                            width: 100%;
                            padding: 6px 8px;
                            font-size: 11px;
                            border: 1px solid #d0d7de;
                            border-radius: 4px;
                            background: #f6f8fa;
                            color: #24292f;
                            margin-bottom: 6px;
                            box-sizing: border-box;
                        ">
                        <button id="{btn_id}" onclick="
                            const inp = document.getElementById('url_val_{idx}');
                            navigator.clipboard.writeText(inp.value);
                            const b = document.getElementById('{btn_id}');
                            b.innerText = '✓ Copied!';
                            b.style.background = '#2ea44f';
                            setTimeout(() => {{
                                b.innerText = '📋 Copy Link';
                                b.style.background = '#0969da';
                            }}, 1800);
                        " style="
                            width: 100%;
                            background-color: #0969da;
                            color: white;
                            border: none;
                            padding: 8px 12px;
                            font-size: 13px;
                            font-weight: 600;
                            border-radius: 6px;
                            cursor: pointer;
                        ">
                            📋 Copy Link
                        </button>
                    </div>
                    """
                    components.html(copy_component_html, height=85)

    # =================================================================
    # TOOL 4: STOCK & ARCHIVAL BATCH SOURCING
    # =================================================================
    else:
        auth_key_name = tool_info.get("auth_key")
        if auth_key_name:
            current_key = globals().get(auth_key_name, "")
            if not current_key:
                st.warning(f"⚠️️ `{auth_key_name}` is not configured in your Streamlit Secrets vault.")

        quality_choice = "1080p Full HD"
        clip_seconds = 10

        if tool_info["type"] == "video":
            col_q1, col_q2 = st.columns(2)
            with col_q1:
                st.markdown("**Clip Length**")
                clip_label = st.selectbox(
                    "Clip Length",
                    ["10 Seconds (Default)", "15 Seconds", "Full Video Length"],
                    index=0,
                    label_visibility="collapsed"
                )
                if clip_label == "10 Seconds (Default)":
                    clip_seconds = 10
                elif clip_label == "15 Seconds":
                    clip_seconds = 15
                else:
                    clip_seconds = None

            with col_q2:
                st.markdown("**Quality**")
                quality_choice = st.selectbox(
                    "Quality",
                    ["1080p Full HD", "4K UHD (2160p)", "720p HD"],
                    index=0,
                    label_visibility="collapsed"
                )

        st.markdown("**Visual Prompts (one prompt per line)**")
        prompt_placeholder = (
            "Big Sur coastal highway sunset\nYosemite Valley misty sunrise waterfalls\nSan Francisco golden gate aerial drone"
            if "California" in selected_tool_name
            else "wright brothers first flight kitty hawk\ncivil war battlefield photography\nmodern corporate boardroom meeting"
        )
        prompt_input = st.text_area(
            "Visual Prompts",
            height=160,
            placeholder=prompt_placeholder,
            label_visibility="collapsed"
        )

        col_btn1, col_btn2 = st.columns([1.3, 1])
        with col_btn1:
            start_btn = st.button("⚡ **Start Fast Parallel Sourcing**", type="primary", use_container_width=True)
        with col_btn2:
            if st.session_state.batch_results:
                if st.button("**Clear Results**", use_container_width=True):
                    st.session_state.batch_results = []
                    st.session_state.zip_bytes = None
                    st.rerun()

        if start_btn:
            lines = [line.strip() for line in prompt_input.splitlines() if line.strip()]
            if not lines:
                st.warning("Please enter at least one visual prompt.")
            else:
                ext = tool_info["ext"]
                st.session_state.batch_results = []
                st.session_state.zip_bytes = None

                with st.spinner(f"Fetching {len(lines)} asset(s) simultaneously from edge servers..."):
                    t_all = time.time()

                    with ThreadPoolExecutor(max_workers=min(len(lines), 8)) as executor:
                        futures = [
                            executor.submit(process_single_prompt, line, selected_tool_name, ext, quality_choice, clip_seconds)
                            for line in lines
                        ]
                        results = [f.result() for f in futures]

                    st.session_state.batch_results = results

                    valid_paths = [r["path"] for r in results if r["ok"] and os.path.exists(r["path"])]
                    if valid_paths:
                        st.session_state.zip_bytes = create_in_memory_zip(valid_paths)

                st.success(f"✓ Retrieved {len(valid_paths)} of {len(lines)} items in {time.time() - t_all:.1f}s total!")
                st.rerun()

        # Results View
        if st.session_state.batch_results:
            results = st.session_state.batch_results
            successful = [r for r in results if r["ok"]]
            failed = [r for r in results if not r["ok"]]

            if successful:
                st.markdown("### **Download Your Sourced Assets**")

                if st.session_state.zip_bytes:
                    zip_mb = len(st.session_state.zip_bytes) / (1024 * 1024)
                    st.download_button(
                        label=f"📦 **Download All as Single Archive (.ZIP) — [{zip_mb:.1f} MB Total]**",
                        data=st.session_state.zip_bytes,
                        file_name="broll_assets.zip",
                        mime="application/zip",
                        type="primary",
                        use_container_width=True
                    )

            st.divider()
            st.markdown("#### **Sourced File Status & Individual Downloads**")

            for r in failed:
                st.error(f"✖ **Failed:** \"{r['prompt']}\" — {r['detail']}")

            for r in successful:
                st.success(f"✓ **Saved:** `{r['filename']}` — {r['detail']} (Fetched in {r['elapsed']:.1f}s)")
                col_prev, col_meta = st.columns([1.6, 1.2])
                with col_prev:
                    if r["ext"] == "mp4" and os.path.exists(r["path"]):
                        st.video(r["path"])
                    elif os.path.exists(r["path"]):
                        st.image(r["path"], use_container_width=True)
                with col_meta:
                    st.markdown(f"**Prompt:** {r['prompt']}")
                    st.markdown(f"**Filename:** `{r['filename']}`")
                    st.caption(f"File Size: {r['detail']}")

                    if r.get("file_bytes"):
                        st.download_button(
                            label=f"⬇ **Download {r['filename']}**",
                            data=r["file_bytes"],
                            file_name=r["filename"],
                            mime="video/mp4" if r["ext"] == "mp4" else "image/jpeg",
                            key=f"dl_single_{r['filename']}",
                            type="secondary",
                            use_container_width=True
                        )

                    if r.get("cdn_url"):
                        st.link_button("🌐 Open Source File", r["cdn_url"], use_container_width=True)
                st.write("---")
