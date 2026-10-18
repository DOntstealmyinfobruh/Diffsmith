import re
from collections import Counter

WORD = re.compile(r"[A-Za-z']+")


def words(text):
    return WORD.findall(text)


def word_count(text):
    return len(words(text))


def top_words(text, n=3):
    counts = Counter(w.lower() for w in words(text))
    return [w for w, _ in counts.most_common(n)]


def reading_time_minutes(text, wpm=200):
    return max(1, round(word_count(text) / wpm))
