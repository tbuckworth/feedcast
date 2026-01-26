#!/usr/bin/env python3
"""Helper script to download and extract voice samples for comparison.

This script helps download audio from YouTube and extract clean voice samples.

Usage:
    # Download from YouTube and extract a segment
    uv run python scripts/download_voice_sample.py --url "https://youtube.com/..." --name attenborough --start 10 --duration 8

    # Just extract a segment from an existing file
    uv run python scripts/download_voice_sample.py --input downloaded.wav --name freeman --start 5 --duration 7

Requirements:
    - yt-dlp (for YouTube downloads): pip install yt-dlp
    - ffmpeg (for audio processing): brew install ffmpeg
"""

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path


def check_dependencies():
    """Check if required tools are installed."""
    missing = []

    try:
        subprocess.run(["yt-dlp", "--version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        missing.append("yt-dlp (install with: pip install yt-dlp)")

    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        missing.append("ffmpeg (install with: brew install ffmpeg)")

    if missing:
        print("Missing dependencies:")
        for dep in missing:
            print(f"  - {dep}")
        return False
    return True


def download_audio(url: str, output_path: Path) -> Path:
    """Download audio from YouTube or other supported sites."""
    print(f"Downloading audio from: {url}")

    cmd = [
        "yt-dlp",
        "-x",  # Extract audio
        "--audio-format", "wav",
        "--audio-quality", "0",  # Best quality
        "-o", str(output_path),
        url,
    ]

    subprocess.run(cmd, check=True)

    # yt-dlp might add extension, find the actual file
    wav_path = output_path.with_suffix(".wav")
    if not wav_path.exists():
        # Try finding any audio file with similar name
        for ext in [".wav", ".m4a", ".mp3", ".opus"]:
            candidate = output_path.with_suffix(ext)
            if candidate.exists():
                return candidate
        raise FileNotFoundError(f"Downloaded file not found: {output_path}")

    return wav_path


def extract_segment(
    input_path: Path,
    output_path: Path,
    start_time: float,
    duration: float,
    target_sample_rate: int = 24000,
) -> Path:
    """Extract a segment from an audio file and resample."""
    print(f"Extracting {duration}s segment starting at {start_time}s...")

    cmd = [
        "ffmpeg",
        "-y",  # Overwrite output
        "-i", str(input_path),
        "-ss", str(start_time),
        "-t", str(duration),
        "-ar", str(target_sample_rate),  # Resample to target rate
        "-ac", "1",  # Mono
        str(output_path),
    ]

    subprocess.run(cmd, check=True, capture_output=True)
    print(f"Saved to: {output_path}")
    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Download and extract voice samples for Chatterbox TTS comparison"
    )
    parser.add_argument(
        "--url",
        help="YouTube or other URL to download from",
    )
    parser.add_argument(
        "--input",
        type=Path,
        help="Local audio file to extract from (alternative to --url)",
    )
    parser.add_argument(
        "--name",
        required=True,
        help="Voice name (e.g., 'attenborough', 'freeman')",
    )
    parser.add_argument(
        "--start",
        type=float,
        default=0,
        help="Start time in seconds",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=8,
        help="Duration in seconds (default: 8)",
    )
    parser.add_argument(
        "--list-timestamps",
        action="store_true",
        help="Just download and show duration, don't extract",
    )

    args = parser.parse_args()

    if not args.url and not args.input:
        print("Error: Must provide either --url or --input")
        return 1

    if not check_dependencies():
        return 1

    # Setup paths
    project_root = Path(__file__).parent.parent
    voice_dir = project_root / "voice_samples"
    output_path = voice_dir / f"{args.name}.wav"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Get the input audio
        if args.url:
            input_audio = download_audio(args.url, tmpdir / "downloaded")
        else:
            input_audio = args.input
            if not input_audio.exists():
                print(f"Error: Input file not found: {input_audio}")
                return 1

        if args.list_timestamps:
            # Show file info
            cmd = ["ffprobe", "-i", str(input_audio), "-show_format", "-v", "quiet"]
            result = subprocess.run(cmd, capture_output=True, text=True)
            print("File info:")
            print(result.stdout)
            print("\nListen to the file and note good timestamps for extraction.")
            return 0

        # Extract the segment
        extract_segment(
            input_audio,
            output_path,
            args.start,
            args.duration,
        )

    print(f"\nVoice sample saved: {output_path}")
    print(f"\nRun comparison with: uv run python scripts/compare_voices.py")

    return 0


if __name__ == "__main__":
    sys.exit(main())
