"""Markdown page templates for Medical Knowledge Base entities."""

from __future__ import annotations


def disease_page(name: str, patients: list[str], procedures: list[str]) -> str:
    blocks = [f"# {name}"]
    if patients:
        links = "\n".join(f"- [[{p}]]" for p in patients)
        blocks.append(f"## Patients\n\n{links}")
    if procedures:
        links = "\n".join(f"- [[{p}]]" for p in procedures)
        blocks.append(f"## Procedures\n\n{links}")
    return "\n\n".join(blocks) + "\n"


def medication_page(name: str, medications: list[str]) -> str:
    links = "\n".join(f"- {m}" for m in medications)
    return f"# {name}\n\n## Medications\n\n{links or 'None recorded'}\n"


def procedure_page(name: str, patients: list[str], findings: str) -> str:
    blocks = [f"# {name}"]
    if patients:
        links = "\n".join(f"- [[{p}]]" for p in patients)
        blocks.append(f"## Related Patients\n\n{links}")
    blocks.append(f"## Findings\n\n{findings or 'See report summary.'}")
    return "\n\n".join(blocks) + "\n"


def doctor_page(name: str, hospital: str | None, patients: list[str]) -> str:
    links = "\n".join(f"- [[{p}]]" for p in patients)
    return (
        f"# {name}\n\n"
        f"## Hospital\n\n{_link_or_na(hospital)}\n\n"
        f"## Patients\n\n{links or 'None recorded'}\n"
    )


def hospital_page(name: str, doctors: list[str], patients: list[str]) -> str:
    links_d = "\n".join(f"- [[{d}]]" for d in doctors)
    links_p = "\n".join(f"- [[{p}]]" for p in patients)
    return (
        f"# {name}\n\n"
        f"## Doctors\n\n{links_d or 'None recorded'}\n\n"
        f"## Patients\n\n{links_p or 'None recorded'}\n"
    )


def _link_or_na(value: str | None) -> str:
    return f"[[{value}]]" if value else "N/A"
