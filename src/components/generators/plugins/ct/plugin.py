"""CT report plugin."""

from ...plugin_base import BaseMedicalReportPlugin, PluginRegistry


class CTPlugin(BaseMedicalReportPlugin):
    report_type = "ct"
    report_label = "CT Scan Report"
    section_order = [
        "Vitals", "Clinical History",
        "Technique", "Findings", "Comparison",
        "Contrast", "Impression", "Recommendations",
    ]


PluginRegistry.register(CTPlugin())
