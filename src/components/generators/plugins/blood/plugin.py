"""Blood / Lab Report plugin."""

from ...plugin_base import BaseMedicalReportPlugin, PluginRegistry


class BloodReportPlugin(BaseMedicalReportPlugin):
    report_type = "blood_report"
    report_label = "Blood Report"
    section_order = [
        "Vitals",
        "Hemoglobin", "WBC", "Platelets", "RBC", "MCV", "MCH", "MCHC", "RDW",
        "Neutrophils", "Lymphocytes", "Monocytes", "Eosinophils", "Basophils",
        "HbA1c", "Glucose Fasting", "Glucose PP",
        "Total Cholesterol", "LDL Cholesterol", "HDL Cholesterol", "Triglycerides",
        "Creatinine", "BUN", "Urea", "Sodium", "Potassium", "Chloride",
        "TSH", "T3", "T4", "Vitamin D", "Vitamin B12",
        "Findings", "Impression", "Recommendations",
    ]


PluginRegistry.register(BloodReportPlugin())


class LabReportPlugin(BloodReportPlugin):
    report_type = "lab_report"
    report_label = "Lab Report"


PluginRegistry.register(LabReportPlugin())
