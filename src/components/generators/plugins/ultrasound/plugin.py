"""Ultrasound report plugin."""

from ...plugin_base import BaseMedicalReportPlugin, PluginRegistry


class UltrasoundPlugin(BaseMedicalReportPlugin):
    report_type = "ultrasound"
    report_label = "Ultrasound Report"
    section_order = [
        "Vitals", "Clinical History", "Indication",
        "Technique", "Findings", "Measurements",
        "Doppler", "Impression", "Recommendations",
    ]


PluginRegistry.register(UltrasoundPlugin())
