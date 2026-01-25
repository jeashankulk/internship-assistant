#!/usr/bin/env python3
"""
Answer Bank - Stores and retrieves answers for job application questions.

Features:
- Saves answers keyed by normalized question text
- Fuzzy matching for similar questions
- Learns from manual user input
- Supports both dropdown and text answers
"""

import json
import re
from pathlib import Path
from difflib import SequenceMatcher
from typing import Optional

STORAGE_DIR = Path(__file__).parent.parent / "storage"
ANSWERS_PATH = STORAGE_DIR / "answers.json"

# Common dropdown patterns and their normalized keys
DROPDOWN_PATTERNS = {
    # Work Authorization
    r"(authorized|authorization|legally|permit).*(work|employment).*(us|u\.s\.|united states)": "work_auth_us",
    r"(require|need).*(sponsor|visa)": "requires_sponsorship",
    r"(citizen|citizenship)": "citizenship",

    # Education
    r"(graduation|graduate|grad).*(date|year|when)": "graduation_date",
    r"(degree|education level)": "degree_type",
    r"(major|field of study|concentration)": "major",
    r"(school|university|college|institution)": "school",
    r"(gpa|grade point)": "gpa",

    # Personal
    r"(gender|sex)": "gender",
    r"(race|ethnic|ethnicity)": "ethnicity",
    r"(veteran|military)": "veteran_status",
    r"(disability|disabled)": "disability_status",
    r"(pronouns?)": "pronouns",

    # Job Related
    r"(hear|heard|find|found).*(about|us|position|job|role)": "referral_source",
    r"(start|available|availability).*(date|when)": "start_date",
    r"(salary|compensation|pay).*(expectation|requirement|desired)": "salary_expectation",
    r"(relocat|willing to move)": "willing_to_relocate",
    r"(remote|hybrid|on-?site|in-?person)": "work_location_preference",

    # Experience
    r"(years?).*(experience)": "years_experience",
    r"(proficien|skill level|expertise).*(programming|coding|language)": "programming_proficiency",
}

# Smart value mappings for common dropdowns
VALUE_MAPPINGS = {
    "work_auth_us": {
        "yes": ["yes", "authorized", "eligible", "legally authorized", "yes - us citizen", "yes - green card", "us citizen", "permanent resident"],
        "no": ["no", "not authorized", "require sponsorship", "will require"],
    },
    "requires_sponsorship": {
        "no": ["no", "not required", "do not require", "won't require", "will not require"],
        "yes": ["yes", "required", "will require", "need sponsorship"],
    },
    "degree_type": {
        "bachelors": ["bachelor", "bachelors", "bs", "ba", "b.s.", "b.a.", "undergraduate"],
        "masters": ["master", "masters", "ms", "ma", "m.s.", "m.a.", "graduate"],
        "phd": ["phd", "ph.d.", "doctorate", "doctoral"],
    },
    "veteran_status": {
        "no": ["no", "not a veteran", "i am not", "n/a", "prefer not"],
        "yes": ["yes", "veteran", "i am a veteran"],
    },
    "disability_status": {
        "no": ["no", "i don't have", "i do not have", "n/a", "prefer not", "decline"],
        "yes": ["yes", "i have a disability"],
    },
    "gender": {
        "male": ["male", "man", "m"],
        "female": ["female", "woman", "f", "w"],
        "other": ["non-binary", "other", "prefer not to say", "decline", "n/a"],
    },
}


class AnswerBank:
    """Stores and retrieves answers for job application questions."""

    def __init__(self, path: Path = ANSWERS_PATH):
        self.path = path
        self.answers = self._load()

    def _load(self) -> dict:
        """Load answers from file."""
        if self.path.exists():
            with open(self.path) as f:
                return json.load(f)
        return {
            "exact": {},      # Exact question text -> answer
            "patterns": {},   # Normalized pattern key -> answer
            "custom": {},     # Custom questions by company -> answer
        }

    def save(self):
        """Save answers to file."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w") as f:
            json.dump(self.answers, f, indent=2)

    def normalize_question(self, question: str) -> str:
        """Normalize a question for matching."""
        # Lowercase, remove extra whitespace, remove special chars
        q = question.lower().strip()
        q = re.sub(r'[^\w\s]', ' ', q)
        q = re.sub(r'\s+', ' ', q)
        return q

    def get_pattern_key(self, question: str) -> Optional[str]:
        """Get the pattern key for a question if it matches a known pattern."""
        q_lower = question.lower()
        for pattern, key in DROPDOWN_PATTERNS.items():
            if re.search(pattern, q_lower):
                return key
        return None

    def find_matching_value(self, pattern_key: str, options: list[str], profile_value: str) -> Optional[str]:
        """Find the best matching option value based on profile value."""
        if pattern_key not in VALUE_MAPPINGS:
            return None

        mappings = VALUE_MAPPINGS[pattern_key]
        profile_lower = profile_value.lower()

        # Find which category the profile value belongs to
        matched_category = None
        for category, keywords in mappings.items():
            if any(kw in profile_lower or profile_lower in kw for kw in keywords):
                matched_category = category
                break

        if not matched_category:
            return None

        # Find the option that matches this category
        target_keywords = mappings[matched_category]
        for option in options:
            option_lower = option.lower()
            if any(kw in option_lower for kw in target_keywords):
                return option

        return None

    def get_answer(self, question: str, company: str = None) -> Optional[str]:
        """Get a stored answer for a question."""
        normalized = self.normalize_question(question)

        # Check exact match first
        if normalized in self.answers["exact"]:
            return self.answers["exact"][normalized]

        # Check pattern match
        pattern_key = self.get_pattern_key(question)
        if pattern_key and pattern_key in self.answers["patterns"]:
            return self.answers["patterns"][pattern_key]

        # Check company-specific custom answers
        if company:
            company_key = company.lower()
            if company_key in self.answers.get("custom", {}):
                if normalized in self.answers["custom"][company_key]:
                    return self.answers["custom"][company_key][normalized]

        # Check fuzzy match against exact answers
        best_match = None
        best_ratio = 0.7  # Minimum similarity threshold

        for stored_q, stored_a in self.answers["exact"].items():
            ratio = SequenceMatcher(None, normalized, stored_q).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = stored_a

        return best_match

    def store_answer(self, question: str, answer: str, company: str = None, is_pattern: bool = False):
        """Store an answer for future use."""
        normalized = self.normalize_question(question)

        if is_pattern:
            pattern_key = self.get_pattern_key(question)
            if pattern_key:
                self.answers["patterns"][pattern_key] = answer
        elif company:
            company_key = company.lower()
            if company_key not in self.answers["custom"]:
                self.answers["custom"][company_key] = {}
            self.answers["custom"][company_key][normalized] = answer
        else:
            self.answers["exact"][normalized] = answer

        self.save()

    def get_all_answers(self) -> dict:
        """Get all stored answers for review."""
        return self.answers


# Global instance
_answer_bank = None

def get_answer_bank() -> AnswerBank:
    """Get the global answer bank instance."""
    global _answer_bank
    if _answer_bank is None:
        _answer_bank = AnswerBank()
    return _answer_bank


if __name__ == "__main__":
    # Test the answer bank
    bank = AnswerBank()

    print("Testing pattern detection:")
    test_questions = [
        "Are you legally authorized to work in the United States?",
        "Will you now or in the future require sponsorship?",
        "What is your expected graduation date?",
        "How did you hear about this position?",
        "Are you a veteran?",
    ]

    for q in test_questions:
        key = bank.get_pattern_key(q)
        print(f"  '{q[:50]}...' -> {key}")
