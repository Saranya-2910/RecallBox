"""RecallBox Retrieval Evaluation Runner (Phase 9 Placeholder)."""
import json
from pathlib import Path


def main():
    questions_file = Path(__file__).parent / "questions.json"
    if questions_file.exists():
        with open(questions_file, "r", encoding="utf-8") as f:
            questions = json.load(f)
        print(f"Loaded {len(questions)} evaluation questions.")
    else:
        print("No questions.json found.")


if __name__ == "__main__":
    main()
