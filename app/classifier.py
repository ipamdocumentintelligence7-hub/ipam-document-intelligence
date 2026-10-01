"""
classifier.py - Automatic document classification + Explainable AI (LIME).

Model: TF-IDF features + Logistic Regression (a simple, fast, well-understood model).
Explainability: LIME shows which words pushed the document toward its category.
If LIME is not installed, exact word contributions from the linear model are shown instead.
"""
import csv
import pickle
import sys
from datetime import datetime

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

from . import config

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))
MAX_CHARS = 6000


def load_seed_data():
    texts, labels = [], []
    with open(config.SEED_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            texts.append(row["text"])
            labels.append(row["category"])
    return texts, labels


def build_pipeline():
    return Pipeline([
        ("tfidf", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, stop_words="english", min_df=1)),
        ("clf", LogisticRegression(max_iter=2000, C=8.0)),
    ])


class DocClassifier:
    def __init__(self):
        self.pipe = None
        self.meta = {}
        self.path = config.MODEL_DIR / "classifier.pkl"

    def load(self) -> bool:
        if self.path.exists():
            try:
                with open(self.path, "rb") as f:
                    saved = pickle.load(f)
                self.pipe, self.meta = saved["pipe"], saved["meta"]
                return True
            except Exception:
                return False
        return False

    def train(self, texts, labels):
        texts = [t[:MAX_CHARS] for t in texts]
        meta = {"samples": len(texts), "classes": sorted(set(labels)),
                "trained_at": datetime.now().strftime("%Y-%m-%d %H:%M")}
        counts = {c: labels.count(c) for c in set(labels)}
        if len(texts) >= 40 and min(counts.values()) >= 4:
            xtr, xte, ytr, yte = train_test_split(texts, labels, test_size=0.2, random_state=42, stratify=labels)
            probe = build_pipeline().fit(xtr, ytr)
            pred = probe.predict(xte)
            meta["holdout_accuracy"] = round(float(accuracy_score(yte, pred)), 4)
            meta["holdout_macro_f1"] = round(float(f1_score(yte, pred, average="macro")), 4)
        self.pipe = build_pipeline().fit(texts, labels)      # final model uses ALL the data
        self.meta = meta
        config.MODEL_DIR.mkdir(parents=True, exist_ok=True)
        with open(self.path, "wb") as f:
            pickle.dump({"pipe": self.pipe, "meta": meta}, f)
        return meta

    @property
    def classes(self):
        return [str(c) for c in self.pipe.classes_]

    def predict(self, text):
        probs = self.pipe.predict_proba([text[:MAX_CHARS]])[0]
        order = np.argsort(probs)[::-1]
        return {"category": self.classes[order[0]], "confidence": float(probs[order[0]]),
                "probabilities": {self.classes[i]: round(float(probs[i]), 4) for i in order}}

    def explain(self, text, label, top_n=12):
        """Return the words that most influenced the decision for `label`."""
        text = text[:MAX_CHARS]
        try:
            from lime.lime_text import LimeTextExplainer
            idx = self.classes.index(label)
            explainer = LimeTextExplainer(class_names=self.classes, random_state=7)
            exp = explainer.explain_instance(text, self.pipe.predict_proba, labels=(idx,),
                                             num_features=top_n, num_samples=500)
            feats = [{"word": w, "weight": round(float(v), 4)} for w, v in exp.as_list(label=idx)]
            return {"method": "LIME", "label": label, "features": feats}
        except Exception:
            return self._linear_explain(text, label, top_n)

    def _linear_explain(self, text, label, top_n):
        tfidf, clf = self.pipe.named_steps["tfidf"], self.pipe.named_steps["clf"]
        x = tfidf.transform([text])
        idx = self.classes.index(label)
        names = tfidf.get_feature_names_out()
        contrib = x.multiply(clf.coef_[idx]).tocoo()
        pairs = sorted(zip(contrib.col, contrib.data), key=lambda p: -abs(p[1]))[:top_n]
        feats = [{"word": names[c], "weight": round(float(v), 4)} for c, v in pairs]
        return {"method": "Linear word contributions (LIME not installed)", "label": label, "features": feats}
