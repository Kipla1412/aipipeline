"""Consultation note plugin."""

from ...plugin_base import BaseMedicalReportPlugin, PluginRegistry


class ConsultationPlugin(BaseMedicalReportPlugin):
    report_type = "consultation"
    report_label = "Consultation Note"
    section_order = [
        "Vitals", "Reason for Consult", "History",
        "Assessment", "Plan", "Recommendations",
    ]


PluginRegistry.register(ConsultationPlugin())
