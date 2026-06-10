import speech_recognition as sr
import pyttsx3
import requests
import psutil
import os
import webbrowser
import subprocess
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import datetime
import threading
import winsound
import re

# ── CONFIG ──────────────────────────────────────────
SIMPLE_MODEL          = "llama3.2"
SMART_MODEL           = "qwen3.6:27b"
OLLAMA_URL            = "http://localhost:11434/api/chat"
WAKE_WORD             = "nova"
SPOTIFY_CLIENT_ID     = "a370ea066f954e93826453b8e9b7ca12"
SPOTIFY_CLIENT_SECRET = "7ff516d1a42c40e0918a0d92aca13728"
SPOTIFY_REDIRECT_URI  = "http://127.0.0.1:8888/callback"
DEFAULT_CITIES        = ["Bhubaneswar", "Soro"]

SPOTIFY_KEYWORDS = [
    "play", "pause", "resume", "next", "previous", "skip",
    "stop music", "volume", "what song", "what's playing", "music"
]

COMPLEX_KEYWORDS = [
    "explain", "compare", "analyze", "write code",
    "difference between", "pros and cons"
]

SYSTEM_CONTEXT_TRIGGERS = [
    "ram", "memory", "cpu", "disk", "battery",
    "process", "system status", "pc health"
]

SYSTEM_PROMPT = """You are NOVA (Neural Operative Virtual Assistant), a personal AI assistant.
You speak in natural conversational language like a real voice assistant.
No bullet points, no markdown, no asterisks, no dashes, no special characters.
Plain spoken sentences only — the way a human would speak out loud.
You are sharp, direct, and efficient.
When given system data, summarize it naturally in spoken form."""

# ── SPOTIFY SETUP ───────────────────────────────────
sp = None

def init_spotify():
    global sp
    try:
        sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
            client_id=SPOTIFY_CLIENT_ID,
            client_secret=SPOTIFY_CLIENT_SECRET,
            redirect_uri=SPOTIFY_REDIRECT_URI,
            scope="user-read-playback-state user-modify-playback-state user-read-currently-playing"
        ))
        sp.current_user()
        print("Spotify connected.")
        return True
    except Exception as e:
        print(f"Spotify error: {e}")
        return False

# ── VOICE SETUP ─────────────────────────────────────
def speak(text):
    if "<think>" in text:
        text = text.split("</think>")[-1].strip()
    print(f"\nNOVA: {text}\n")
    try:
        import win32com.client
        speaker = win32com.client.Dispatch("SAPI.SpVoice")
        speaker.Rate = 1
        voices = speaker.GetVoices()
        # try to find Indian English voice
        selected = None
        for i in range(voices.Count):
            v = voices.Item(i)
            desc = v.GetDescription().lower()
            if "india" in desc or "hindi" in desc or "heera" in desc or "ravi" in desc:
                selected = v
                break
        if selected:
            speaker.Voice = selected
        speaker.Speak(text)
    except Exception as e:
        print(f"TTS error: {e}")

# ── MIC SETUP ───────────────────────────────────────
recognizer = sr.Recognizer()
recognizer.energy_threshold = 200
recognizer.dynamic_energy_threshold = False
recognizer.pause_threshold = 1.2
mic = sr.Microphone()

print("Warming up microphone...")
with mic as source:
    recognizer.adjust_for_ambient_noise(source, duration=2)
print("Mic ready.")

# ── LISTEN ──────────────────────────────────────────
def listen(timeout=8, phrase_limit=10):
    try:
        with mic as source:
            print("Listening...")
            audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_limit)
        text = recognizer.recognize_google(audio, language="en-IN")
        print(f"You: {text}")
        return text.lower()
    except sr.WaitTimeoutError:
        return ""
    except sr.UnknownValueError:
        return ""
    except Exception as e:
        print(f"Listen error: {e}")
        return ""

# ── SYSTEM INFO ─────────────────────────────────────
def get_system_info():
    ram = psutil.virtual_memory()
    cpu = psutil.cpu_percent(interval=1)
    disk = psutil.disk_usage('C:\\')
    try:
        battery = psutil.sensors_battery()
        bat_str = f"{battery.percent}% ({'charging' if battery.power_plugged else 'discharging'})" if battery else "N/A"
    except:
        bat_str = "N/A"
    top_procs = sorted(
        [p for p in psutil.process_iter(['name', 'memory_percent']) if p.info['memory_percent'] > 0],
        key=lambda x: x.info['memory_percent'], reverse=True
    )[:5]
    procs_str = ", ".join([f"{p.info['name']}({p.info['memory_percent']:.1f}%)" for p in top_procs])
    return f"""
LIVE SYSTEM STATUS:
- RAM: {ram.percent}% used ({ram.used//1024//1024}MB of {ram.total//1024//1024}MB)
- CPU: {cpu}%
- Disk C: {disk.percent}% used | {disk.free//1024//1024//1024}GB free
- Battery: {bat_str}
- Top RAM processes: {procs_str}
"""

# ── KILL PROCESS ────────────────────────────────────
def kill_process(name):
    killed = []
    for proc in psutil.process_iter(['name']):
        if name.lower() in proc.info['name'].lower():
            try:
                proc.kill()
                killed.append(proc.info['name'])
            except:
                pass
    return killed

# ── TIME & DATE ─────────────────────────────────────
def get_time():
    now = datetime.datetime.now()
    return now.strftime("%I:%M %p").lstrip("0")

def get_date():
    now = datetime.datetime.now()
    return now.strftime("%A, %d %B %Y")

# ── WEATHER ─────────────────────────────────────────
def get_weather(city=None, forecast=False):
    cities = [city] if city else DEFAULT_CITIES
    results = []
    for c in cities:
        try:
            if forecast:
                url = f"http://wttr.in/{c}?format=%l:+Tomorrow+%t+%C"
                # get tomorrow specifically
                url = f"http://wttr.in/{c}?format=j1"
                response = requests.get(url, timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    tomorrow = data['weather'][1]
                    desc = tomorrow['hourly'][4]['weatherDesc'][0]['value']
                    max_t = tomorrow['maxtempC']
                    min_t = tomorrow['mintempC']
                    rain = tomorrow['hourly'][4]['chanceofrain']
                    results.append(f"{c}: Tomorrow {desc}, max {max_t} degrees, min {min_t} degrees, {rain} percent chance of rain.")
            else:
                url = f"http://wttr.in/{c}?format=3"
                response = requests.get(url, timeout=5)
                if response.status_code == 200:
                    text = response.text.strip().encode('ascii','ignore').decode('ascii')
                    text = re.sub(r'\s+', ' ', text)
                    results.append(text)
        except Exception as e:
            results.append(f"Couldn't fetch weather for {c}.")
    return ". ".join(results)

# ── SYSTEM VOLUME ────────────────────────────────────
def set_system_volume(level):
    try:
        from ctypes import cast, POINTER
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(interface, POINTER(IAudioEndpointVolume))
        volume.SetMasterVolumeLevelScalar(level / 100, None)
        return True
    except:
        return False

def adjust_volume(query):
    nums = re.findall(r'\d+', query)
    if not nums:
        speak("Say a percentage like set volume to 50.")
        return
    level = max(0, min(100, int(nums[0])))
    if set_system_volume(level):
        speak(f"Volume set to {level} percent.")
    else:
        speak("Couldn't set volume.")

# ── BRIGHTNESS ───────────────────────────────────────
def adjust_brightness(query):
    try:
        import screen_brightness_control as sbc
        current = sbc.get_brightness()[0]
        nums = re.findall(r'\d+', query)
        if not nums:
            speak(f"Current brightness is {current} percent.")
            return
        level = int(nums[0])
        if "reduce" in query or "decrease" in query or "lower" in query:
            new_level = max(0, current - level)
        elif "increase" in query or "raise" in query or "higher" in query:
            new_level = min(100, current + level)
        else:
            new_level = max(0, min(100, level))
        sbc.set_brightness(new_level)
        speak(f"Brightness set to {new_level} percent.")
    except:
        speak("Couldn't adjust brightness.")

# ── TIMER ────────────────────────────────────────────
def set_timer(query):
    minutes = re.findall(r'(\d+)\s*minute', query)
    seconds = re.findall(r'(\d+)\s*second', query)
    hours   = re.findall(r'(\d+)\s*hour', query)
    total_seconds = 0
    if hours:
        total_seconds += int(hours[0]) * 3600
    if minutes:
        total_seconds += int(minutes[0]) * 60
    if seconds:
        total_seconds += int(seconds[0])
    if total_seconds == 0:
        speak("Couldn't understand the timer duration.")
        return
    speak(f"Timer set for {total_seconds} seconds.")
    def timer_thread():
        import time
        time.sleep(total_seconds)
        speak("Timer done.")
        winsound.Beep(1000, 1000)
    threading.Thread(target=timer_thread, daemon=True).start()

# ── SCREENSHOT ───────────────────────────────────────
def take_screenshot():
    try:
        import pyautogui
        filename = f"C:\\NOVA\\screenshot_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        pyautogui.screenshot(filename)
        speak("Screenshot saved.")
    except:
        speak("Couldn't take screenshot.")

# ── TYPE BY VOICE ────────────────────────────────────
def type_text(query):
    try:
        import pyautogui
        text = query.replace("type", "").replace("write", "").strip()
        if text:
            pyautogui.typewrite(text, interval=0.05)
            speak("Typed.")
        else:
            speak("What should I type?")
    except:
        speak("Couldn't type.")

# ── WIKIPEDIA ────────────────────────────────────────
def search_wikipedia(query):
    try:
        import wikipedia
        search = query.replace("wikipedia", "").replace("search", "").replace("tell me about", "").strip()
        result = wikipedia.summary(search, sentences=2)
        speak(result)
    except:
        speak("Couldn't find that on Wikipedia.")

# ── GOOGLE SEARCH ────────────────────────────────────
def google_search(query):
    search = query.replace("search", "").replace("google", "").replace("on google", "").replace("look up", "").strip()
    url = f"https://www.google.com/search?q={search.replace(' ', '+')}"
    webbrowser.open(url)
    speak(f"Searching {search} on Google.")

# ── SPOTIFY ─────────────────────────────────────────
def get_active_device():
    try:
        devices = sp.devices()
        if devices['devices']:
            return devices['devices'][0]['id']
    except:
        pass
    return None

def spotify_action(query):
    if sp is None:
        speak("Spotify is not connected.")
        return
    device_id = get_active_device()
    if not device_id:
        speak("No active Spotify device. Open Spotify on your PC first.")
        return
    try:
        if "pause" in query or "stop music" in query or "stop" in query:
            sp.pause_playback(device_id=device_id)
            speak("Paused.")
        elif "next" in query or "skip" in query:
            sp.next_track(device_id=device_id)
            speak("Next track.")
        elif ("previous" in query and "song" in query) or ("previous" in query and "track" in query) or "go back" in query:
            sp.previous_track(device_id=device_id)
            speak("Previous track.")
        elif query.strip() in ["play", "resume", "continue"]:
            sp.start_playback(device_id=device_id)
            speak("Resumed.")
        elif "what" in query and ("playing" in query or "song" in query):
            current = sp.current_playback()
            if current and current.get('item'):
                track = current['item']['name']
                artist = current['item']['artists'][0]['name']
                speak(f"Playing {track} by {artist}.")
            else:
                speak("Nothing is playing right now.")
        elif "volume" in query:
            words = query.split()
            for w in words:
                if w.isdigit():
                    vol = max(0, min(100, int(w)))
                    sp.volume(vol, device_id=device_id)
                    speak(f"Volume set to {vol}.")
                    return
            speak("Say a volume number between 0 and 100.")
        elif "play" in query:
            song = query.split("play", 1)[-1].strip()
            song = song.replace("on spotify", "").replace(" song", "").strip()
            if not song:
                speak("What song?")
                song = listen()
            if song:
                results = sp.search(q=song, limit=10, type='track')
                tracks = results['tracks']['items']
                if tracks:
                    best = None
                    song_words = set(song.lower().split())
                    best_score = 0
                    for track in tracks:
                        track_words = set(track['name'].lower().split())
                        score = len(song_words & track_words)
                        if score > best_score:
                            best_score = score
                            best = track
                    if not best:
                        best = tracks[0]
                    sp.start_playback(device_id=device_id, uris=[best['uri']])
                    speak(f"Playing {best['name']} by {best['artists'][0]['name']}.")
                else:
                    speak(f"Couldn't find {song} on Spotify.")
    except Exception as e:
        speak(f"Spotify error: {str(e)}")

# ── OPEN APP ────────────────────────────────────────
def open_app(query):
    apps = {
        "chrome":         "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
        "brave":          "C:\\Program Files\\BraveSoftware\\Brave-Browser\\Application\\brave.exe",
        "notepad":        "notepad.exe",
        "calculator":     "calc.exe",
        "spotify":        "spotify.exe",
        "explorer":       "explorer.exe",
        "vs code":        "code",
        "android studio": "studio64.exe",
    }
    for app, path in apps.items():
        if app in query:
            try:
                subprocess.Popen(path, shell=True)
                speak(f"Opening {app}.")
                return True
            except:
                speak(f"Couldn't open {app}.")
                return True
    return False

# ── MODEL SELECTION ──────────────────────────────────
def pick_model(query):
    for keyword in COMPLEX_KEYWORDS:
        if keyword in query:
            return SMART_MODEL
    return SIMPLE_MODEL

# ── ASK OLLAMA ──────────────────────────────────────
def ask_ollama(query, model):
    is_system_query = any(k in query for k in SYSTEM_CONTEXT_TRIGGERS)
    context = get_system_info() if is_system_query else ""
    full_query = f"{context}\nUser: {query}" if context else query
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": full_query}
        ],
        "stream": False
    }
    try:
        speak("On it.")
        response = requests.post(OLLAMA_URL, json=payload, timeout=300)
        data = response.json()
        return data["message"]["content"]
    except Exception as e:
        return f"Couldn't reach Ollama: {e}"

# ── HANDLE QUERY ────────────────────────────────────
def handle(query):
    if not query:
        return

    # exit
    if any(w in query for w in ["shut down", "shutdown", "goodbye", "turn off", "close yourself", "terminate yourself"]):
        os._exit(0)

    # system volume — must come BEFORE spotify block
    if "volume" in query and "spotify" not in query:
        adjust_volume(query)
        return

    # spotify
    if any(k in query for k in SPOTIFY_KEYWORDS):
        spotify_action(query)
        return

    # time
    if "time" in query and "timer" not in query:
        speak(f"It's {get_time()}.")
        return

    # date
    if "date" in query or "what day" in query:
        speak(f"Today is {get_date()}.")
        return

# weather
    if "weather" in query:
        city = None
        if "soro" in query or "sorrow" in query:
            city = "Soro"
        elif "bhubaneswar" in query or "bbsr" in query:
            city = "Bhubaneswar"
        is_forecast = any(w in query for w in ["tomorrow", "future", "forecast", "next", "coming"])
        speak(get_weather(city, forecast=is_forecast))
        return

    # brightness
    if "brightness" in query:
        adjust_brightness(query)
        return

    # dark mode toggle (actual Windows registry call)
    if "dark mode" in query:
        enable = "dark" in query and "cancel" not in query and "off" not in query and "disable" not in query
        val = 0 if enable else 1
        try:
            subprocess.run(
                f'reg add HKCU\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize '
                f'/v AppsUseLightTheme /t REG_DWORD /d {val} /f',
                shell=True, capture_output=True
            )
            subprocess.run(
                f'reg add HKCU\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize '
                f'/v SystemUsesLightTheme /t REG_DWORD /d {val} /f',
                shell=True, capture_output=True
            )
            speak("Dark mode enabled." if enable else "Dark mode disabled.")
        except:
            speak("Couldn't change theme.")
        return

    # timer
    if "timer" in query or "remind me" in query:
        set_timer(query)
        return

    # screenshot
    if "screenshot" in query:
        take_screenshot()
        return

    # type by voice
    if query.startswith("type") or query.startswith("write"):
        type_text(query)
        return

    # wikipedia — bare open just prompts, search if term given
    if "wikipedia" in query:
        search_term = query.replace("open", "").replace("wikipedia", "").replace("search", "").replace("tell me about", "").strip()
        if not search_term:
            speak("What do you want to search on Wikipedia?")
            search_term = listen()
        if search_term:
            search_wikipedia(search_term)
        return

    # tell me about — wikipedia
    if "tell me about" in query and "wikipedia" not in query:
        topic = query.replace("tell me about", "").strip()
        if any(w in topic for w in ["yourself", "you", "nova", "who are you", "what are you"]):
            response = ask_ollama(query, SIMPLE_MODEL)
            speak(response)
        else:
            search_wikipedia(query)
        return
          
    # google search
    if "search" in query or "look up" in query:
        google_search(query)
        return

    # kill process
    if "kill" in query:
        target = query.replace("kill", "").strip()
        if target:
            killed = kill_process(target)
            speak(f"Killed {', '.join(killed)}." if killed else f"No process found: {target}.")
        return

    # websites
    if "open youtube" in query:
        if "brave" in query:
            subprocess.Popen(["C:\\Program Files\\BraveSoftware\\Brave-Browser\\Application\\brave.exe", "https://youtube.com"])
        elif "chrome" in query:
            subprocess.Popen(["C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe", "https://youtube.com"])
        else:
            webbrowser.open("https://youtube.com")
        speak("Opening YouTube.")
        return

    if "open google" in query:
        if "brave" in query:
            subprocess.Popen(["C:\\Program Files\\BraveSoftware\\Brave-Browser\\Application\\brave.exe", "https://google.com"])
        elif "chrome" in query:
            subprocess.Popen(["C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe", "https://google.com"])
        else:
            webbrowser.open("https://google.com")
        speak("Opening Google.")
        return

    # close browser
    if "close" in query and any(x in query for x in ["chrome", "brave", "browser", "youtube"]):
        killed = kill_process("chrome") + kill_process("brave")
        speak("Closed browser." if killed else "Browser wasn't open.")
        return

    # close / terminate any app
    if "close" in query or "terminate" in query:
        target = query.replace("close", "").replace("terminate", "").replace("the", "").strip()
        # map spoken names to process names
        process_map = {
            "vs code": "Code",
            "vscode": "Code",
            "chrome": "chrome",
            "brave": "brave",
            "spotify": "Spotify",
            "notepad": "notepad",
            "android studio": "studio64",
            "notion": "Notion",
        }
        for spoken, process in process_map.items():
            if spoken in target:
               killed = kill_process(process)
               speak(f"Closed {spoken}." if killed else f"{spoken} wasn't running.")
               return
        killed = kill_process(target)
        speak(f"Closed {target}." if killed else f"{target} wasn't running.")
        return

    # open app
    if "open" in query:
        if open_app(query):
            return

    # system check
    if any(k in query for k in ["system status", "how is my pc", "pc health", "check my pc"]):
        info = get_system_info()
        response = ask_ollama(f"Analyze this and give a quick summary:\n{info}", SIMPLE_MODEL)
        speak(response)
        return

    # ollama fallback
    model = pick_model(query)
    print(f"[Model: {model}]")
    response = ask_ollama(query, model)
    speak(response)

# ── MAIN LOOP ───────────────────────────────────────
def main():
    print("Initializing NOVA...")
    spotify_ok = init_spotify()
    if spotify_ok:
       speak("Connected to NOVA. Say Nova to activate.")
    else:
       speak("Connected to NOVA. Spotify unavailable. Say Nova to activate.")

    activated = False

    while True:
        query = listen(timeout=10, phrase_limit=15)
        if not query:
            continue
        if not activated:
            if WAKE_WORD in query:
                activated = True
                command = query.replace(WAKE_WORD, "").strip()
                if command:
                    handle(command)
                else:
                    speak("Yes?")
            continue
        handle(query)

if __name__ == "__main__":
    main()