import streamlit as st
import yt_dlp
import os
import re
import tempfile
from pathlib import Path

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(page_title="YT Downloader", page_icon="▶", layout="centered")

# ── CSS ────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&display=swap');

html, body, [class*="css"] { font-family: 'Space Grotesk', sans-serif; }
.stApp { background: #0f0f0f; color: #f0f0f0; }

h1 { font-size: 2.4rem !important; font-weight: 700 !important;
     color: #ff0000 !important; letter-spacing: -1px; }

.subtitle { color: #666; font-size: 0.9rem; margin-top: -10px; margin-bottom: 24px; }

div[data-testid="stTextInput"] input,
div[data-testid="stTextArea"] textarea {
    background: #1a1a1a; border: 1px solid #2e2e2e; border-radius: 8px;
    color: #f0f0f0; font-size: 0.92rem; padding: 10px 13px;
}
div[data-testid="stTextInput"] input:focus,
div[data-testid="stTextArea"] textarea:focus {
    border-color: #ff0000; box-shadow: 0 0 0 2px rgba(255,0,0,0.15);
}

div[data-testid="stSelectbox"] > div,
div[data-testid="stRadio"] > div {
    background: #1a1a1a; border-radius: 8px;
}

.stButton > button {
    background: #ff0000; color: white; border: none; border-radius: 8px;
    padding: 11px 26px; font-weight: 600; font-size: 0.95rem;
    width: 100%; transition: background 0.18s;
}
.stButton > button:hover { background: #cc0000; color: white; }

.tag {
    display: inline-block; background: #222; color: #999;
    border-radius: 5px; padding: 2px 10px; font-size: 0.78rem;
    margin-right: 5px; margin-top: 4px;
}
.playlist-tag {
    display: inline-block; background: #1a1a2e; color: #7b9fff;
    border: 1px solid #2a2a5e; border-radius: 5px; padding: 3px 12px;
    font-size: 0.82rem; margin-right: 5px; margin-top: 4px; font-weight: 600;
}
.private-tag {
    display: inline-block; background: #2e1a1a; color: #ff7b7b;
    border: 1px solid #5e2a2a; border-radius: 5px; padding: 3px 12px;
    font-size: 0.82rem; margin-right: 5px; margin-top: 4px; font-weight: 600;
}

.success-msg {
    background: #0d2e1a; border: 1px solid #1a5e33; border-radius: 8px;
    padding: 13px 17px; color: #4caf87; font-weight: 600; margin: 10px 0;
}
.error-msg {
    background: #2e0d0d; border: 1px solid #5e1a1a; border-radius: 8px;
    padding: 13px 17px; color: #e57373; font-weight: 600; margin: 10px 0;
}
.info-msg {
    background: #1a1a2e; border: 1px solid #2a2a5e; border-radius: 8px;
    padding: 13px 17px; color: #7b9fff; margin: 10px 0; font-size: 0.9rem;
}
.warn-msg {
    background: #2e2a0d; border: 1px solid #5e520a; border-radius: 8px;
    padding: 13px 17px; color: #d4b84a; margin: 10px 0; font-size: 0.9rem;
}

.video-row {
    background: #161616; border: 1px solid #2a2a2a; border-radius: 8px;
    padding: 10px 14px; margin: 6px 0; display: flex; align-items: center; gap: 12px;
}
.video-index { color: #555; font-size: 0.8rem; min-width: 24px; }
.video-title { color: #ddd; font-size: 0.88rem; flex: 1; }
.video-dur { color: #666; font-size: 0.8rem; white-space: nowrap; }

.section-header {
    font-size: 0.75rem; font-weight: 700; color: #555;
    text-transform: uppercase; letter-spacing: 1.5px; margin: 18px 0 8px 0;
}

hr { border: none; border-top: 1px solid #222; margin: 18px 0; }
#MainMenu, footer, header { visibility: hidden; }

div[data-testid="stFileUploader"] {
    background: #1a1a1a; border: 1px dashed #333; border-radius: 8px; padding: 8px;
}
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def is_playlist_url(url: str) -> bool:
    return bool(re.search(r"[?&]list=", url))

def is_valid_url(url: str) -> bool:
    patterns = [
        r"(https?://)?(www\.)?(youtube\.com|youtu\.be)/",
        r"(https?://)?(www\.)?youtube\.com/playlist",
    ]
    return any(re.search(p, url) for p in patterns)

def human_size(nbytes):
    for unit in ["B", "KB", "MB", "GB"]:
        if nbytes < 1024:
            return f"{nbytes:.1f} {unit}"
        nbytes /= 1024
    return f"{nbytes:.1f} TB"

def fmt_dur(secs):
    if not secs:
        return "?"
    m, s = divmod(int(secs), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

def clean_ansi(s):
    return re.sub(r"\x1b\[[0-9;]*m", "", s or "")

def build_ydl_opts(cookie_path=None, cookie_browser=None):
    """Base yt-dlp options, with optional auth."""
    opts = {"quiet": True, "no_warnings": True}
    if cookie_path:
        opts["cookiefile"] = cookie_path
    elif cookie_browser:
        opts["cookiesfrombrowser"] = (cookie_browser,)
    return opts

def get_formats_for_video(info):
    resolutions = [2160, 1440, 1080, 720, 480, 360, 240, 144]
    seen, fmts = set(), []
    for fmt in info.get("formats", []):
        h = fmt.get("height")
        if not h:
            continue
        if h in resolutions and h not in seen:
            fmts.append({
                "label": f"{h}p",
                "height": h,
                "format_spec": f"bestvideo[height<={h}]+bestaudio/best[height<={h}]",
            })
            seen.add(h)
    fmts.sort(key=lambda x: x["height"], reverse=True)
    fmts.append({"label": "Audio only (MP3)", "height": 0,
                 "format_spec": "bestaudio/best", "audio_only": True})
    return fmts


# ── Fetch info ─────────────────────────────────────────────────────────────────

def fetch_info(url, cookie_path=None, cookie_browser=None):
    opts = build_ydl_opts(cookie_path, cookie_browser)
    opts.update({"skip_download": True, "extract_flat": False,
                 "ignoreerrors": True})
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)
    except Exception as e:
        return {"error": str(e)}

def fetch_playlist_flat(url, cookie_path=None, cookie_browser=None):
    """Quickly fetch playlist metadata without downloading each video."""
    opts = build_ydl_opts(cookie_path, cookie_browser)
    opts.update({"skip_download": True, "extract_flat": True,
                 "ignoreerrors": True})
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)
    except Exception as e:
        return {"error": str(e)}


# ── Download ───────────────────────────────────────────────────────────────────

def download_single(url, fmt, save_dir, progress_ph, cookie_path=None, cookie_browser=None):
    os.makedirs(save_dir, exist_ok=True)
    is_audio = fmt.get("audio_only", False)

    def hook(d):
        if d["status"] == "downloading":
            raw = clean_ansi(d.get("_percent_str", "0%"))
            try:
                pct = float(raw.replace("%", "")) / 100
            except ValueError:
                pct = 0
            speed = clean_ansi(d.get("_speed_str", ""))
            eta = clean_ansi(d.get("_eta_str", ""))
            progress_ph.progress(min(pct, 1.0),
                text=f"Downloading… {raw}  |  {speed}  |  ETA {eta}")

    opts = build_ydl_opts(cookie_path, cookie_browser)
    opts.update({
        "format": fmt["format_spec"],
        "outtmpl": os.path.join(save_dir, "%(title)s.%(ext)s"),
        "progress_hooks": [hook],
        "merge_output_format": "mp4",
        "postprocessors": [],
    })
    if is_audio:
        opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }]
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            ext = "mp3" if is_audio else "mp4"
            title = re.sub(r'[\\/*?:"<>|]', "_", info.get("title", "video"))
            path = os.path.join(save_dir, f"{title}.{ext}")
            if not os.path.exists(path):
                for f in Path(save_dir).glob(f"*.{ext}"):
                    path = str(f); break
        progress_ph.progress(1.0, text="✅ Done!")
        return path
    except Exception as e:
        return f"ERROR:{e}"


def download_playlist(url, fmt, save_dir, status_ph, cookie_path=None, cookie_browser=None):
    """Download all videos in a playlist into a named subfolder."""
    is_audio = fmt.get("audio_only", False)
    state = {"current": 0, "title": "", "percent": 0, "speed": "", "eta": "",
              "done": 0, "total": 0, "errors": []}

    def hook(d):
        if d["status"] == "downloading":
            state["title"] = d.get("info_dict", {}).get("title", "")[:60]
            raw = clean_ansi(d.get("_percent_str", "0%"))
            try:
                state["percent"] = float(raw.replace("%", ""))
            except ValueError:
                pass
            state["speed"] = clean_ansi(d.get("_speed_str", ""))
            state["eta"] = clean_ansi(d.get("_eta_str", ""))
            total = state["total"] or 1
            done = state["done"]
            overall = ((done + state["percent"] / 100) / total) * 100
            status_ph.progress(
                min(overall / 100, 1.0),
                text=f"[{done+1}/{total}] {state['title']} — "
                     f"{state['percent']:.0f}%  {state['speed']}  ETA {state['eta']}"
            )
        elif d["status"] == "finished":
            state["done"] += 1
            state["percent"] = 0

    opts = build_ydl_opts(cookie_path, cookie_browser)
    opts.update({
        "format": fmt["format_spec"],
        "outtmpl": os.path.join(save_dir, "%(playlist_title)s", "%(playlist_index)s - %(title)s.%(ext)s"),
        "progress_hooks": [hook],
        "merge_output_format": "mp4",
        "ignoreerrors": True,
        "postprocessors": [],
    })
    if is_audio:
        opts["outtmpl"] = os.path.join(
            save_dir, "%(playlist_title)s", "%(playlist_index)s - %(title)s.%(ext)s")
        opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }]

    try:
        # Pre-fetch to get total count
        flat_opts = build_ydl_opts(cookie_path, cookie_browser)
        flat_opts.update({"skip_download": True, "extract_flat": True,
                          "quiet": True, "no_warnings": True, "ignoreerrors": True})
        with yt_dlp.YoutubeDL(flat_opts) as ydl:
            flat = ydl.extract_info(url, download=False)
            state["total"] = len(flat.get("entries", [])) if flat else 0

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)

        playlist_name = (info or {}).get("title", "Playlist")
        folder = os.path.join(save_dir, re.sub(r'[\\/*?:"<>|]', "_", playlist_name))
        status_ph.progress(1.0, text=f"✅ Playlist download complete!")
        return {"folder": folder, "title": playlist_name,
                "done": state["done"], "total": state["total"],
                "errors": state["errors"]}
    except Exception as e:
        return {"error": str(e)}


# ══════════════════════════════════════════════════════════════════════════════
# SESSION STATE
# ══════════════════════════════════════════════════════════════════════════════

for key, default in {
    "info": None, "formats": [], "is_playlist": False,
    "playlist_entries": [], "cookie_path": None,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default


# ══════════════════════════════════════════════════════════════════════════════
# UI — HEADER
# ══════════════════════════════════════════════════════════════════════════════

st.markdown("# ▶ YT Downloader")
st.markdown('<p class="subtitle">Single videos · Playlists · Public & Private — powered by yt-dlp</p>',
            unsafe_allow_html=True)

# ── URL input ──────────────────────────────────────────────────────────────────
url = st.text_input("YouTube URL",
    placeholder="https://www.youtube.com/watch?v=...  or  .../playlist?list=...")

# ── Save directory ─────────────────────────────────────────────────────────────
save_dir = st.text_input("Save to folder",
    value=str(Path.home() / "Downloads" / "YT_Downloads"))

st.markdown("<hr>", unsafe_allow_html=True)

# ── Private playlist / auth section ───────────────────────────────────────────
st.markdown('<p class="section-header">🔒 Private Playlist / Account Access (optional)</p>',
            unsafe_allow_html=True)

st.markdown("""
<div class="info-msg">
    To download <b>private or unlisted playlists</b> you need to give yt-dlp access to your
    YouTube login. Choose one of the two methods below.
</div>
""", unsafe_allow_html=True)

auth_method = st.radio(
    "Auth method",
    ["None (public only)", "Import cookies from browser", "Upload cookies.txt file"],
    horizontal=True,
    label_visibility="collapsed",
)

cookie_path = None
cookie_browser = None

if auth_method == "Import cookies from browser":
    browser = st.selectbox("Which browser?",
        ["chrome", "firefox", "edge", "safari", "brave", "opera"],
        help="yt-dlp will read your browser's YouTube cookies automatically.")
    cookie_browser = browser
    st.markdown("""
    <div class="warn-msg">
        ⚠️ Make sure you're <b>logged into YouTube</b> in that browser. Close the browser
        before running the download if you get auth errors (some browsers lock the cookie DB).
    </div>""", unsafe_allow_html=True)

elif auth_method == "Upload cookies.txt file":
    st.markdown("""
    <div class="info-msg">
        Export your cookies using the browser extension
        <b>"Get cookies.txt LOCALLY"</b> (Chrome/Firefox), then upload the file here.
    </div>""", unsafe_allow_html=True)
    uploaded = st.file_uploader("Upload cookies.txt", type=["txt"])
    if uploaded:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="wb")
        tmp.write(uploaded.read())
        tmp.close()
        cookie_path = tmp.name
        st.session_state.cookie_path = cookie_path
        st.markdown('<div class="success-msg">✅ cookies.txt loaded</div>',
                    unsafe_allow_html=True)
    elif st.session_state.cookie_path:
        cookie_path = st.session_state.cookie_path

st.markdown("<hr>", unsafe_allow_html=True)

# ── Fetch button ───────────────────────────────────────────────────────────────
fetch_btn = st.button("🔍 Fetch Info")

if fetch_btn:
    if not url.strip():
        st.markdown('<div class="error-msg">⚠️ Paste a YouTube URL first.</div>',
                    unsafe_allow_html=True)
    elif not is_valid_url(url):
        st.markdown('<div class="error-msg">⚠️ That doesn\'t look like a valid YouTube URL.</div>',
                    unsafe_allow_html=True)
    else:
        st.session_state.is_playlist = is_playlist_url(url)

        if st.session_state.is_playlist:
            with st.spinner("Fetching playlist info… (this may take a moment for large playlists)"):
                info = fetch_playlist_flat(url, cookie_path, cookie_browser)
        else:
            with st.spinner("Fetching video info…"):
                info = fetch_info(url, cookie_path, cookie_browser)

        if not info or "error" in (info or {}):
            err = (info or {}).get("error", "Unknown error")
            st.markdown(f'<div class="error-msg">❌ {err}</div>',
                        unsafe_allow_html=True)
            st.session_state.info = None
        else:
            st.session_state.info = info
            if st.session_state.is_playlist:
                st.session_state.playlist_entries = info.get("entries", []) or []
                # Get formats from first available entry or use defaults
                st.session_state.formats = [
                    {"label": "1080p", "height": 1080,
                     "format_spec": "bestvideo[height<=1080]+bestaudio/best[height<=1080]"},
                    {"label": "720p", "height": 720,
                     "format_spec": "bestvideo[height<=720]+bestaudio/best[height<=720]"},
                    {"label": "480p", "height": 480,
                     "format_spec": "bestvideo[height<=480]+bestaudio/best[height<=480]"},
                    {"label": "360p", "height": 360,
                     "format_spec": "bestvideo[height<=360]+bestaudio/best[height<=360]"},
                    {"label": "Audio only (MP3)", "height": 0,
                     "format_spec": "bestaudio/best", "audio_only": True},
                ]
            else:
                st.session_state.formats = get_formats_for_video(info)


# ══════════════════════════════════════════════════════════════════════════════
# RESULTS
# ══════════════════════════════════════════════════════════════════════════════

if st.session_state.info:
    info = st.session_state.info
    is_playlist = st.session_state.is_playlist

    st.markdown("<hr>", unsafe_allow_html=True)

    # ── PLAYLIST ──────────────────────────────────────────────────────────────
    if is_playlist:
        entries = st.session_state.playlist_entries
        pl_title = info.get("title", "Playlist")
        pl_uploader = info.get("uploader") or info.get("channel") or "Unknown"
        pl_count = len([e for e in entries if e])
        privacy = info.get("availability", "")

        st.markdown(f"### 📋 {pl_title}")
        priv_label = (
            '<span class="private-tag">🔒 Private</span>' if privacy in ("private", "needs_auth")
            else '<span class="playlist-tag">🌐 Public</span>'
        )
        st.markdown(
            f'{priv_label}'
            f'<span class="tag">👤 {pl_uploader}</span>'
            f'<span class="tag">🎬 {pl_count} videos</span>',
            unsafe_allow_html=True,
        )

        # Show video list (first 50)
        st.markdown('<p class="section-header">Videos in playlist</p>', unsafe_allow_html=True)
        show_entries = [e for e in entries if e][:50]
        rows_html = ""
        for i, e in enumerate(show_entries, 1):
            t = (e.get("title") or "Untitled")[:70]
            d = fmt_dur(e.get("duration"))
            rows_html += (
                f'<div class="video-row">'
                f'<span class="video-index">{i}</span>'
                f'<span class="video-title">{t}</span>'
                f'<span class="video-dur">{d}</span>'
                f'</div>'
            )
        if pl_count > 50:
            rows_html += f'<p style="color:#555;font-size:0.8rem;margin-top:8px;">… and {pl_count - 50} more</p>'
        st.markdown(rows_html, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # Quality selector
        format_labels = [f["label"] for f in st.session_state.formats]
        selected_label = st.selectbox("Download quality (applied to all videos)", format_labels)
        selected_fmt = next(f for f in st.session_state.formats if f["label"] == selected_label)

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(f"""
        <div class="info-msg">
            Videos will be saved in a subfolder: <code>{save_dir}/{pl_title}/</code><br>
            Named as: <code>01 - Video Title.mp4</code>, <code>02 - ...</code> etc.
        </div>""", unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

        if st.button(f"⬇️ Download All {pl_count} Videos"):
            status_ph = st.empty()
            result = download_playlist(
                url, selected_fmt, save_dir, status_ph, cookie_path, cookie_browser)

            if "error" in result:
                st.markdown(f'<div class="error-msg">❌ {result["error"]}</div>',
                            unsafe_allow_html=True)
            else:
                done = result.get("done", "?")
                total = result.get("total", "?")
                folder = result.get("folder", save_dir)
                st.markdown(
                    f'<div class="success-msg">'
                    f'✅ Downloaded {done}/{total} videos<br>'
                    f'📁 Saved to: <code>{folder}</code>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

    # ── SINGLE VIDEO ──────────────────────────────────────────────────────────
    else:
        thumb = info.get("thumbnail", "")
        title = info.get("title", "Unknown")
        uploader = info.get("uploader", "Unknown")
        duration = info.get("duration", 0)
        view_count = info.get("view_count") or 0

        if thumb:
            st.image(thumb, use_container_width=True)

        st.markdown(f"### {title}")
        st.markdown(
            f'<span class="tag">👤 {uploader}</span>'
            f'<span class="tag">⏱ {fmt_dur(duration)}</span>'
            f'<span class="tag">👁 {view_count:,} views</span>',
            unsafe_allow_html=True,
        )

        st.markdown("<br>", unsafe_allow_html=True)

        format_labels = [f["label"] for f in st.session_state.formats]
        selected_label = st.selectbox("Choose quality", format_labels)
        selected_fmt = next(f for f in st.session_state.formats if f["label"] == selected_label)

        st.markdown("<br>", unsafe_allow_html=True)

        if st.button("⬇️ Download"):
            progress_ph = st.empty()
            result = download_single(
                url, selected_fmt, save_dir, progress_ph, cookie_path, cookie_browser)

            if result and result.startswith("ERROR:"):
                st.markdown(f'<div class="error-msg">❌ {result[6:]}</div>',
                            unsafe_allow_html=True)
            elif result and os.path.exists(result):
                size = human_size(os.path.getsize(result))
                st.markdown(
                    f'<div class="success-msg">✅ Saved to: <code>{result}</code> ({size})</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    '<div class="error-msg">❌ File not found after download. '
                    'Check the save folder manually.</div>',
                    unsafe_allow_html=True,
                )

st.markdown("<br><br>", unsafe_allow_html=True)
st.markdown(
    '<p style="color:#333;font-size:0.78rem;text-align:center;">'
    'For personal use only · Respect copyright</p>',
    unsafe_allow_html=True,
)