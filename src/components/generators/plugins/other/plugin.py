"""Default / Other report plugin — catch-all for unclassified reports."""

from ...plugin_base import BaseMedicalReportPlugin, PluginRegistry


class DefaultPlugin(BaseMedicalReportPlugin):
    report_type = "other"
    report_label = "General Medical Report"
    section_order = [
        "Vitals", "Clinical History",
        "Findings", "Impression", "Recommendations",
    ]


PluginRegistry.register(DefaultPlugin())
