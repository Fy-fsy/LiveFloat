# LiveFloat (浮译)    [中文](./README.md)

Turn the **foreign-language audio from web pages, videos, and meetings** into real-time Chinese subtitles displayed in an **always-on-top floating window** — it stays visible even when the page is fullscreen (browser F11 / video-site fullscreen).

> Repository: <https://github.com/Fy-fsy/LiveFloat>

> Core idea: directly capture the **sound your Windows system is playing** (WASAPI loopback — no virtual sound card, no player modification), transcribe it locally with Whisper, then translate it, and finally render it in a click-through subtitle overlay.

---

## Features

- 🎧 **System audio capture**: captures any sound your PC is playing (browser, video apps, online meetings, live streams).
- 🧠 **Local speech recognition**: faster-whisper — offline, free, and privacy-safe (audio never leaves your machine).
- 🌐 **Multiple translation providers**:
  - `MyMemory` free online (default, no key, ~5,000 words per day)
  - `DeepSeek / OpenAI-compatible` (best quality; needs your own API Key)
  - `Google Translate`, `Microsoft Edge Translate` (experimental; Google Translate requires network access)
  - `Argos offline translation`: fully offline, no key; first use downloads a ~70 MB model in-app (English ⇄ Chinese)
- 🪟 **Always-on-top overlay**: translucent, draggable, lockable click-through; stays visible over fullscreen video.
- 📜 **History**: scroll up/down inside the overlay to review previous translations.
- 📝 **Subtitle recording**: writes each sentence to `.md` / `.txt` files (one file per day); one-click delete of history.
- 🌍 **Bilingual UI**: switch between Chinese and English with the button in the top-right of the console; Simplified Chinese is the default.
- ⌨️ **Global hotkeys**:
  - `Ctrl+Alt+F` show/hide subtitle overlay
  - `Ctrl+Alt+L` lock/unlock (click-through)
  - `Ctrl+Alt+S` open console
- 📐 Font size, opacity, width, history length, and whether to show the original text are all adjustable.

---

## Quick start (run from source)

1. Double-click **`start.bat`**
   - On first run it automatically creates a virtual environment and installs dependencies (uses the Aliyun PyPI mirror automatically in China).
2. Open the console and click **“Start” (开始翻译)**
   - The speech model is downloaded automatically on first run; wait a moment.
3. Play any foreign-language video in a web page and you'll see bilingual subtitles float up at the bottom.

> If `start.bat` fails to install dependencies, run manually:
> ```bat
> py -3.12 -m venv .venv
> .venv\Scripts\python.exe -m pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com
> .venv\Scripts\python.exe run.py
> ```

---

## Requirements

- Windows 10 22H2 / Windows 11 (64-bit)
- Python 3.12 (recommended; 3.10–3.12 all work)
- First run needs internet to download the speech model (~145 MB, via the `hf-mirror.com` mirror by default)

---

## Usage tips

1. **Audio device**: on the “Audio” page, choose the device that is currently playing (headphones/speakers). If the web audio comes from your headphones, choose the headphones.
2. **Source language**: auto-detect by default; if you know it's English, switch to the `Base English` model for faster and more accurate results.
3. **Translation quality**: the free MyMemory is ~5,000 words per day; for better quality, enter a DeepSeek API Key on the “Translate” page (model name `deepseek-chat`).
   For even better quality, consider using a better source-language model and connecting a better translation model.
4. **When locked**: the overlay is click-through and won't block clicking the page; press `Ctrl+Alt+L` to unlock, then you can drag it or click its buttons.

---

## FAQ

1. Can't open the .exe file?
  Double-click **`start.bat`**.
2. After opening, a blank white window appears with no content?
   Use Task Manager to end the LiveFloat process, then reopen it.
3. Why does the warning “Running this app might put your PC at risk. App: LiveFloat.exe, Publisher: Unknown publisher” appear?
  I don't have the money to buy a code-signing certificate; without one this warning appears, but after you allow it once it won't show again.
4. Is there a virus?
   No. You can use AI to inspect my source code.
5. If you encounter problems while using it, you can send me an Issue.
---

## Privacy & disclaimer

- Speech recognition runs **locally**; **online translation** sends the text to the provider you selected (MyMemory / DeepSeek, etc.), so please don't enter sensitive content.
- When **offline translation (Argos)** is enabled, translation also runs locally, without network access.
- This software was created with the help of DeepSeek.

## Credits

- [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
- [Silero VAD](https://github.com/snakers4/silero-vad)
- [PyAudioWPatch](https://github.com/s0d3s/PyAudioWPatch)
- [PySide6](https://doc.qt.io/qtforpython-6/)
- [soxr](https://github.com/mgeier/python-soundfile) (resampling)
