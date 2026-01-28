#!/usr/bin/env bash
# Test voice cloning at various text lengths to establish baseline.
# Run locally, then listen to each output with: afplay <file>
set -euo pipefail

cd "$(dirname "$0")/.."

# Load env
set -a && source .env && set +a

echo "=== Test 1: Short text (31 chars) ==="
uv run python -c "
from pathlib import Path
from src.audio import AudioGenerator
gen = AudioGenerator()
gen.generate('This is a short test.', Path('test_short.mp3'))
print('Done: test_short.mp3')
"

echo ""
echo "=== Test 2: Medium text (~370 chars) ==="
uv run python -c "
from pathlib import Path
from src.audio import AudioGenerator
text = '''Voice cloning technology has advanced significantly in recent years. \
Modern systems can capture the nuances of a speaker's voice from just a few \
seconds of audio. This enables natural-sounding text-to-speech that maintains \
the original speaker's characteristics including tone, pace, and inflection. \
The results can be remarkably convincing, though quality varies by provider.'''
gen = AudioGenerator()
gen.generate(text, Path('test_medium.mp3'))
print('Done: test_medium.mp3')
"

echo ""
echo "=== Test 3: Long text (~1400 chars, near chunk limit) ==="
uv run python -c "
from pathlib import Path
from src.audio import AudioGenerator
text = '''The history of artificial intelligence is a fascinating journey through \
decades of ambitious research and unexpected breakthroughs. In the 1950s, pioneers \
like Alan Turing and John McCarthy laid the theoretical foundations for what would \
become one of the most transformative technologies of the modern era. Early AI \
systems were rule-based, relying on explicit programming to make decisions. These \
systems showed promise in narrow domains like chess and theorem proving, but they \
struggled with the kind of flexible reasoning that comes naturally to humans. \
The field experienced several winters, periods of reduced funding and interest, \
when the gap between AI promises and AI reality became too wide to ignore. But \
each winter was followed by a spring. The neural network revolution of the 2010s, \
powered by deep learning and massive datasets, brought AI into everyday life. \
Image recognition, natural language processing, and game-playing systems achieved \
superhuman performance. Today we stand at another inflection point, with large \
language models demonstrating capabilities that surprise even their creators. \
The question is no longer whether AI can match human intelligence in specific \
domains, but how broadly these capabilities will extend and what implications \
they hold for society.'''
gen = AudioGenerator()
gen.generate(text, Path('test_long.mp3'))
print('Done: test_long.mp3')
"

echo ""
echo "=== Test 4: Multi-chunk text (~3000 chars, forces chunking) ==="
uv run python -c "
from pathlib import Path
from src.audio import AudioGenerator
text = '''The story of computing begins long before electronic computers existed. \
Ancient civilizations used abacuses and mechanical devices to perform calculations. \
In the 17th century, Blaise Pascal and Gottfried Wilhelm Leibniz built some of the \
first mechanical calculators. Charles Babbage designed the Analytical Engine in the \
1830s, a remarkable vision of a general-purpose computer that was never fully built \
during his lifetime. Ada Lovelace, working with Babbage, wrote what many consider \
the first computer program. \
\
The 20th century brought electronic computing into reality. Alan Turing formalized \
the concept of computation with his theoretical Turing machine in 1936. During World \
War Two, the need to break enemy codes accelerated computer development. The Colossus \
machines at Bletchley Park and the ENIAC at the University of Pennsylvania were among \
the first electronic computers. These room-sized machines used thousands of vacuum \
tubes and consumed enormous amounts of power. \
\
The invention of the transistor in 1947 at Bell Labs changed everything. Transistors \
were smaller, faster, more reliable, and consumed less power than vacuum tubes. This \
led to the second generation of computers in the late 1950s and 1960s. The integrated \
circuit, developed independently by Jack Kilby and Robert Noyce, put multiple \
transistors on a single chip, enabling further miniaturization. \
\
The personal computer revolution of the 1970s and 1980s brought computing to homes \
and offices. Companies like Apple, IBM, and Microsoft made computers accessible to \
ordinary people. The graphical user interface, popularized by the Macintosh in 1984, \
made computers intuitive to use. The internet, which grew from a military research \
network called ARPANET, connected these personal computers into a global network. \
\
The World Wide Web, invented by Tim Berners-Lee in 1989, transformed the internet \
from a text-based system used mainly by academics and military personnel into a \
multimedia platform accessible to everyone. The dot-com boom of the late 1990s saw \
explosive growth in internet businesses. While the bubble burst in 2000, the \
underlying technology continued to advance. Social media, smartphones, cloud computing, \
and artificial intelligence have since reshaped how we work, communicate, and live. \
The pace of change shows no signs of slowing down.'''
gen = AudioGenerator()
gen.generate(text, Path('test_multichunk.mp3'))
print('Done: test_multichunk.mp3')
"

echo ""
echo "=== All tests complete ==="
echo "Listen to outputs:"
echo "  afplay test_short.mp3"
echo "  afplay test_medium.mp3"
echo "  afplay test_long.mp3"
echo "  afplay test_multichunk.mp3"
