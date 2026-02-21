"""
Load the TF-IDF model trained on the query dataset and use it to predict the intent of a query.
"""
from __future__ import annotations

from pathlib import Path
from typing import Tuple

import joblib

MODEL_PATH = Path(__file__).with_name("model_query_tfidf.joblib")

_model = None


def _get_model():
    global _model
    if _model is None:
        if not MODEL_PATH.exists():
            raise FileNotFoundError(
                f"TF-IDF model not found at {MODEL_PATH}. Train it first (train_query_tfidf.py)."
            )
        _model = joblib.load(MODEL_PATH)
    return _model


def predict_intent(text: str) -> Tuple[str, float]:
    """
    Returns (predicted_label, confidence).
    """
    model = _get_model()
    proba = model.predict_proba([text])[0]
    idx = int(proba.argmax())
    label = str(model.classes_[idx])
    conf = float(proba[idx])
    return label, conf
