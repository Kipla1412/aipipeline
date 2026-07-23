"""X-Ray report plugin."""

from ...plugin_base import BaseMedicalReportPlugin, PluginRegistry


class XRayPlugin(BaseMedicalReportPlugin):
    report_type = "xray"
    report_label = "X-Ray Report"
    section_order = [
        "Vitals", "Clinical History",
        "Technique", "Views", "Findings", "Comparison",
        "Impression", "Recommendations",
    ]


PluginRegistry.register(XRayPlugin())
