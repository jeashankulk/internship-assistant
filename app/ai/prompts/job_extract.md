# Job Extraction Prompt (MVP)

Return STRICT JSON only, matching the ExtractedJobFields schema.

Inputs:
- job.title
- job.company
- job.location
- job.description_text
- user_profile.targets (SWE/QUANT/OR)
- constraints: internships only, Summer 2026 only

Output keys (example):
{
  "role_family": "SWE|QUANT|OR|OTHER",
  "is_internship": true,
  "season": "Summer|Fall|Spring|Other|null",
  "year": 2026,
  "is_summer_2026": true,
  "paid_flag": "PAID|UNPAID|UNKNOWN",
  "requirements": [],
  "preferred_skills": [],
  "keywords": [],
  "ai_confidence": 0.0
}
