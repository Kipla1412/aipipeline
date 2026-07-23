"""ECG report plugin."""

from ...plugin_base import BaseMedicalReportPlugin, PluginRegistry


class ECGPlugin(BaseMedicalReportPlugin):
    report_type = "ecg"
    report_label = "ECG Report"
    section_order = [
        "Vitals",
        "Rhythm", "Heart Rate", "PR Interval", "QRS Duration", "QT Interval",
        "QTc Interval", "Axis", "P Wave", "ST Segment", "T Wave", "U Wave",
        "Findings", "Impression", "Interpretation", "Recommendations",
    ]


PluginRegistry.register(ECGPlugin())
