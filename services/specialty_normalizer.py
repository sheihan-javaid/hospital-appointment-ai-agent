# services/specialty_normalizer.py

SPECIALTY_MAP = {

    # ── Dentistry ───────────────────────────────────────────────────
    "dentist":           "dentistry",
    "dental":            "dentistry",
    "teeth":             "dentistry",
    "tooth":             "dentistry",
    "toothache":         "dentistry",
    "gums":              "dentistry",
    "braces":            "dentistry",
    "cavity":            "dentistry",
    "root canal":        "dentistry",
    "oral":              "dentistry",

    # ── Cardiology ──────────────────────────────────────────────────
    "cardio":            "cardiology",
    "cardiologist":      "cardiology",
    "heart":             "cardiology",
    "chest pain":        "cardiology",
    "bp":                "cardiology",
    "blood pressure":    "cardiology",
    "palpitations":      "cardiology",
    "cardiac":           "cardiology",

    # ── Neurology ───────────────────────────────────────────────────
    "neuro":             "neurology",
    "neurologist":       "neurology",
    "brain":             "neurology",
    "headache":          "neurology",
    "migraine":          "neurology",
    "seizure":           "neurology",
    "epilepsy":          "neurology",
    "nerve":             "neurology",
    "dizziness":         "neurology",
    "numbness":          "neurology",

    # ── Pediatrics ──────────────────────────────────────────────────
    "pediatric":         "pediatrics",
    "pediatrician":      "pediatrics",
    "paediatrics":       "pediatrics",
    "paediatrician":     "pediatrics",
    "child":             "pediatrics",
    "children":          "pediatrics",
    "baby":              "pediatrics",
    "infant":            "pediatrics",
    "kid":               "pediatrics",
    "kids":              "pediatrics",

    # ── Orthopedics ─────────────────────────────────────────────────
    "orthopedic":        "orthopedics",
    "orthopaedics":      "orthopedics",
    "orthopedist":       "orthopedics",
    "bone":              "orthopedics",
    "bones":             "orthopedics",
    "joint":             "orthopedics",
    "knee":              "orthopedics",
    "back pain":         "orthopedics",
    "spine":             "orthopedics",
    "fracture":          "orthopedics",
    "sports injury":     "orthopedics",

    # ── Dermatology ─────────────────────────────────────────────────
    "dermatologist":     "dermatology",
    "skin":              "dermatology",
    "acne":              "dermatology",
    "rash":              "dermatology",
    "eczema":            "dermatology",
    "psoriasis":         "dermatology",
    "hair loss":         "dermatology",
    "alopecia":          "dermatology",
    "mole":              "dermatology",
    "allergy":           "dermatology",

    # ── General Practice ────────────────────────────────────────────
    "general":           "general practice",
    "gp":                "general practice",
    "general physician": "general practice",
    "physician":         "general practice",
    "fever":             "general practice",
    "cold":              "general practice",
    "flu":               "general practice",
    "cough":             "general practice",
    "checkup":           "general practice",
    "check-up":          "general practice",
    "general doctor":    "general practice",
    "family doctor":     "general practice",

    # ── Gynecology ──────────────────────────────────────────────────
    "gynecologist":      "gynecology",
    "gynaecology":       "gynecology",
    "gynaecologist":     "gynecology",
    "gyno":              "gynecology",
    "obgyn":             "gynecology",
    "ob-gyn":            "gynecology",
    "women":             "gynecology",
    "pregnancy":         "gynecology",
    "prenatal":          "gynecology",
    "periods":           "gynecology",
    "menstrual":         "gynecology",
    "pcos":              "gynecology",

    # ── Urology ─────────────────────────────────────────────────────
    "urologist":         "urology",
    "kidney":            "urology",
    "bladder":           "urology",
    "uti":               "urology",
    "urinary":           "urology",
    "prostate":          "urology",
    "kidney stone":      "urology",

    # ── Endocrinology ───────────────────────────────────────────────
    "endocrinologist":   "endocrinology",
    "diabetes":          "endocrinology",
    "diabetic":          "endocrinology",
    "thyroid":           "endocrinology",
    "hormones":          "endocrinology",
    "hormone":           "endocrinology",
    "insulin":           "endocrinology",
    "sugar":             "endocrinology",
    "blood sugar":       "endocrinology",
    "obesity":           "endocrinology",
}


def normalize_specialty(raw: str) -> str:
    """
    Resolves a user-provided specialty string to a canonical DB value.

    Resolution order:
      1. Exact match in SPECIALTY_MAP
      2. Substring scan (catches symptom phrases like "my back pain is severe")
      3. Fall through — return as-is and let MongoDB regex handle it
    """
    normalized = raw.lower().strip()

    # 1. Exact match
    if normalized in SPECIALTY_MAP:
        return SPECIALTY_MAP[normalized]

    # 2. Substring scan — longest key first to avoid short-key false matches
    #    e.g. "kidney stone" should win over "kidney"
    for key in sorted(SPECIALTY_MAP, key=len, reverse=True):
        if key in normalized:
            return SPECIALTY_MAP[key]

    # 3. Fall through
    return normalized