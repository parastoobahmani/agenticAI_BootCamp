"""سند: مسئله ۱ بخش ۱؛ TF-IDF محلی بدون NumPy و بدون هزینهٔ API."""
import json
import math
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def words(text):
    return re.findall(r'[a-z0-9_]+|[\u0600-\u06ff]+', text.lower())


class Search:
    def __init__(self, path=ROOT / 'data/knowledge.json'):
        self.chunks = []
        for source in json.loads(Path(path).read_text(encoding='utf-8')):
            tokens = source['text'].split()
            for start in range(0, len(tokens), 150):  # 180 کلمه؛ همپوشانی 30
                self.chunks.append({**source, 'chunk_id': source['id'] + ':' + str(start),
                                    'text': ' '.join(tokens[start:start + 180])})
        counts = [Counter(words(c['title'] + ' ' + c['section'] + ' ' + c['text'])) for c in self.chunks]
        df = Counter(term for count in counts for term in count)
        self.idf = {w: math.log((len(counts) + 1) / (n + 1)) + 1 for w, n in df.items()}
        self.vectors = [self.vector(c) for c in counts]

    def vector(self, count):
        vec = {w: (1 + math.log(n)) * self.idf[w] for w, n in count.items() if w in self.idf}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1
        return {w: v / norm for w, v in vec.items()}

    def search(self, query, k=4, baseline=False):
        q = self.vector(Counter(words(query)))
        scored = []
        for chunk, vec in zip(self.chunks, self.vectors):
            score = sum(v * vec.get(w, 0) for w, v in q.items())
            if not baseline and chunk['kind'] == 'docs':
                score *= 1.15  # سند رسمی اولویت اندکی دارد، نه تضمین درستی.
            if score > 0:
                scored.append((score, chunk))
        result, seen = [], set()
        for score, chunk in sorted(scored, key=lambda x: x[0], reverse=True):
            if not baseline and chunk['id'] in seen:
                continue
            seen.add(chunk['id'])
            result.append({**chunk, 'score': round(score, 4)})
            if len(result) == k:
                break
        return result
