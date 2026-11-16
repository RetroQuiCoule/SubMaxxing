"""
Chunker module for Submaxxing.
Handles splitting long SRT subtitles into bite-sized 1-4 word chunks,
grouping Whisper word-level timestamps into dynamic karaoke chunks,
and intelligently fusing French elisions (c', d', l', j', qu', etc.).
"""

import re
from typing import List, Tuple
from styles import WordTiming, SubChunk

FRENCH_CLITICS = {
    "c'", "d'", "l'", "j'", "m'", "t'", "s'", "n'", "qu'", "jusqu'", "lorsqu'", "puisqu'",
    "c’", "d’", "l’", "j’", "m’", "t’", "s’", "n’", "qu’", "jusqu’", "lorsqu’", "puisqu’"
}

_HTML_TAGS_RE = re.compile(r'<[^>]+>')
_APOSTROPHE_SPACES_RE = re.compile(r"\b([cldjmstnq]|qu|jusqu|lorsqu|puisqu)['’]\s+", re.IGNORECASE)
_WHITESPACE_RE = re.compile(r'\s+')
_SRT_BLOCK_RE = re.compile(r'\n\s*\n')


def parse_srt_timestamp(ts: str) -> float:
    """Converts '00:01:23,456' or '00:01:23.456' into seconds."""
    ts = ts.strip().replace(',', '.')
    parts = ts.split(':')
    if len(parts) == 3:
        h, m, s = parts
        return int(h) * 3600 + int(m) * 60 + float(s)
    elif len(parts) == 2:
        m, s = parts
        return int(m) * 60 + float(s)
    return float(ts)


def clean_subtitle_text(text: str) -> str:
    """Removes HTML tags, heals French apostrophes with spaces, and cleans whitespace."""
    text = _HTML_TAGS_RE.sub('', text)
    # Heal spaces after apostrophes in French (e.g. "c' est" -> "c'est", "d' accord" -> "d'accord")
    text = _APOSTROPHE_SPACES_RE.sub(r"\1'", text)
    text = _WHITESPACE_RE.sub(' ', text).strip()
    return text


def parse_srt(srt_content: str) -> List[Tuple[float, float, str]]:
    """
    Parses SRT content into a list of (start_seconds, end_seconds, text).
    """
    blocks = _SRT_BLOCK_RE.split(srt_content.strip())
    entries = []

    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue

        time_line_idx = -1
        for i, line in enumerate(lines):
            if '-->' in line:
                time_line_idx = i
                break

        if time_line_idx == -1:
            continue

        time_line = lines[time_line_idx]
        parts = time_line.split('-->')
        if len(parts) != 2:
            continue

        try:
            start_sec = parse_srt_timestamp(parts[0])
            end_sec = parse_srt_timestamp(parts[1])
        except ValueError:
            continue

        raw_text = " ".join(lines[time_line_idx + 1:])
        text = clean_subtitle_text(raw_text)
        if text:
            entries.append((start_sec, end_sec, text))

    return entries


def merge_french_elisions(words: List[WordTiming]) -> List[WordTiming]:
    """
    Merges clitics ending with an apostrophe (c', d', l', j', qu', etc.)
    with the subsequent word so they are never split or shown in isolation.
    """
    if not words:
        return []

    merged: List[WordTiming] = []
    i = 0
    n = len(words)

    while i < n:
        curr = words[i]
        curr_text = curr.word.strip()
        curr_lower = curr_text.lower()

        is_clitic = (
            curr_lower in FRENCH_CLITICS or
            curr_text.endswith("'") or
            curr_text.endswith("’") or
            (len(curr_text) <= 3 and ("'" in curr_text or "’" in curr_text) and not curr_text[0].isalnum())
        )

        if is_clitic and (i + 1 < n):
            nxt = words[i + 1]
            glued_text = f"{curr_text}{nxt.word.lstrip()}"
            merged.append(WordTiming(
                word=glued_text,
                start=curr.start,
                end=nxt.end
            ))
            i += 2
        else:
            merged.append(curr)
            i += 1

    return merged


def split_sentence_into_word_timings(start: float, end: float, text: str) -> List[WordTiming]:
    """
    Given a sentence and its start/end time, splits into words
    and estimates timestamps proportionally based on word length.
    """
    words = text.split()
    if not words:
        return []

    duration = max(0.2, end - start)
    weights = [max(1, len(w)) for w in words]
    total_weight = sum(weights)

    timings = []
    current_time = start

    for i, (w, weight) in enumerate(zip(words, weights)):
        w_duration = duration * (weight / total_weight)
        w_start = current_time
        w_end = current_time + w_duration if i < len(words) - 1 else end
        timings.append(WordTiming(word=w, start=w_start, end=w_end))
        current_time = w_end

    # Always ensure clitics are properly merged
    return merge_french_elisions(timings)


def group_words_into_chunks(words: List[WordTiming], max_words: int = 2) -> List[SubChunk]:
    """
    Groups individual WordTiming objects into chunks of up to `max_words`.
    """
    if max_words < 1:
        max_words = 1

    # First merge any remaining elisions
    words = merge_french_elisions(words)

    chunks = []
    for i in range(0, len(words), max_words):
        slice_words = words[i:i + max_words]
        if not slice_words:
            continue
        c_start = slice_words[0].start
        c_end = slice_words[-1].end
        chunks.append(SubChunk(words=slice_words, start=c_start, end=c_end))

    return chunks


def srt_to_chunks(srt_path_or_content: str, max_words: int = 2, is_file: bool = True) -> List[SubChunk]:
    """
    Parses an SRT file or string, slices long sentences into word timings,
    and returns a list of SubChunk objects ready for styling.
    """
    if is_file:
        with open(srt_path_or_content, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
    else:
        content = srt_path_or_content

    entries = parse_srt(content)
    all_chunks = []

    for start, end, text in entries:
        word_timings = split_sentence_into_word_timings(start, end, text)
        chunks = group_words_into_chunks(word_timings, max_words=max_words)
        all_chunks.extend(chunks)

    return all_chunks
