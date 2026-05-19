# 📷 Immich photopainter

> 🖼️ A plug-and-play e-paper photo frame for the **Waveshare PhotoPainter ACCE** kit (7.3″ Spectra 6 color e-paper + Raspberry Pi Zero 2 W) that pulls random photos from one of your **Immich** albums on the LAN.

Everything — album, refresh frequency, orientation, display mode, language — is set from a **web UI hosted on the Pi**. No SSH, no YAML files to edit.

> Throughout this guide, `<your-host>` is **the hostname you set in Raspberry Pi Imager** (e.g. `photopainter`, `myframe` — whatever you chose). On most home networks you'll reach the Pi at `http://<your-host>.local/`. If that doesn't resolve, use the Pi's IP instead (find it in your router's DHCP list).

![status: works](https://img.shields.io/badge/status-works-brightgreen)
![license: MIT](https://img.shields.io/badge/license-MIT-blue)
![pi: zero 2 w](https://img.shields.io/badge/pi-zero%202%20w-c51a4a)

---

## ✨ Features

- 🎲 Random pick from any Immich album, refreshed every **5–60 min** (configurable).
- 🌙 Configurable **quiet hours** (toggle + start/end hour, wraps midnight) — silent at night, last photo stays on screen for free (e-paper).
- 🎨 Per-orientation display modes : **fill** (crop), **square** (1:1 centered), or **original** (full photo with bands). Bands color: white or black.
- 🔄 Rotation 0° / 90° / 180° / 270° — hang the frame portrait, landscape, upside-down…
- 🌈 Floyd-Steinberg dithering against the Spectra 6 native palette.
- 💾 Local cache (1–10 GB) with nightly purge — if Immich is offline, the frame keeps cycling from the cache.
- 🌍 Bilingual UI (🇬🇧 / 🇫🇷).
- 🔒 LAN-only by design (no auth needed, no cloud).

---

## 📦 What you need

| | |
|---|---|
| 🧩 | **Waveshare PhotoPainter ACCE** kit (panel + HAT, assembled) |
| 🥧 | **Raspberry Pi Zero 2 W** (64-bit, 512 MB RAM) |
| 💾 | **microSD card ≥ 8 GB** from a real brand (SanDisk, Samsung, Kingston, Lexar) |
| 🔌 | A **USB-C charger** (a phone charger works) |
| 🏠 | A self-hosted **Immich** server reachable on your LAN |
| 💻 | A computer with **Raspberry Pi Imager** installed |

---

## 🚀 Install

### 1️⃣ Flash the SD card

Open **Raspberry Pi Imager** → pick **Raspberry Pi OS Lite (64-bit)** → click the ⚙️ icon and set:

- **Hostname** : anything you want (`photopainter`, `myframe`…). Remember it — that's your `<your-host>`.
- **Username / password** : pick whatever you'll remember.
- **Wi-Fi** : your home SSID + password, the right country.
- **SSH** : ✅ enabled (password auth).
- **Locale** : your timezone + keyboard layout.

Click **Write** and wait.

### 2️⃣ Pre-enable SPI on the SD

Once the card is flashed, a partition called **`bootfs`** appears in your Finder / File Explorer. Open it and:

1. 📝 Open the file **`config.txt`** with any text editor (TextEdit, Notepad, VS Code…).
2. 🔍 Find the line that says **`#dtparam=spi=on`** (around line 8).
3. ✂️ Delete the **`#`** at the beginning so it becomes **`dtparam=spi=on`**.
4. 💾 Save the file.
5. ⏏️ Eject the **`bootfs`** volume safely (right-click → Eject).

### 3️⃣ Boot the Pi

Slide the SD into the Pi, plug the USB-C **into the HAT's port** (not the Pi's), and wait **~3 minutes** for the first boot (the Pi reboots itself once during cloud-init).

### 4️⃣ Install photopainter

```bash
ssh <your-user>@<your-host>.local
git clone https://github.com/<you>/photopainter.git
cd photopainter
sudo ./install.sh
```

The install script takes care of everything (drivers, the [PWR_PIN patch](#-pitfalls), cron, the web service). ☕

### 5️⃣ Configure from the web UI

Open **`http://<your-host>.local/`** (or `http://<pi-ip>/`) on any device on your LAN. Fill in:

1. 🌐 **Immich URL** (e.g. `https://photos.example.com`).
2. 🔑 **API key** — a one-click tutorial in the UI tells you which 3 permissions to check.
3. 📁 **Album** — once URL + key are saved, the dropdown auto-fills with your albums.
4. ⚙️ **Frequency, orientation, display mode** to your liking.

Hit **💾 Save**. A first photo appears on the panel in ~25 seconds. 🎉

That's it — the frame refreshes on its own from now on.

---

## 🚧 Pitfalls

Two things will trip up the unwary. The install script handles both for you, just so you know:

- ⚡ **`PWR_PIN = 27` (not 18)** — the generic [`waveshareteam/e-Paper`](https://github.com/waveshareteam/e-Paper) repo defaults to GPIO 18, but the PhotoPainter ACCE HAT uses **GPIO 27**. Skip the patch and the screen stays blank with `init()` silently returning 0.
- 💾 **Counterfeit SD cards** — fake cards corrupt ext4 within hours. Buy a real branded card. The install script warns you if it spots one.

---

## 📄 License

[MIT](LICENSE).
