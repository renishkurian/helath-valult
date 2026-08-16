DOCTOR_SPECIALTIES = [
    "General Physician",
    "Paediatrics",
    "Gynaecology",
    "Obstetrics",
    "Cardiology",
    "Orthopaedics",
    "Dermatology",
    "ENT",
    "Ophthalmology",
    "Dentistry",
    "Neurology",
    "Psychiatry",
    "Pulmonology",
    "Gastroenterology",
    "Nephrology",
    "Endocrinology",
    "Urology",
    "Oncology",
    "Physiotherapy",
    "Ayurveda",
    "Homeopathy",
]


def resolve_doctor_specialty(specialty: str = "", specialty_custom: str = "") -> str | None:
    from app.templating import nice_name
    raw = (specialty or "").strip()
    custom = (specialty_custom or "").strip()
    if raw.lower() in ("other", "__other__"):
        return nice_name(custom) if custom else None
    if custom and (not raw or raw.lower() == "other"):
        return nice_name(custom)
    return nice_name(raw) if raw else None
