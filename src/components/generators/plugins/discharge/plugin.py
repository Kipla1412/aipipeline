"""Discharge Summary plugin."""

from ...plugin_base import BaseMedicalReportPlugin, PluginRegistry


class DischargeSummaryPlugin(BaseMedicalReportPlugin):
    report_type = "discharge_summary"
    report_label = "Discharge Summary"
    section_order = [
        "Vitals",
        "Admission Date", "Discharge Date", "Reason for Admission",
        "Hospital Course", "Discharge Diagnosis",
        "Discharge Medications", "Discharge Instructions",
        "Follow-up", "Diet", "Activity", "Plan",
    ]


PluginRegistry.register(DischargeSummaryPlugin())
