Voice Samples Directory
=======================

Place WAV files here for voice comparison. Each file should be:
- 5-10 seconds of clean speech
- No background music or noise
- Single speaker
- 24kHz+ sample rate preferred

Expected files:
---------------
attenborough.wav  - David Attenborough (British, nature documentary)
pacey.wav         - Steven Pacey (British, audiobook narrator)
freeman.wav       - Morgan Freeman (American, deep authoritative)
jones.wav         - James Earl Jones (American, iconic voice)
coyote.wav        - Peter Coyote (American, documentary narrator)
vance.wav         - Simon Vance (British, Audie Award winner)
perkins.wav       - Derek Perkins (British, intellectual/poetic)
fry.wav           - Stephen Fry (British, warm authoritative)

Sample Sources:
---------------
- SoundCloud clips
- Audible audiobook samples
- YouTube documentary clips
- Voicy soundboards

Tools for extraction:
---------------------
- yt-dlp: Download audio from YouTube
- Audacity: Trim and clean audio segments
- ffmpeg: Convert formats

Run comparison:
---------------
uv run python scripts/compare_voices.py

Output will be saved to voice_samples/output/
