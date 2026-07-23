"""Operative Report plugin."""

from ...plugin_base import BaseMedicalReportPlugin, PluginRegistry


class OperativeReportPlugin(BaseMedicalReportPlugin):
    report_type = "operative_report"
    report_label = "Operative Report"
    section_order = [
        "Vitals",
        "Procedure", "Surgeon", "Assistant", "Anesthesia",
        "Preoperative Diagnosis", "Postoperative Diagnosis",
        "Findings", "Technique", "Complications",
        "Estimated Blood Loss", "Specimens", "Drains",
        "Plan", "Recommendations",
    ]


PluginRegistry.register(OperativeReportPlugin())
