# Pikabot

The desktop pet now uses 16 Pikachu-style frames, runs back and forth at the bottom of the primary display, and remains visible over ordinary windows. `pet_always_visible` defaults to true, overriding fullscreen/meeting hiding. Windows secure screens or exclusive fullscreen games may cover overlays. Use the tray to hide the pet, or Ctrl+Alt+P to toggle dragging. Voice activation remains available.

## Voice activation

After waking, full sentences are transcribed locally. You can ask **What is the temperature of my laptop?** Wait for the wake reply to finish before speaking. The recognizer allows about 1.2–1.5 seconds of ending silence. **Status / commands → Last heard** shows the latest recognized sentence in memory; transcripts are not written to disk. Unsupported requests receive an explicit response. The assistant still handles laptop commands rather than general conversation.

Say **Hey Pikabot**, wait for "I'm here", then say **temperature**, **status**, **top tasks**, or **cool down**. It stays awake across commands and pauses until you say **Okay, you may take a break** (or **take a break**). After that it accepts only the wake phrase. Break mode still uses the microphone to detect the wake phrase; the tray microphone toggle fully stops capture. Cool down still shows a confirmation before requesting any app close. Recognition supports these commands rather than open-ended conversation.

Recognition uses the installed offline Windows English speech engine and the default microphone. Audio is not uploaded or saved during normal use. The tray's **Microphone on / off** toggles listening; **Status / commands** shows listener health. Do-not-disturb stops microphone capture. Mute suppresses spoken replies. Speech playback temporarily suppresses recognition to reduce self-triggering. Voice recognition adds a separate Windows process and therefore increases memory use.

Verified with a generated wake-phrase WAV (98.4% recognizer confidence), default microphone initialization, and wake/timeout tests. Your own voice and room acoustics still affect recognition. If it cannot hear you, check the Windows default input device and microphone permissions for desktop apps.

Pikabot is a lightweight Windows 10/11 laptop guardian. It samples system load every five seconds, reads real CPU temperature from LibreHardwareMonitor when available, shows a small animated character and tray menu, and offers carefully reviewed process actions.

## Setup

1. Install Python 3.10 or newer from [python.org](https://www.python.org/downloads/windows/), selecting **pip** and **tcl/tk**.
2. Open PowerShell in this folder and run `python -m pip install -r requirements.txt`.
3. Run `python -m pikabot.main` to try it. The first launch creates original placeholder PNG frames in `assets/`.
4. For real CPU temperatures, download and run [LibreHardwareMonitor](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases). In its Options menu, turn on **Remote Web Server**; set its port to **8085**. Open `http://localhost:8085/data.json` in a browser to confirm it reports CPU package temperature. If your version uses another port, edit `lhm_url` in `config.json`.
5. Once satisfied, run `./install.ps1` to register a per-user logon task. It uses `pythonw.exe` so no console appears and restarts up to three times after a crash. `./uninstall.ps1` removes the scheduled task.

The first launch is **dry run**. In the tray, toggle dry run only after checking candidates. A real close always asks permission; save work before approving. `Undo last close` reopens the executable, but cannot restore unsaved work or the prior window state.

## Commands

Open **Status / commands** from the tray and enter `status`, `top tasks`, `cool down`, `whitelist add app.exe`, `whitelist remove app.exe`, `history`, or `sleep`. `sleep` pauses automatic action prompts. The tray also controls mute, do-not-disturb, overlay visibility, and dry run. Press **Ctrl+Alt+P** to toggle drag mode, then drag the character; press it again to restore click-through.

## Safe simulation

Run `python -m pikabot.main --simulate-temp 75` for WARM, `85` for HOT, or `95` for CRITICAL. Only one instance runs at a time, so quit between runs. Simulation always enforces dry run and never changes the power plan or hibernates. Use this to inspect the UI and logs without heating your laptop.

## Safety and limitations

- Without a sensor, CPU load is shown but **not converted into a made-up Celsius value**. Temperature actions stay inactive.
- Process selection is limited to named browsers and background apps in `config.json`, excluding the protected list, whitelist, and Pikabot. Every close needs confirmation. Unknown apps are left alone.
- CRITICAL switches to Windows Power Saver when a real CPU sensor temperature is available and dry run is off. Optional hibernation after 60 seconds of *rising* temperature is disabled by default (`allow_critical_hibernate`). Save work before enabling it.
- The overlay hides over full-screen windows and foreground meeting titles (Zoom, Teams, Google Meet). Title matching is a heuristic; other meeting software can be configured through `meeting_title_keywords`.
- Performance depends on the machine and installed software. Measure it in Task Manager before enabling login startup.

## Art and screenshots

Replace `assets/safe_0.png`, `safe_1.png`, `warm_0.png`, `warm_1.png`, `hot_0.png`, `hot_1.png`, `critical_0.png`, and `critical_1.png` with 88×88 transparent PNGs you have rights to use. The included frames are generated placeholders.

Screenshot placeholder: tray menu. Screenshot placeholder: running character. Screenshot placeholder: HOT confirmation.

## Troubleshooting

- No temperature: confirm LibreHardwareMonitor's web server and URL; some laptops expose no sensor. The app will keep monitoring CPU and RAM without thermal actions.
- No tray icon: check Windows hidden tray icons and that `pystray` and Pillow installed.
- No voice: check the default Windows speech voice and `pyttsx3`; mute and do-not-disturb settings also suppress speech.
- Speech uses the installed Windows voice by default. Set `voice_backend` to `pyttsx3` in `config.json` to try that engine instead; it falls back to Windows speech if initialization fails.
- Access denied: run without admin rights normally; inaccessible processes are skipped and logged in `logs/actions.log`.
- A process returned after closing: some browsers and launchers restart their own workers; Pikabot does not force-kill them.

Future work: better meeting detection, a temperature trend chart, and an opt-in overheating predictor trained on the laptop's own logs.

## Installed verification update

Both `PikabotGuardian` and `PikabotSensor` are registered and running on this laptop. The sensor task needs administrator privileges; registration uses `install.ps1 -SkipDependencies -ElevatedSensor` after explicit approval. Both tasks ignore overlapping starts and permit battery operation. There is one guardian and one sensor process.

Run `./.python/python.exe -m unittest -v test_safety` for safety tests. `test_close_integration.py` creates a disposable window and verifies a real WM_CLOSE request. Real closes now let apps show their save dialogs; apps without a visible window remain running. Undo is recorded only after confirmed exit.

Hibernation is verified using a mocked OS command, not an actual laptop hibernation. Dry run remains enabled, and hibernation remains opt-in. The original 60 MB target applies to the measured guardian process only: LibreHardwareMonitor adds approximately 79 MB and speech can temporarily launch a separate Windows process. The combined system does not meet a 60 MB total-memory limit. Startup registration has been tested, but an actual reboot/login cycle has not been performed.
