"""Interview tracks.

One track is live: the UK university pre-CAS credibility interview. It is modelled
as a spec (required facts, formats, things it must never ask for) so that a second
track, when it comes, cannot leak its assumptions into this one. Pre-CAS happens
before a CAS exists: a CAS number must never be required.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SessionFormat:
    id: str
    label: str
    practice_seconds: int
    # Shown to the student. A format is a product choice, not a claim about how long
    # a real interview lasts.
    disclosure: str


@dataclass(frozen=True)
class TrackSpec:
    id: str
    label: str
    stage: str
    required_facts: tuple[str, ...]
    optional_facts: tuple[str, ...]
    # Facts this track must never require.
    must_not_require: tuple[str, ...]
    formats: tuple[SessionFormat, ...]
    notes: tuple[str, ...] = field(default_factory=tuple)

    def format(self, format_id: str) -> SessionFormat:
        for f in self.formats:
            if f.id == format_id:
                return f
        raise KeyError(format_id)


UK_PRE_CAS = TrackSpec(
    id="uk_pre_cas",
    label="UK pre-CAS credibility interview practice",
    stage="Practice for a UK university's own credibility interview, held before it issues a CAS.",
    # Nothing is required: students can practise straight away, give five quick
    # details, or fill the full bio. The interviewer asks about whatever is missing.
    required_facts=(),
    optional_facts=(
        "student.full_name",
        "student.home_country",
        "program.university",
        "program.course",
        "program.start_date",
        "program.level",
        "uk.offer_conditions",
        "uk.accommodation_plan",
        "academic.history",
        "academic.gap_explanation",
        "academic.english_test",
        "funding.costs",
        "funding.funds",
        "funding.scholarships",
        "funding.sponsor_income",
    ),
    must_not_require=("uk.cas_number",),
    formats=(
        SessionFormat(
            id="interview_5m",
            label="Five-minute interview (3 questions)",
            practice_seconds=300,
            disclosure=(
                "A five-minute, three-question practice interview with a fictional AI "
                "interviewer. It is not a university or UKVI interview and does not "
                "predict any decision."
            ),
        ),
    ),
    notes=(
        "Pre-CAS happens before a CAS exists: never ask for a CAS number.",
        "Never present the interviewer as a university officer or a UKVI official.",
        "Never use government branding.",
    ),
)

TRACKS: dict[str, TrackSpec] = {UK_PRE_CAS.id: UK_PRE_CAS}


def get_track(track_id: str) -> TrackSpec:
    try:
        return TRACKS[track_id]
    except KeyError as e:
        raise KeyError(f"unknown track {track_id!r}") from e
