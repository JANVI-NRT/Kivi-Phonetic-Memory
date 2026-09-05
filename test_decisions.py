import requests
import json

words = [
    "aditya",
    "rahit",
    "rohit",
    "someone",
    "aadityaaa",
]

results = []

for word in words:
    response = requests.get(
        "http://127.0.0.1:8000/memories/decide",
        params={"q": word},
    )

    results.append({
        "input": word,
        "response": response.json(),
    })

with open("decision_results.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)

print("Done! Results saved to decision_results.json")