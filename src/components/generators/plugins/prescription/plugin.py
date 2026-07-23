"""Prescription plugin."""

from ...plugin_base import BaseMedicalReportPlugin, PluginRegistry


class PrescriptionPlugin(BaseMedicalReportPlugin):
    report_type = "prescription"
    report_label = "Prescription"
    section_order = [
        "Vitals",
        "Medication", "Dosage", "Frequency", "Duration", "Route",
        "Refills", "Special Instructions", "Diagnosis",
        "Findings", "Recommendations",
    ]


PluginRegistry.register(PrescriptionPlugin())
