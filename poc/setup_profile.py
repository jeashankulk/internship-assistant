#!/usr/bin/env python3
"""
Quick setup wizard to create your profile for testing.
Creates storage/profile.json with your real information.
Also configures target roles in config/roles.json.
"""

import json
from pathlib import Path


# Preset role configurations
ROLE_PRESETS = {
    "1": {
        "name": "Software Engineering",
        "include_keywords": [
            "software", "engineer", "developer", "swe",
            "backend", "frontend", "full stack", "fullstack",
            "platform", "infrastructure", "systems",
            "devops", "sre", "cloud",
            "mobile", "ios", "android", "web"
        ],
        "exclude_keywords": [
            "marketing", "sales", "communications", "hr", "human resources",
            "legal", "finance", "accounting", "recruiting", "talent",
            "content", "social media", "graphic", "design",
            "customer", "support", "success", "admin"
        ]
    },
    "2": {
        "name": "Data Science / ML / AI",
        "include_keywords": [
            "data", "machine learning", "ml", "ai", "artificial intelligence",
            "analytics", "analyst", "science", "scientist",
            "research", "nlp", "computer vision", "deep learning"
        ],
        "exclude_keywords": [
            "marketing", "sales", "communications", "hr", "human resources",
            "legal", "recruiting", "talent",
            "content", "social media", "graphic",
            "customer", "support", "success", "admin"
        ]
    },
    "3": {
        "name": "Quantitative / Trading",
        "include_keywords": [
            "quant", "quantitative", "trading", "trader",
            "algorithmic", "algo", "strats", "strategies",
            "research", "researcher", "analytics"
        ],
        "exclude_keywords": [
            "marketing", "sales", "communications", "hr", "human resources",
            "legal", "recruiting", "talent",
            "content", "social media", "graphic",
            "customer", "support", "success", "admin"
        ]
    },
    "4": {
        "name": "Product / Program Management",
        "include_keywords": [
            "product", "program", "project", "manager", "management",
            "pm", "apm", "tpm", "technical program"
        ],
        "exclude_keywords": [
            "marketing", "sales", "communications", "hr", "human resources",
            "legal", "finance", "accounting", "recruiting", "talent",
            "content", "social media", "graphic",
            "customer", "support", "success", "admin"
        ]
    },
    "5": {
        "name": "Design / UX / UI",
        "include_keywords": [
            "design", "ux", "ui", "user experience", "user interface",
            "product design", "visual", "graphic", "interaction"
        ],
        "exclude_keywords": [
            "engineering", "software", "backend", "frontend",
            "marketing", "sales", "hr", "legal", "finance"
        ]
    },
    "6": {
        "name": "Finance / Accounting",
        "include_keywords": [
            "finance", "financial", "accounting", "accountant",
            "investment", "banking", "analyst", "fp&a", "treasury"
        ],
        "exclude_keywords": [
            "software", "engineering", "developer",
            "marketing", "sales", "hr", "legal"
        ]
    },
    "7": {
        "name": "Marketing / Growth",
        "include_keywords": [
            "marketing", "growth", "brand", "content", "social media",
            "digital marketing", "performance", "acquisition"
        ],
        "exclude_keywords": [
            "software", "engineering", "developer",
            "finance", "accounting", "hr", "legal"
        ]
    }
}


def setup_roles():
    """Configure target roles and update config/roles.json."""
    print("\n" + "-" * 40)
    print("TARGET ROLES")
    print("-" * 40)
    print("What types of internships are you looking for?")
    print("(Select multiple by entering numbers separated by commas)\n")

    for key, preset in ROLE_PRESETS.items():
        print(f"  {key}) {preset['name']}")

    print("\n  8) Custom (I'll edit config/roles.json manually)")

    choices = input("\nEnter your choices (e.g., 1,2,3) [1]: ").strip() or "1"

    if "8" in choices:
        print("\n  You can edit config/roles.json to customize your search.")
        return ["CUSTOM"]

    # Parse selections
    selected = []
    for c in choices.replace(" ", "").split(","):
        if c in ROLE_PRESETS:
            selected.append(c)

    if not selected:
        selected = ["1"]  # Default to SWE

    # Combine keywords from all selected presets
    combined_include = set()
    combined_exclude = set()
    role_names = []

    for choice in selected:
        preset = ROLE_PRESETS[choice]
        role_names.append(preset["name"])
        combined_include.update(preset["include_keywords"])
        combined_exclude.update(preset["exclude_keywords"])

    # Remove conflicts (if a keyword is in include, don't exclude it)
    combined_exclude -= combined_include

    # Build config
    config = {
        "description": f"Configured for: {', '.join(role_names)}",
        "include_keywords": sorted(list(combined_include)),
        "exclude_keywords": sorted(list(combined_exclude)),
        "must_contain": ["intern"]
    }

    # Save to config/roles.json
    config_dir = Path(__file__).parent.parent / "config"
    config_dir.mkdir(exist_ok=True)
    config_path = config_dir / "roles.json"

    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)

    print(f"\n  ✓ Configured for: {', '.join(role_names)}")
    print(f"  ✓ Saved to: {config_path}")

    return role_names


def setup_profile():
    print("=" * 60)
    print("INTERNSHIP ASSISTANT - PROFILE SETUP")
    print("=" * 60)
    print("\nThis will create your profile for auto-filling applications.")
    print("Press Enter to skip optional fields.\n")

    profile = {}

    # Required fields
    print("-" * 40)
    print("BASIC INFORMATION")
    print("-" * 40)

    profile["first_name"] = input("First Name: ").strip()
    profile["last_name"] = input("Last Name: ").strip()
    profile["full_name"] = f"{profile['first_name']} {profile['last_name']}"
    profile["email"] = input("Email: ").strip()
    profile["phone"] = input("Phone (e.g., +1-555-123-4567): ").strip() or ""

    print("\n" + "-" * 40)
    print("LOCATION")
    print("-" * 40)

    profile["location"] = input("Current Location (City, State): ").strip() or ""

    print("\n" + "-" * 40)
    print("EDUCATION")
    print("-" * 40)

    profile["school"] = input("School/University: ").strip() or ""
    profile["degree"] = input("Degree (e.g., Bachelor's, Master's): ").strip() or "Bachelor's"
    profile["major"] = input("Major: ").strip() or ""
    profile["graduation_year"] = input("Expected Graduation Year (e.g., 2026): ").strip() or "2026"
    profile["graduation_month"] = input("Graduation Month (e.g., May, December): ").strip() or "May"

    print("\n" + "-" * 40)
    print("LINKS (press Enter to skip)")
    print("-" * 40)

    profile["linkedin"] = input("LinkedIn URL: ").strip() or ""
    profile["github"] = input("GitHub URL: ").strip() or ""
    profile["website"] = input("Personal Website/Portfolio URL: ").strip() or ""

    print("\n" + "-" * 40)
    print("RESUME")
    print("-" * 40)

    resume_path = input("Path to your Resume PDF: ").strip()
    if resume_path:
        # Expand ~ to home directory
        resume_path = str(Path(resume_path).expanduser())
        if Path(resume_path).exists():
            profile["resume_path"] = resume_path
            print(f"  ✓ Found: {resume_path}")
        else:
            print(f"  ✗ File not found: {resume_path}")
            profile["resume_path"] = ""
    else:
        profile["resume_path"] = ""

    print("\n" + "-" * 40)
    print("WORK AUTHORIZATION")
    print("-" * 40)

    print("Are you authorized to work in the US?")
    print("  1) Yes - US Citizen")
    print("  2) Yes - Green Card")
    print("  3) Yes - Work Visa")
    print("  4) No - Require Sponsorship")
    auth_choice = input("Enter 1-4 [1]: ").strip() or "1"

    auth_map = {
        "1": ("yes", "no", "US Citizen"),
        "2": ("yes", "no", "Green Card"),
        "3": ("yes", "yes", "Work Visa"),
        "4": ("no", "yes", "Require Sponsorship"),
    }
    auth = auth_map.get(auth_choice, auth_map["1"])
    profile["work_authorization"] = auth[0]
    profile["requires_sponsorship"] = auth[1]
    profile["work_authorization_detail"] = auth[2]

    print("\n" + "-" * 40)
    print("OPTIONAL: COVER LETTER SNIPPET")
    print("-" * 40)
    print("(A brief intro used for 'Why are you interested?' fields)")
    print("Press Enter twice to finish:")

    lines = []
    while True:
        line = input()
        if line == "":
            break
        lines.append(line)
    profile["cover_letter"] = "\n".join(lines) if lines else ""

    # Target roles - configure what types of jobs to search for
    role_names = setup_roles()
    profile["target_roles"] = role_names

    # Save profile
    storage_dir = Path(__file__).parent.parent / "storage"
    storage_dir.mkdir(exist_ok=True)
    profile_path = storage_dir / "profile.json"

    with open(profile_path, "w") as f:
        json.dump(profile, f, indent=2)

    print("\n" + "=" * 60)
    print("SETUP COMPLETE!")
    print("=" * 60)
    print(f"\nProfile saved to: {profile_path}")
    print("\nYour profile:")
    print(f"  Name: {profile['full_name']}")
    print(f"  Email: {profile['email']}")
    print(f"  School: {profile['school']} ({profile['graduation_year']})")
    print(f"  Resume: {profile['resume_path'] or 'Not provided'}")
    print(f"  LinkedIn: {profile['linkedin'] or 'Not provided'}")
    print(f"  GitHub: {profile['github'] or 'Not provided'}")
    print(f"  Target Roles: {', '.join(profile['target_roles'])}")
    print(f"\nRole config saved to: config/roles.json")
    print("\nYou can run the app with: python run_ui.py")

    return profile


if __name__ == "__main__":
    setup_profile()
