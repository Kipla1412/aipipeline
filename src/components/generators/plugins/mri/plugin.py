"""MRI report plugin."""

from ...plugin_base import BaseMedicalReportPlugin, PluginRegistry


class MRIPlugin(BaseMedicalReportPlugin):
    report_type = "mri"
    report_label = "MRI Report"
    section_order = [
        "Vitals", "Clinical History",
        "Technique", "Findings", "Comparison",
        "Contrast", "Impression", "Recommendations",
    ]


PluginRegistry.register(MRIPlugin())
