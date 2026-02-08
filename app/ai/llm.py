"""
LLM Client for OpenAI interactions.
"""
import os
import json
from typing import Optional, Dict, Any
import logging

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

from dotenv import load_dotenv

# Load env to get key
load_dotenv()

logger = logging.getLogger(__name__)

class LLMClient:
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.client = None
        if self.api_key and OpenAI:
            try:
                self.client = OpenAI(api_key=self.api_key)
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI client: {e}")

    def is_available(self) -> bool:
        return self.client is not None

    def parse_resume(self, resume_text: str) -> Dict[str, Any]:
        """Extract profile information from resume text."""
        if not self.client:
            return {}

        prompt = f"""
        You are an expert AI assistant helping a student fill out internship applications.
        Your task is to extract structured data from the resume text below to populate their profile.
        
        CRITICAL: matching the exact field names is important.

        Extract the following fields and return them as a valid JSON object:
        - first_name: (string) The first name of the applicant.
        - last_name: (string) The last name of the applicant.
        - full_name: (string) The full name (First + Last).
        - email: (string) Email address.
        - phone: (string) Phone number.
        - location: (string) City, State (e.g. "San Francisco, CA").
        - school: (string) Current university or college name.
        - degree: (string) Degree type (e.g. "Bachelor of Science", "Master's").
        - major: (string) Major or field of study (e.g. "Computer Science").
        - graduation_year: (string) Expected graduation year (e.g. "2026").
        - graduation_month: (string) Expected graduation month (e.g. "May", "December").
        - linkedin: (string) LinkedIn profile URL.
        - github: (string) GitHub profile URL.
        - website: (string) Personal website or portfolio URL.
        - skills: (list of strings) Key technical skills.

        If a field cannot be found, return an empty string "" for string fields, or [] for lists. Do NOT return null or "N/A".

        Resume Text:
        {resume_text[:12000]}
        """

        try:
            print(f"[DEBUG] Sending resume to LLM (length: {len(resume_text)})")
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a precise data extraction assistant. Respond only with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"}
            )
            content = response.choices[0].message.content
            print(f"[DEBUG] LLM Response: {content[:100]}...")
            return json.loads(content)
        except Exception as e:
            logger.error(f"Error parsing resume: {e}")
            print(f"[ERROR] Resume parsing failed: {e}")
            # Identify if it's an API key issue or rate limit
            return {}

    def check_answer_bank(self, question: str, answer_bank: Dict[str, Any]) -> Optional[str]:
        """
        Check if any existing answer in the bank matches the question semantically.
        Returns the answer text if a match is found, else None.
        """
        if not self.client or not answer_bank:
            return None

        # Convert simple bank to list of "Question: Answer" strings for context
        # answer_bank structure: key -> {exact: ..., generated: ...} or just value
        # We need to flatten it to a searchable format
        bank_context = []
        for key, value in answer_bank.items():
            val_str = value if isinstance(value, str) else value.get('value', str(value))
            bank_context.append(f"Q: {key}\nA: {val_str}")
        
        if not bank_context:
            return None

        # prompt to find match
        context_str = "\n---\n".join(bank_context[:50]) # Limit context window
        
        prompt = f"""
        You are filling out a job application.
        Current Question: "{question}"

        Below is a list of questions you have answered previously:
        {context_str}

        Task: Determine if any of the PREVIOUS answers can be used for the CURRENT Question.
        - The questions must be asking for the same information.
        - Be careful: "Have you worked at Apple?" is DIFFERENT from "Have you worked at Tesla?".
        - If a match is found, return the exact Answer text.
        - If no match is found, return "NO_MATCH".
        """

        try:
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant. Respond with the answer text or NO_MATCH."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0
            )
            content = response.choices[0].message.content.strip()
            if content == "NO_MATCH":
                return None
            return content
        except Exception as e:
            logger.error(f"Error checking answer bank: {e}")
            return None

    def generate_answer_from_resume(self, question: str, resume_text: str, options: Optional[list] = None) -> Optional[str]:
        """Generate an answer based exclusively on the resume."""
        if not self.client:
            return None

        prompt = f"""
        You are an applicant filling out a job application.
        Question: "{question}"
        
        {f"Options: {', '.join(options)}" if options else ""}

        Resume:
        {resume_text[:10000]}

        Task: Answer the question truthfully based ONLY on the resume provided.
        - If the question asks for a specific number (e.g., GPA, years of experience), extract it.
        - If the question asks for a "Yes/No", answer "Yes" or "No".
        - If the answer cannot be found in the resume, return "UNKNOWN".
        - Keep the answer concise and professional.
        """

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a job applicant. Answer strictly based on your resume."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0
            )
            content = response.choices[0].message.content.strip()
            if "UNKNOWN" in content:
                return None
            return content
        except Exception as e:
            logger.error(f"Error generating answer from resume: {e}")
            return None
