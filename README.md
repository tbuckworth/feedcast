# Feedcast

A tool that converts RSS feeds to podcast audio. Monitors blogs, summarizes posts with Claude, generates audio with Kokoro TTS, and publishes to a podcast RSS feed.

## Features

- **RSS Monitoring**: Track multiple RSS feeds, detect new posts
- **Content Processing**: Summarize with Claude or use verbatim text
- **TTS Generation**: High-quality audio via Kokoro TTS
- **Podcast Feed**: Valid RSS 2.0 with iTunes tags
- **Automated**: GitHub Actions for daily updates

## Setup

### Prerequisites

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) package manager
- `espeak-ng` system package (for Kokoro TTS)

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/feedcast.git
cd feedcast

# Install dependencies
uv sync

# Copy environment file and add your API key
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY
```

### Configuration

Edit `config.yaml` to configure:

- **podcast**: Metadata for your podcast feed
- **tts**: Voice and speed settings
- **default_prompt**: Summarization prompt for Claude
- **feeds**: List of RSS feeds to monitor

```yaml
feeds:
  - name: "Blog Name"
    url: "https://example.com/feed"
    mode: "summarize"  # or "verbatim"
    prompt: null  # uses default_prompt, or specify custom
```

## Usage

### Run Locally

```bash
uv run python -m src.main
```

This will:
1. Fetch new posts from configured feeds
2. Process content (summarize or clean)
3. Generate audio files
4. Update the podcast RSS feed

### GitHub Actions

The included workflow runs daily at 8am UTC. To enable:

1. Push to GitHub
2. Add `ANTHROPIC_API_KEY` to repository secrets
3. Enable GitHub Pages on the `main` branch, `/output` folder

Your podcast will be available at:
`https://<username>.github.io/feedcast/feed.xml`

## Project Structure

```
feedcast/
├── src/
│   ├── monitor.py      # RSS feed monitoring
│   ├── processor.py    # Content processing (Claude API)
│   ├── audio.py        # TTS generation (Kokoro)
│   ├── feed.py         # Podcast RSS generation
│   └── main.py         # Entry point
├── config.yaml         # Feed configuration
├── data/
│   ├── posts.db        # SQLite - tracks processed posts
│   └── audio/          # Generated audio files
├── output/
│   └── feed.xml        # Generated podcast RSS feed
└── .github/workflows/  # GitHub Actions
```

## TTS Voices

Available Kokoro voices:
- `bm_george` (British male) - default
- `bm_daniel` (British male)
- `bm_fable` (British male)
- `bm_lewis` (British male)
- `af_*` (American female)
- `am_*` (American male)

## License

MIT
