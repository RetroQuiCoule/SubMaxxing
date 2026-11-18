"""
Topic Segmenter module for Submaxxing.
Analyzes full interview / talk show / podcast transcriptions with word timestamps,
detects thematic boundaries, extracts viral hooks, and generates chaptered blocks.
Supports both a built-in deterministic semantic engine (0 dependency, instant)
and an optional local/cloud LLM engine (Ollama, LM Studio, OpenAI-compatible APIs).
"""

import os
import re
import json
import urllib.request
import urllib.error
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Tuple, Dict, Any, Set

from styles import WordTiming


VIRAL_KEYWORDS_FR = {
    "secret", "jamais", "incroyable", "fou", "dingue", "vérité", "grave",
    "argent", "succès", "erreur", "problème", "danger", "astuce", "méthode",
    "million", "business", "arnaque", "mensonge", "choc", "découverte",
    "attention", "pire", "meilleur", "urgent", "absolument"
}

VIRAL_KEYWORDS_EN = {
    "secret", "never", "insane", "crazy", "truth", "money", "success",
    "mistake", "problem", "danger", "trick", "method", "million", "business",
    "scam", "lie", "shocking", "worst", "best", "urgent", "absolutely"
}

TOPIC_SHIFT_MARKERS_FR = [
    r"\b(pourquoi|comment|est-ce que|qu'en pensez-vous|qu'est-ce qui)\b",
    r"\b(alors|maintenant|en parlant de|pour en revenir à|passons à|d'ailleurs)\b",
    r"\b(le vrai problème|ce qu'il faut comprendre|la vérité c'est|au fond)\b",
    r"\b(sur la question de|au sujet de|concernant)\b"
]

TOPIC_SHIFT_MARKERS_EN = [
    r"\b(why|how|what do you think|can you explain)\b",
    r"\b(now|speaking of|let's talk about|moving on to|by the way)\b",
    r"\b(the real problem|what people don't get|the truth is)\b"
]


@dataclass
class ThematicBlock:
    id: int
    title: str
    hook: str
    summary: str
    start: float
    end: float
    duration: float
    virality_score: int  # 1 to 10
    key_phrases: List[str] = field(default_factory=list)
    selected: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "hook": self.hook,
            "summary": self.summary,
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "duration": round(self.duration, 3),
            "virality_score": self.virality_score,
            "key_phrases": self.key_phrases,
            "selected": self.selected
        }


def _group_words_into_sentences(word_timings: List[WordTiming]) -> List[Dict[str, Any]]:
    """Groups words into sentences with start, end, and text."""
    if not word_timings:
        return []

    sentences: List[Dict[str, Any]] = []
    current_words: List[WordTiming] = []

    for i, w in enumerate(word_timings):
        current_words.append(w)
        ends_sentence = False

        # Sentence end punctuation
        if any(w.word.endswith(punct) for punct in [".", "!", "?", "…"]):
            ends_sentence = True
        # Or pause > 0.8s to next word
        elif i < len(word_timings) - 1 and (word_timings[i + 1].start - w.end) > 0.8:
            ends_sentence = True
        # Or accumulated length > 20 words
        elif len(current_words) >= 22:
            ends_sentence = True

        if ends_sentence or i == len(word_timings) - 1:
            sent_text = " ".join(wt.word for wt in current_words).strip()
            if sent_text:
                sentences.append({
                    "start": current_words[0].start,
                    "end": current_words[-1].end,
                    "text": sent_text,
                    "word_count": len(current_words),
                    "words": current_words
                })
            current_words = []

    return sentences


def _score_sentence_as_hook(sentence: str, duration: float) -> int:
    """Scores how punchy a sentence is to serve as an opening hook (1 to 10)."""
    score = 4
    lower = sentence.lower()

    # Questions are great hooks
    if "?" in sentence or lower.startswith(("pourquoi", "comment", "est-ce", "why", "how")):
        score += 2

    # Viral / power words
    viral_words = VIRAL_KEYWORDS_FR | VIRAL_KEYWORDS_EN
    tokens = set(re.findall(r"\w+", lower))
    matches = tokens & viral_words
    if matches:
        score += min(3, len(matches) * 2)

    # Exclamation
    if "!" in sentence:
        score += 1

    # Length sweet spot for a hook: 4 to 16 words
    words = sentence.split()
    if 4 <= len(words) <= 15:
        score += 1

    return min(10, max(1, score))


def _extract_title_from_text(text: str, default_idx: int) -> str:
    """Extracts a readable title or topic summary from text."""
    clean = re.sub(r"[^\w\s\u00C0-\u017F]", " ", text)
    words = clean.split()

    # Filter out stopwords
    stopwords = {
        "le", "la", "les", "un", "une", "des", "du", "de", "d", "l",
        "ce", "cette", "ces", "et", "ou", "mais", "donc", "or", "ni", "car",
        "je", "tu", "il", "elle", "on", "nous", "vous", "ils", "elles",
        "que", "qui", "quoi", "dont", "où", "en", "y", "a", "à", "dans", "pour",
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of"
    }
    content_words = [w for w in words if len(w) > 3 and w.lower() not in stopwords]
    if len(content_words) >= 3:
        title_words = content_words[:5]
        return " ".join(title_words).capitalize()

    return f"Moment clé #{default_idx}"


def segment_topics_heuristic(
    word_timings: List[WordTiming],
    video_duration: float,
    min_block_sec: float = 25.0,
    max_block_sec: float = 90.0
) -> List[ThematicBlock]:
    """
    Deterministic rule-based thematic boundary detector.
    Groups sentences into self-contained 25s - 90s blocks, finds the best hook,
    and calculates virality metrics. Runs in ~5ms with zero external dependencies.
    """
    sentences = _group_words_into_sentences(word_timings)
    if not sentences:
        return []

    shift_regex = re.compile("|".join(TOPIC_SHIFT_MARKERS_FR + TOPIC_SHIFT_MARKERS_EN), re.IGNORECASE)

    raw_blocks: List[List[Dict[str, Any]]] = []
    current_block: List[Dict[str, Any]] = []

    for s in sentences:
        if not current_block:
            current_block.append(s)
            continue

        block_start = current_block[0]["start"]
        current_dur = s["end"] - block_start

        # Check for topic break triggers
        is_topic_shift = bool(shift_regex.search(s["text"][:40]))
        has_big_pause = (s["start"] - current_block[-1]["end"]) > 1.2

        if (current_dur >= min_block_sec and (is_topic_shift or has_big_pause)) or current_dur >= max_block_sec:
            raw_blocks.append(current_block)
            current_block = [s]
        else:
            current_block.append(s)

    if current_block:
        # If last block is too short (< 15s) and we already have blocks, merge it with previous
        if raw_blocks and (current_block[-1]["end"] - current_block[0]["start"]) < 15.0:
            raw_blocks[-1].extend(current_block)
        else:
            raw_blocks.append(current_block)

    blocks: List[ThematicBlock] = []

    for idx, blk in enumerate(raw_blocks, start=1):
        b_start = blk[0]["start"]
        b_end = blk[-1]["end"]
        b_dur = b_end - b_start
        full_text = " ".join(s["text"] for s in blk)

        # Find best hook sentence inside block
        best_hook_sent = blk[0]["text"]
        highest_hook_score = 1

        for s in blk[:3]:  # Check first 3 sentences
            h_score = _score_sentence_as_hook(s["text"], s["end"] - s["start"])
            if h_score > highest_hook_score:
                highest_hook_score = h_score
                best_hook_sent = s["text"]

        # Compute block virality score
        # Factors: hook score, word density, presence of questions, viral keywords
        total_words = sum(s["word_count"] for s in blk)
        wpm = (total_words / max(b_dur, 1.0)) * 60.0
        pacing_bonus = 2 if wpm > 130 else 1

        tokens = set(re.findall(r"\w+", full_text.lower()))
        viral_count = len(tokens & (VIRAL_KEYWORDS_FR | VIRAL_KEYWORDS_EN))
        viral_bonus = min(3, viral_count)

        raw_virality = int(round((highest_hook_score * 0.5) + pacing_bonus + viral_bonus))
        virality_score = min(10, max(1, raw_virality))

        # Extract title and summary
        title = _extract_title_from_text(best_hook_sent, idx)
        summary = full_text[:160] + ("..." if len(full_text) > 160 else "")

        blocks.append(ThematicBlock(
            id=idx,
            title=title,
            hook=best_hook_sent,
            summary=summary,
            start=b_start,
            end=b_end,
            duration=b_dur,
            virality_score=virality_score,
            key_phrases=[s["text"] for s in blk[:2]],
            selected=(idx == 1)  # Default select first block
        ))

    return blocks


def segment_topics_llm(
    word_timings: List[WordTiming],
    video_duration: float,
    api_url: str = "http://localhost:11434/v1",
    api_key: Optional[str] = None,
    model_name: str = "llama3.2:3b",
    timeout_sec: int = 25
) -> Optional[List[ThematicBlock]]:
    """
    Segments topics and scores hooks using a local LLM (e.g. Ollama, LM Studio)
    or cloud OpenAI-compatible endpoint. Falls back cleanly to heuristic if unreachable.
    """
    sentences = _group_words_into_sentences(word_timings)
    if not sentences:
        return None

    # Prepare compact transcript with timestamps
    lines = []
    for s in sentences:
        lines.append(f"[{s['start']:.1f}s - {s['end']:.1f}s]: {s['text']}")
    compact_transcript = "\n".join(lines)

    prompt = f"""Tu es un monteur vidéo expert pour TikTok, Reels et Shorts.
Analyse la transcription horodatée ci-dessous d'une interview/discussion et découpe-la en blocs thématiques pertinents (durée idéale par extrait : entre 30s et 90s).

Pour chaque bloc, fournis un objet JSON valide avec :
- "title": Un titre accrocheur de 3 à 6 mots.
- "hook": La phrase d'accroche la plus percutante au début du bloc.
- "summary": Résumé en 1 phrase du sujet abordé.
- "start": Timestamp début exact (en secondes, float).
- "end": Timestamp fin exact (en secondes, float).
- "virality_score": Note d'intérêt de 1 à 10 pour un Short/Reel.

Réponds UNIQUEMENT avec un tableau JSON d'objets, sans texte avant ni après. Exemple :
[
  {{"title": "L'erreur fatale", "hook": "Le vrai problème, c'est...", "summary": "Explication sur...", "start": 12.4, "end": 64.2, "virality_score": 9}}
]

Transcription :
{compact_transcript}
"""

    url = api_url.rstrip("/") + "/chat/completions"
    headers = {
        "Content-Type": "application/json"
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": "Tu es un assistant JSON strict spécialisé dans le montage vidéo."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3
    }

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        content = data["choices"][0]["message"]["content"].strip()
        # Extract JSON array from LLM response
        match = re.search(r"\[.*\]", content, re.DOTALL)
        if match:
            raw_json = match.group(0)
            items = json.loads(raw_json)

            blocks: List[ThematicBlock] = []
            for i, it in enumerate(items, start=1):
                s = float(it.get("start", 0.0))
                e = float(it.get("end", video_duration))
                blocks.append(ThematicBlock(
                    id=i,
                    title=str(it.get("title", f"Thème #{i}")),
                    hook=str(it.get("hook", "")),
                    summary=str(it.get("summary", "")),
                    start=s,
                    end=e,
                    duration=round(e - s, 3),
                    virality_score=int(it.get("virality_score", 7)),
                    selected=(i == 1)
                ))
            if blocks:
                return blocks
    except Exception as e:
        print(f"[!] Info: Moteur LLM ({api_url}) non joignable ({e}), bascule automatique sur l'analyseur heuristique.")

    return None


def segment_topics(
    word_timings: List[WordTiming],
    video_duration: float,
    engine: str = "auto",
    api_url: Optional[str] = None,
    api_key: Optional[str] = None,
    model_name: Optional[str] = None,
    min_block_sec: float = 25.0,
    max_block_sec: float = 90.0
) -> List[ThematicBlock]:
    """
    Main entry point for topic segmentation.
    If engine == 'llm' or engine == 'auto' and local Ollama is active, attempts LLM segmentation.
    Otherwise, uses the deterministic semantic boundary engine.
    """
    if engine in ("llm", "auto") and api_url:
        blocks = segment_topics_llm(
            word_timings=word_timings,
            video_duration=video_duration,
            api_url=api_url,
            api_key=api_key,
            model_name=model_name or "llama3.2:3b"
        )
        if blocks:
            return blocks

    return segment_topics_heuristic(
        word_timings=word_timings,
        video_duration=video_duration,
        min_block_sec=min_block_sec,
        max_block_sec=max_block_sec
    )
