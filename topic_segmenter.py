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


def _score_sentence_editorial(sentence: Dict[str, Any]) -> int:
    """Computes an editorial virality score for a sentence."""
    txt = sentence["text"]
    lower = txt.lower()
    score = 0

    # 1. Questions or strong topic shifts
    if "?" in txt or lower.startswith(("pourquoi", "comment", "est-ce", "qu'est-ce", "qui", "quand")):
        score += 5
    if "!" in txt:
        score += 3

    shift_regex = re.compile("|".join(TOPIC_SHIFT_MARKERS_FR + TOPIC_SHIFT_MARKERS_EN), re.IGNORECASE)
    if bool(shift_regex.search(txt[:50])):
        score += 4

    # 2. Viral keywords
    viral_words = VIRAL_KEYWORDS_FR | VIRAL_KEYWORDS_EN
    tokens = set(re.findall(r"\w+", lower))
    matches = tokens & viral_words
    score += len(matches) * 3

    # 3. Capitalized named entities (people, countries, organizations)
    cap_words = [
        w for w in txt.split()
        if w and w[0].isupper() and w.lower() not in {
            "le", "la", "les", "ce", "cette", "un", "une", "c'est", "il", "elle", "on", "nous", "vous", "je", "tu"
        }
    ]
    score += min(5, len(cap_words) * 2)

    # 4. Penalty for repetitive filler words
    filler_tokens = {"bonjour", "voila", "oui", "d'accord", "merci", "euh", "hein"}
    filler_count = sum(1 for t in tokens if t in filler_tokens)
    if filler_count >= 2:
        score -= 4

    return score


def segment_topics_heuristic(
    word_timings: List[WordTiming],
    video_duration: float,
    min_block_sec: float = 25.0,
    max_block_sec: float = 75.0,
    max_highlights: int = 5
) -> List[ThematicBlock]:
    """
    Intelligent Viral Highlight Detector (Opus Clip / Klap style).
    Extracts the 3 to 5 most punchy, pertinent moments (the gems)
    rather than dumb sequential end-to-end slicing.
    Boring moments and transition chatter between highlights are cleanly excluded.
    """
    sentences = _group_words_into_sentences(word_timings)
    if not sentences:
        return []

    if video_duration <= 75.0 or len(sentences) <= 3:
        # Video is short enough to be a single standalone clip
        full_text = " ".join(s["text"] for s in sentences)
        hook = sentences[0]["text"]
        return [ThematicBlock(
            id=1,
            title=_extract_title_from_text(hook, 1),
            hook=hook,
            summary=full_text[:160] + ("..." if len(full_text) > 160 else ""),
            start=round(sentences[0]["start"], 2),
            end=round(sentences[-1]["end"], 2),
            duration=round(sentences[-1]["end"] - sentences[0]["start"], 2),
            virality_score=8,
            key_phrases=[s["text"] for s in sentences[:2]],
            selected=True
        )]

    # 1. Score each sentence for editorial punch
    scored_sentences = []
    for s in sentences:
        ed_score = _score_sentence_editorial(s)
        scored_sentences.append({
            **s,
            "ed_score": ed_score
        })

    num_s = len(scored_sentences)
    candidates = []

    # 2. Window search for high-density highlights starting on strong hooks
    for i in range(num_s):
        s_start = scored_sentences[i]
        # Only start on sentences with real editorial impact
        if s_start["ed_score"] < 3:
            continue

        start_time = s_start["start"]
        accum_words = 0
        window_sents = []

        for j in range(i, num_s):
            s_curr = scored_sentences[j]
            window_sents.append(s_curr)
            accum_words += s_curr["word_count"]
            cur_dur = s_curr["end"] - start_time

            if cur_dur > max_block_sec:
                break

            if cur_dur >= min_block_sec:
                # Clean boundary check
                ends_clean = any(s_curr["text"].rstrip().endswith(p) for p in ('.', '!', '?', '…', ':'))
                has_next_pause = (j < num_s - 1 and (scored_sentences[j + 1]["start"] - s_curr["end"]) >= 0.5)

                if ends_clean or has_next_pause or cur_dur >= (max_block_sec - 8):
                    avg_density = sum(s["ed_score"] for s in window_sents) / len(window_sents)
                    hook_bonus = s_start["ed_score"] * 1.5

                    # Word rate bonus (lively speech)
                    wpm = (accum_words / max(cur_dur, 1.0)) * 60.0
                    wpm_bonus = min(2.5, max(0.0, (wpm - 100) / 30.0))

                    # Duration sweet spot (35s to 65s)
                    dur_fit = 2.0 if 35.0 <= cur_dur <= 65.0 else 0.5

                    total_score = hook_bonus + (avg_density * 2.0) + wpm_bonus + dur_fit
                    candidates.append({
                        "start": start_time,
                        "end": s_curr["end"],
                        "duration": cur_dur,
                        "score": total_score,
                        "hook": s_start["text"],
                        "full_text": " ".join(s["text"] for s in window_sents),
                        "sentences": window_sents
                    })

    # Fallback if no candidate meets strict threshold
    if not candidates:
        for i in range(0, num_s, max(1, num_s // 4)):
            start_time = scored_sentences[i]["start"]
            for j in range(i, num_s):
                cur_dur = scored_sentences[j]["end"] - start_time
                if min_block_sec <= cur_dur <= max_block_sec:
                    w_s = scored_sentences[i:j+1]
                    candidates.append({
                        "start": start_time,
                        "end": scored_sentences[j]["end"],
                        "duration": cur_dur,
                        "score": 5.0,
                        "hook": scored_sentences[i]["text"],
                        "full_text": " ".join(s["text"] for s in w_s),
                        "sentences": w_s
                    })
                    break

    # 3. Non-Maximum Suppression (NMS) to select top distinct highlights
    candidates.sort(key=lambda c: c["score"], reverse=True)
    selected_candidates = []

    for cand in candidates:
        overlap = False
        for sel in selected_candidates:
            ov_start = max(cand["start"], sel["start"])
            ov_end = min(cand["end"], sel["end"])
            if ov_end > ov_start:
                ov_dur = ov_end - ov_start
                # Exclude if overlap is more than 8 seconds or 15%
                if ov_dur > 8.0 or (ov_dur / min(cand["duration"], sel["duration"])) > 0.15:
                    overlap = True
                    break
        if not overlap:
            selected_candidates.append(cand)
            if len(selected_candidates) >= max_highlights:
                break

    # 4. Build ThematicBlocks ranked by virality
    blocks: List[ThematicBlock] = []
    for rank, c in enumerate(selected_candidates, start=1):
        raw_v = int(round(c["score"] * 0.35))
        virality_score = min(10, max(6, raw_v))
        if rank == 1 and virality_score < 9:
            virality_score = 9
        elif rank == 2 and virality_score < 8:
            virality_score = 8

        title = _extract_title_from_text(c["hook"], rank)
        summary = c["full_text"][:160] + ("..." if len(c["full_text"]) > 160 else "")

        blocks.append(ThematicBlock(
            id=rank,
            title=title,
            hook=c["hook"],
            summary=summary,
            start=round(c["start"], 2),
            end=round(c["end"], 2),
            duration=round(c["duration"], 2),
            virality_score=virality_score,
            key_phrases=[s["text"] for s in c["sentences"][:2]],
            selected=(rank == 1)
        ))

    return blocks


def segment_topics_llm(
    word_timings: List[WordTiming],
    video_duration: float,
    api_url: str = "http://localhost:11434/v1",
    api_key: Optional[str] = None,
    model_name: str = "qwen3.5:4b",
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

    prompt = f"""Tu es un monteur vidéo d'élite spécialisé dans les formats courts ultra-viraux (TikTok, Reels, Shorts).
Voici la transcription horodatée d'une émission / interview :

OBJECTIF :
Extraire UNIQUEMENT les 3 à 5 MEILLEURS extraits viraux (les pépites / moments forts).

DIRECTIVES STRICTES :
1. NE DÉCOUPE PAS toute la vidéo chronologiquement bout à bout ! Ne fais AUCUN découpage continu !
2. Ignore complètement les moments mous, transitions banales, présentations et bavardages sans enjeu.
3. Chaque extrait retenu doit être une pépite autonome (débat tendu, révélation choc, punchline, question cruciale) :
   - Commence par une accroche percutante ("hook").
   - Dure entre 30s et 75s (grand maximum 90s).
   - Se termine sur une conclusion nette.
4. Note chaque extrait avec un "virality_score" de 1 à 10 et classe les plus forts en premier.

Format de réponse : UNIQUEMENT un tableau JSON valide sans texte avant ni après.
Exemple :
[
  {{"title": "Le coup de gueule", "hook": "La vérité c'est que...", "summary": "Explication sur...", "start": 45.2, "end": 98.4, "virality_score": 9}}
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
            model_name=model_name or "qwen3.5:4b"
        )
        if blocks:
            return blocks

    return segment_topics_heuristic(
        word_timings=word_timings,
        video_duration=video_duration,
        min_block_sec=min_block_sec,
        max_block_sec=max_block_sec
    )
