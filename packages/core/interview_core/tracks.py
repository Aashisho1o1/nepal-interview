"""Interview tracks.

US F-1, UK university pre-CAS and UKVI credibility interviews are different
workflows with different inputs. They are modelled separately so that one track's
assumptions (for example "an I-20 exists" or "a CAS exists") never leak into another.

Only one track is enabled in milestone one. The others are defined so the API can
show them, refuse to start them, and so tests can prove the distinctions hold.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SessionFormat:
    id: str
    label: str
    practice_seconds: int
    # Shown to the student. A drill is a product format, not a claim about how long
    # a real interview lasts.
    disclosure: str


@dataclass(frozen=True)
class TrackSpec:
    id: str
    label: str
    stage: str
    enabled: bool
    required_facts: tuple[str, ...]
    optional_facts: tuple[str, ...]
    # Facts this track must never require. Pre-CAS happens before a CAS exists.
    must_not_require: tuple[str, ...]
    topics: tuple[str, ...]
    formats: tuple[SessionFormat, ...]
    interviewer_role: str
    notes: tuple[str, ...] = field(default_factory=tuple)

    def format(self, format_id: str) -> SessionFormat:
        for f in self.formats:
            if f.id == format_id:
                return f
        raise KeyError(format_id)


US_F1 = TrackSpec(
    id="us_f1",
    label="US F-1 student visa practice",
    stage="Practice for a US F-1 visa interview after receiving an I-20.",
    enabled=True,
    required_facts=(
        "student.full_name",
        "program.university",
        "program.course",
        "program.level",
        "program.start_date",
        "funding.costs",
        "funding.funds",
    ),
    optional_facts=(
        "funding.scholarships",
        "funding.sponsor_income",
        "academic.history",
        "academic.gap_explanation",
        "plans.after_study",
    ),
    must_not_require=("uk.cas_number", "uk.offer_conditions"),
    topics=(
        "study_purpose",
        "course_choice",
        "university_choice",
        "academic_background",
        "funding",
        "plans_after_study",
    ),
    formats=(
        SessionFormat(
            id="pressure_drill_3m",
            label="Three-minute pressure drill",
            practice_seconds=180,
            disclosure=(
                "A three-minute practice drill. Real interviews vary in length; this is a "
                "practice format, not a simulation of a specific consular interview."
            ),
        ),
    ),
    interviewer_role="a fictional practice interviewer modelled on a professional questioner",
    notes=(
        "Never present the interviewer as a consular officer.",
        "Never use government branding.",
    ),
)

UK_PRE_CAS = TrackSpec(
    id="uk_pre_cas",
    label="UK university pre-CAS interview practice",
    stage="Practice for a university's own interview before it issues a CAS.",
    enabled=False,
    required_facts=(
        "student.full_name",
        "program.university",
        "program.course",
        "program.start_date",
        "funding.costs",
        "funding.funds",
        "uk.accommodation_plan",
    ),
    optional_facts=("uk.offer_conditions", "academic.history", "funding.scholarships"),
    # Pre-CAS happens before the CAS is issued. Requiring one would block every student.
    must_not_require=("uk.cas_number",),
    topics=(
        "course_knowledge",
        "university_choice",
        "study_plan",
        "funding",
        "accommodation",
        "plans_after_study",
    ),
    formats=(
        SessionFormat(
            id="short_drill_3m",
            label="Three-minute short drill",
            practice_seconds=180,
            disclosure="A short drill. It is not a full university pre-CAS mock interview.",
        ),
    ),
    interviewer_role="a fictional practice interviewer for a university admissions check",
    notes=("Institution-specific question banks are not built yet.",),
)

UKVI = TrackSpec(
    id="ukvi",
    label="UKVI credibility interview practice",
    stage="Practice for a UKVI credibility interview at the visa stage.",
    enabled=False,
    required_facts=(
        "student.full_name",
        "program.university",
        "program.course",
        "funding.costs",
        "funding.funds",
    ),
    optional_facts=("uk.cas_number", "academic.history"),
    must_not_require=(),
    topics=("consistency", "course_knowledge", "funding", "plans_after_study"),
    formats=(
        SessionFormat(
            id="short_drill_3m",
            label="Three-minute short drill",
            practice_seconds=180,
            disclosure="A short drill for practice. It is not a UKVI interview.",
        ),
    ),
    interviewer_role="a fictional practice interviewer; not a Home Office official",
    notes=("Scenario not validated; disabled in milestone one.",),
)

TRACKS: dict[str, TrackSpec] = {t.id: t for t in (US_F1, UK_PRE_CAS, UKVI)}


def get_track(track_id: str) -> TrackSpec:
    try:
        return TRACKS[track_id]
    except KeyError as e:
        raise KeyError(f"unknown track {track_id!r}") from e
