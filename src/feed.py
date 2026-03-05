"""Podcast RSS feed generation."""

import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

# Register namespace prefixes
ET.register_namespace("itunes", "http://www.itunes.com/dtds/podcast-1.0.dtd")
ET.register_namespace("atom", "http://www.w3.org/2005/Atom")
ET.register_namespace("podcast", "https://podcastindex.org/namespace/1.0")


@dataclass
class PodcastConfig:
    """Configuration for the podcast feed."""

    title: str
    description: str
    author: str
    email: str
    language: str
    base_url: str
    image_url: Optional[str] = None


@dataclass
class Episode:
    """Represents a podcast episode."""

    id: str
    title: str
    description: str
    audio_file: str
    published: datetime
    duration_seconds: int
    link: Optional[str] = None
    transcript_url: Optional[str] = None


class FeedGenerator:
    """Generates podcast RSS 2.0 XML feed."""

    ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"
    PODCAST_NS = "https://podcastindex.org/namespace/1.0"

    def __init__(self, config: PodcastConfig):
        self.config = config

    @staticmethod
    def _build_briefing_description(title: str, content: str) -> str:
        """Build a rich description for news briefings with topic bullets."""
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        if len(paragraphs) <= 1:
            return title

        # Skip the first paragraph (date opener) and extract first sentence from each
        bullets = []
        for para in paragraphs[1:]:
            first_sentence = para.split(". ")[0].rstrip(".")
            if first_sentence:
                bullets.append(f"- {first_sentence}")
            if len(bullets) >= 6:
                break

        if not bullets:
            return title

        return f"{title}\n\nTopics covered:\n" + "\n".join(bullets)

    def _get_audio_duration(self, audio_path: Path) -> int:
        """Get duration of audio file in seconds."""
        try:
            import soundfile as sf

            info = sf.info(audio_path)
            return int(info.duration)
        except Exception:
            return 0

    def _get_file_size(self, audio_path: Path) -> int:
        """Get file size in bytes."""
        try:
            return audio_path.stat().st_size
        except Exception:
            return 0

    def _format_duration(self, seconds: int) -> str:
        """Format duration as HH:MM:SS."""
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    def _format_rfc822(self, dt: datetime) -> str:
        """Format datetime as RFC 822."""
        return dt.strftime("%a, %d %b %Y %H:%M:%S +0000")

    def generate(self, episodes: list[Episode], output_path: Path) -> None:
        """Generate the podcast RSS feed XML."""
        ATOM_NS = "http://www.w3.org/2005/Atom"

        # Create root element
        rss = ET.Element("rss")
        rss.set("version", "2.0")

        channel = ET.SubElement(rss, "channel")

        # Channel metadata
        ET.SubElement(channel, "title").text = self.config.title
        ET.SubElement(channel, "description").text = self.config.description
        ET.SubElement(channel, "language").text = self.config.language
        ET.SubElement(channel, "link").text = self.config.base_url

        # Atom self-link
        atom_link = ET.SubElement(channel, f"{{{ATOM_NS}}}link")
        atom_link.set("href", f"{self.config.base_url}/feed.xml")
        atom_link.set("rel", "self")
        atom_link.set("type", "application/rss+xml")

        # iTunes specific tags
        ET.SubElement(channel, f"{{{self.ITUNES_NS}}}author").text = self.config.author
        ET.SubElement(channel, f"{{{self.ITUNES_NS}}}explicit").text = "false"
        ET.SubElement(channel, f"{{{self.ITUNES_NS}}}type").text = "episodic"

        owner = ET.SubElement(channel, f"{{{self.ITUNES_NS}}}owner")
        ET.SubElement(owner, f"{{{self.ITUNES_NS}}}name").text = self.config.author
        ET.SubElement(owner, f"{{{self.ITUNES_NS}}}email").text = self.config.email

        if self.config.image_url:
            image = ET.SubElement(channel, f"{{{self.ITUNES_NS}}}image")
            image.set("href", self.config.image_url)

            # Standard RSS <image> for broader player compatibility
            rss_image = ET.SubElement(channel, "image")
            ET.SubElement(rss_image, "url").text = self.config.image_url
            ET.SubElement(rss_image, "title").text = self.config.title
            ET.SubElement(rss_image, "link").text = self.config.base_url

        # Category
        category = ET.SubElement(channel, f"{{{self.ITUNES_NS}}}category")
        category.set("text", "Technology")

        # Add episodes
        for episode in sorted(episodes, key=lambda e: e.published, reverse=True):
            item = ET.SubElement(channel, "item")

            ET.SubElement(item, "title").text = episode.title
            ET.SubElement(item, "description").text = episode.description
            ET.SubElement(item, "pubDate").text = self._format_rfc822(episode.published)
            ET.SubElement(item, "guid").text = episode.id

            if episode.link:
                ET.SubElement(item, "link").text = episode.link

            # Enclosure (audio file)
            audio_url = f"{self.config.base_url}/audio/{episode.audio_file}"
            enclosure = ET.SubElement(item, "enclosure")
            enclosure.set("url", audio_url)
            # Detect MIME type from file extension
            if episode.audio_file.endswith(".mp3"):
                enclosure.set("type", "audio/mpeg")
            else:
                enclosure.set("type", "audio/wav")
            enclosure.set("length", "0")  # Could compute actual size

            # iTunes episode tags
            ET.SubElement(
                item, f"{{{self.ITUNES_NS}}}duration"
            ).text = self._format_duration(episode.duration_seconds)
            ET.SubElement(item, f"{{{self.ITUNES_NS}}}explicit").text = "false"
            ET.SubElement(item, f"{{{self.ITUNES_NS}}}episodeType").text = "full"

            # Podcast 2.0 transcript
            if episode.transcript_url:
                transcript = ET.SubElement(item, f"{{{self.PODCAST_NS}}}transcript")
                transcript.set("url", episode.transcript_url)
                transcript.set("type", "text/plain")

        # Write to file
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Indent XML (Python 3.9+)
        ET.indent(rss, space="  ")
        tree = ET.ElementTree(rss)
        tree.write(output_path, encoding="utf-8", xml_declaration=True)

    def load_episodes_from_db(
        self, db_entries: list[dict], audio_dir: Path,
        transcript_dir: Optional[Path] = None,
    ) -> list[Episode]:
        """Load episodes from database entries."""
        episodes = []

        for entry in db_entries:
            audio_file = entry.get("audio_file")
            if not audio_file:
                continue

            audio_path = audio_dir / audio_file
            if not audio_path.exists():
                continue

            duration = self._get_audio_duration(audio_path)
            published = datetime.fromisoformat(entry["published"])
            content = entry.get("content", "")
            is_briefing = entry["id"].startswith("news-briefing-")

            # Build description
            if is_briefing and content:
                description = self._build_briefing_description(entry["title"], content)
            else:
                description = f"Audio version of {entry['title']} from {entry['feed_name']}"

            # Write transcript and build URL for news briefings
            transcript_url = None
            if is_briefing and content and transcript_dir:
                transcript_dir.mkdir(parents=True, exist_ok=True)
                transcript_path = transcript_dir / f"{entry['id']}.txt"
                transcript_path.write_text(content, encoding="utf-8")
                transcript_url = f"{self.config.base_url}/transcripts/{entry['id']}.txt"

            episodes.append(
                Episode(
                    id=entry["id"],
                    title=entry["title"],
                    description=description,
                    audio_file=audio_file,
                    published=published,
                    duration_seconds=duration,
                    link=entry.get("link"),
                    transcript_url=transcript_url,
                )
            )

        return episodes
