from pathlib import Path
import joblib

MODEL_PATH = Path("backend/ml/model_query_tfidf.joblib")

model = joblib.load(MODEL_PATH)


tests = [
  "what hotels in colombo have rooftop bars?",
  "i need a hotel with a gym in mount lavinia",
  "show me honeymoon packages in bentota",
  "are there any hotels near the cricket stadium in colombo?",
  "find me a hotel with balcony rooms in kandy",
  "what's the average cost per night in galle?",
  "i want a hotel near the nine arch bridge in ella",
  "do you have hotels with kitchenettes in negombo?",
  "show me adults-only resorts in sri lanka",
  "what hotels offer surfing lessons in weligama?",
  "i need wheelchair accessible hotels in colombo",
  "are there any tea estate bungalows in nuwara eliya?",
  "find hotels with private beach access in nilaveli",
  "what's the closest hotel to pinnawala elephant orphanage?",
  "show me hotels that accept cryptocurrency payments",
  "i want a hotel with traditional sri lankan architecture in galle",
  "do any hotels in hikkaduwa have turtle watching tours?",
  "what hotels have the best breakfast buffets in colombo?",
  "i need a quiet hotel away from the main road in mirissa",
  "are there any historic colonial hotels in kandy?",
  "find me a hotel with laundry service in trincomalee",
  "what hotels are near the shopping malls in colombo?",
  "show me long-term stay options in ella for 2 months",
  "i want a hotel with ayurvedic spa treatments in bentota",
  "what's the cancellation policy for hotels in unawatuna?"
]
for t in tests:
    proba = model.predict_proba([t])[0]
    label = model.classes_[proba.argmax()]
    conf = proba.max()
    print(f"{t!r} -> {label} ({conf:.2f})")
