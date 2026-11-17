"""
Chunker module for Submaxxing.
Handles splitting long SRT subtitles into bite-sized 1-4 word chunks,
grouping Whisper word-level timestamps into dynamic karaoke chunks with speech rhythm awareness,
and intelligently fusing French elisions (c', d', l', j', qu', etc.) and English contractions.
"""

import re
from typing import List, Tuple
from styles import WordTiming, SubChunk

FRENCH_CLITICS_NO_APOS = {
    "c", "d", "l", "j", "m", "t", "s", "n", "qu", "jusqu", "lorsqu", "puisqu"
}

FRENCH_CLITICS_WITH_APOS = {
    "c'", "d'", "l'", "j'", "m'", "t'", "s'", "n'", "qu'", "jusqu'", "lorsqu'", "puisqu'",
    "c’", "d’", "l’", "j’", "m’", "t’", "s’", "n’", "qu’", "jusqu’", "lorsqu’", "puisqu’"
}

FRENCH_CLITICS = FRENCH_CLITICS_WITH_APOS

ENGLISH_CONTRACTIONS = {"t", "s", "m", "re", "ve", "ll", "d"}
ENGLISH_CONTRACTION_BASES = {
    "don", "doesn", "didn", "isn", "aren", "wasn", "weren", "haven", "hasn", "hadn",
    "won", "wouldn", "can", "couldn", "shouldn", "mustn",
    "it", "i", "you", "he", "she", "we", "they", "that", "what", "there", "who", "let"
}

_HTML_TAGS_RE = re.compile(r'<[^>]+>')
_APOSTROPHE_SPACES_RE = re.compile(r"\b([cldjmstnq]|qu|jusqu|lorsqu|puisqu)['’]\s+", re.IGNORECASE)
_WHITESPACE_RE = re.compile(r'\s+')
_SRT_BLOCK_RE = re.compile(r'\n\s*\n')
_PUNCT_ONLY_RE = re.compile(r'^[^\w\s]+$')
_VOWELS = set("aeiouyéèêëàâîïôûùœæAEIOUYÉÈÊËÀÂÎÏÔÛÙŒÆ")


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
    Intelligently merges clitics and contractions in French, English, and general speech.
    Fixes Whisper's tokenization splitting:
      - French: ' d' + "'autant" -> "d'autant", ' l' + "'alignation" -> "l'alignation", ' c' + "'est" -> "c'est"
      - English: ' don' + "'t" -> "don't", ' it' + "'s" -> "it's", ' I' + "'m" -> "I'm"
      - Stray punctuation tokens: attached to preceding word instead of standing alone.
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

        if not curr_text:
            i += 1
            continue

        # If current token is pure punctuation (e.g. standalone "," or "."), attach to previous word
        if _PUNCT_ONLY_RE.match(curr_text) and curr_text not in {"'", "’"}:
            if merged:
                prev = merged[-1]
                prev.word = f"{prev.word}{curr_text}"
                prev.end = max(prev.end, curr.end)
            i += 1
            continue

        if i + 1 < n:
            nxt = words[i + 1]
            nxt_text = nxt.word.strip()
            nxt_lower = nxt_text.lower()

            # Case 1: nxt starts with apostrophe (e.g. "'autant", "'alignation", "'est", "'t", "'s", "'re")
            if nxt_text.startswith("'") or nxt_text.startswith("’"):
                glued_text = f"{curr_text}{nxt_text}"
                merged.append(WordTiming(
                    word=glued_text,
                    start=curr.start,
                    end=nxt.end
                ))
                i += 2
                continue

            # Case 2: curr ends with apostrophe (e.g. "d'", "l'", "c'", "qu'", "don'")
            if curr_text.endswith("'") or curr_text.endswith("’"):
                glued_text = f"{curr_text}{nxt_text.lstrip()}"
                merged.append(WordTiming(
                    word=glued_text,
                    start=curr.start,
                    end=nxt.end
                ))
                i += 2
                continue

            # Case 3: curr is a French clitic without apostrophe before next word (e.g. "d" + "accord" -> "d'accord")
            if curr_lower in FRENCH_CLITICS_NO_APOS and (nxt_text and (nxt_text[0] in _VOWELS or nxt_text[0].lower() == 'h')):
                glued_text = f"{curr_text}'{nxt_text.lstrip()}"
                merged.append(WordTiming(
                    word=glued_text,
                    start=curr.start,
                    end=nxt.end
                ))
                i += 2
                continue

            # Case 4: English contraction without apostrophe token (e.g. "don" + "t" -> "don't", "it" + "s" -> "it's")
            if nxt_lower in ENGLISH_CONTRACTIONS and (curr_lower.endswith("n") or curr_lower in ENGLISH_CONTRACTION_BASES):
                glued_text = f"{curr_text}'{nxt_text}"
                merged.append(WordTiming(
                    word=glued_text,
                    start=curr.start,
                    end=nxt.end
                ))
                i += 2
                continue

            # Case 5: nxt is standalone apostrophe token, followed by word (e.g. "d" + "'" + "accord")
            if nxt_text in {"'", "’"} and i + 2 < n:
                after = words[i + 2]
                glued_text = f"{curr_text}'{after.word.strip()}"
                merged.append(WordTiming(
                    word=glued_text,
                    start=curr.start,
                    end=after.end
                ))
                i += 3
                continue

        merged.append(curr)
        i += 1

    return merged


# Alias for backward compatibility
merge_word_tokens = merge_french_elisions


def split_sentence_into_word_timings(start: float, end: float, text: str) -> List[WordTiming]:
    """
    Given a sentence and its start/end time, splits into words.
    Uses syllable/phonetic weighting and punctuation pauses rather than crude character counts,
    yielding significantly more natural timing that respects speaker pacing.
    """
    words = text.split()
    if not words:
        return []

    if len(words) == 1:
        return [WordTiming(word=words[0], start=start, end=end)]

    total_duration = max(0.2, end - start)

    # Phonetic syllable weighting: vowels carry vocal duration in speech
    weights = []
    for w in words:
        clean = w.strip('.,!?:;"\'()[]')
        vowels = sum(1 for c in clean if c in _VOWELS)
        w_weight = max(1.0, vowels * 1.8 + len(clean) * 0.4)

        # Clause punctuation adds perceived pause weight
        if any(w.endswith(p) for p in (',', ';')):
            w_weight += 0.8
        elif any(w.endswith(p) for p in ('.', '!', '?', ':', '…')):
            w_weight += 1.2

        weights.append(w_weight)

    total_weight = sum(weights)
    timings: List[WordTiming] = []
    current_time = start

    for i, (w, weight) in enumerate(zip(words, weights)):
        w_duration = total_duration * (weight / total_weight)
        w_start = current_time
        w_end = current_time + w_duration if i < len(words) - 1 else end
        timings.append(WordTiming(word=w, start=w_start, end=w_end))
        current_time = w_end

    return merge_french_elisions(timings)


def group_words_into_chunks(words: List[WordTiming], max_words: int = 2, pause_threshold: float = 0.35) -> List[SubChunk]:
    """
    Groups individual WordTiming objects into dynamic chunks of up to `max_words`.
    Crucially respects speech rhythm and acoustic pauses:
      - Ends chunk at sentence punctuation (. ! ? : …)
      - Ends chunk when there is a speech pause (gap >= pause_threshold)
      - Ends chunk at clause boundaries (comma with gap >= 0.15s)
      - Enforces max words and duration limits for punchy TikTok readability.
    """
    if not words:
        return []

    if max_words < 1:
        max_words = 1

    # First merge any remaining elisions/contractions
    words = merge_french_elisions(words)

    chunks: List[SubChunk] = []
    current_words: List[WordTiming] = []
    max_chunk_sec = 2.4 if max_words <= 2 else 3.5

    for i, w in enumerate(words):
        current_words.append(w)
        end_chunk = False

        # 1. Reached max words
        if len(current_words) >= max_words:
            end_chunk = True

        # 2. Punctuation ending a sentence or thought
        w_clean = w.word.rstrip(' \t\n\r"\'”’')
        if any(w_clean.endswith(p) for p in ('.', '!', '?', ':', ';', '…')):
            end_chunk = True

        # 3. Pause before next word (speaker took a breath or hesitated)
        if i + 1 < len(words):
            next_w = words[i + 1]
            gap = next_w.start - w.end
            if gap >= pause_threshold:
                end_chunk = True
            elif any(w_clean.endswith(p) for p in (',', ';')) and gap >= 0.15:
                end_chunk = True
        else:
            # Last word overall
            end_chunk = True

        # 4. Total chunk duration safeguard
        chunk_dur = current_words[-1].end - current_words[0].start
        if chunk_dur >= max_chunk_sec:
            end_chunk = True

        if end_chunk and current_words:
            c_start = current_words[0].start
            c_end = current_words[-1].end
            chunks.append(SubChunk(words=list(current_words), start=c_start, end=c_end))
            current_words = []

    if current_words:
        chunks.append(SubChunk(words=current_words, start=current_words[0].start, end=current_words[-1].end))

    return chunks


def srt_to_chunks(srt_path_or_content: str, max_words: int = 2, is_file: bool = True) -> List[SubChunk]:
    """
    Parses an SRT file or string, extracts or estimates word timings with rhythm awareness,
    and returns a list of SubChunk objects ready for styling.
    Each SRT entry is processed independently so chunks never inappropriately bleed across distinct subtitle blocks.
    """
    if is_file:
        with open(srt_path_or_content, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
    else:
        content = srt_path_or_content

    entries = parse_srt(content)
    all_chunks: List[SubChunk] = []

    for start, end, text in entries:
        raw_words = text.split()
        if not raw_words:
            continue

        timings = split_sentence_into_word_timings(start, end, text)
        entry_chunks = group_words_into_chunks(timings, max_words=max_words)
        all_chunks.extend(entry_chunks)

    return all_chunks
