from __future__ import annotations

import json
from pathlib import Path

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

DATA_PATH = Path("backend/ml/query_dataset_ml.jsonl")
MODEL_PATH = Path("backend/ml/model_query_tfidf.joblib")


def load_jsonl(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")
    X, y = [], []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip(): # “If this line is empty or just spaces…” skip
            continue
        row = json.loads(line) # Json to dict
        X.append(row["text"])
        y.append(row["label"])
    return X, y


def main():
    X, y = load_jsonl(DATA_PATH)

    model = Pipeline(
        steps=[
            ("tfidf", TfidfVectorizer(
                lowercase=True,
                strip_accents="unicode", # Remove accent marks (e.g., café → cafe)
                analyzer="char_wb", # Character based n-grams 
                ngram_range=(3, 6), # Use 3-6 character n-grams 
                min_df=1, # “How many times must something appear in the dataset before we keep it?” , make it bigger as the dataset grows
            )),
            ("clf", LogisticRegression(
                max_iter=500,
                class_weight="balanced", # not needed bcz dataset is balanced ( Added for Future proofing) 
            )),
        ]
    )

    model.fit(X, y)
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODEL_PATH)

    print(f"✅ Saved query TF-IDF model to: {MODEL_PATH}")
    print(f"Classes: {list(model.classes_)}") # Should show ['EXPLORE_LOCAL', 'LIVE_PRICES', 'NEED_DATES', 'OUT_OF_SCOPE']
    print(f"Samples: {len(X)}")


if __name__ == "__main__":
    main()
