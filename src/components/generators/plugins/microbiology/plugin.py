"""Microbiology plugin."""

from ...plugin_base import BaseMedicalReportPlugin, PluginRegistry


class MicrobiologyPlugin(BaseMedicalReportPlugin):
    report_type = "microbiology"
    report_label = "Microbiology Report"
    section_order = [
        "Specimen Source", "Organism", "Colony Count",
        "Sensitivity", "Resistance", "MIC Values",
        "Findings", "Impression", "Recommendations",
    ]


PluginRegistry.register(MicrobiologyPlugin())
