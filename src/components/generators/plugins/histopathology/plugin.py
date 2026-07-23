"""Histopathology plugin."""

from ...plugin_base import BaseMedicalReportPlugin, PluginRegistry


class HistopathologyPlugin(BaseMedicalReportPlugin):
    report_type = "histopathology"
    report_label = "Histopathology Report"
    section_order = [
        "Specimen", "Gross Description", "Microscopic Findings",
        "Diagnosis", "Margins", "Lymph Nodes",
        "Immunohistochemistry", "Molecular Studies",
        "Findings", "Impression", "Recommendations",
    ]


PluginRegistry.register(HistopathologyPlugin())
