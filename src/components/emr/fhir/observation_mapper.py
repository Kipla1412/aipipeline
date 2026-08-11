"""FHIR Observation mapper with LOINC mapping and valueQuantity/valueString.

Uses fhir.resources Observation (64 fields, fully typed).
"""

from fhir.resources.observation import Observation
from fhir.resources.codeableconcept import CodeableConcept
from fhir.resources.coding import Coding
from fhir.resources.quantity import Quantity
from fhir.resources.range import Range

_LOINC: dict[str, dict] = {
    "Hemoglobin": {"system": "http://loinc.org", "code": "718-7"},
    "WBC": {"system": "http://loinc.org", "code": "6690-2"},
    "RBC": {"system": "http://loinc.org", "code": "789-8"},
    "Platelets": {"system": "http://loinc.org", "code": "777-3"},
    "Glucose (Fasting)": {"system": "http://loinc.org", "code": "1558-6"},
    "HbA1c": {"system": "http://loinc.org", "code": "4548-4"},
    "Creatinine": {"system": "http://loinc.org", "code": "2160-0"},
    "Sodium": {"system": "http://loinc.org", "code": "2951-2"},
    "Potassium": {"system": "http://loinc.org", "code": "2823-3"},
    "Total Cholesterol": {"system": "http://loinc.org", "code": "2093-3"},
    "LDL Cholesterol": {"system": "http://loinc.org", "code": "2089-1"},
    "HDL Cholesterol": {"system": "http://loinc.org", "code": "2085-9"},
    "Triglycerides": {"system": "http://loinc.org", "code": "2571-8"},
    "Blood Pressure": {"system": "http://loinc.org", "code": "85354-9"},
    "Heart Rate": {"system": "http://loinc.org", "code": "8867-4"},
    "Temperature": {"system": "http://loinc.org", "code": "8310-5"},
    "Weight": {"system": "http://loinc.org", "code": "29463-7"},
    "Height": {"system": "http://loinc.org", "code": "8302-2"},
    "BMI": {"system": "http://loinc.org", "code": "39156-5"},
    "ALT": {"system": "http://loinc.org", "code": "1742-6"},
    "AST": {"system": "http://loinc.org", "code": "1920-8"},
    "BUN": {"system": "http://loinc.org", "code": "3094-0"},
    "Total Bilirubin": {"system": "http://loinc.org", "code": "1975-2"},
    "Albumin": {"system": "http://loinc.org", "code": "1751-7"},
    "Total Protein": {"system": "http://loinc.org", "code": "2885-2"},
    "Chloride": {"system": "http://loinc.org", "code": "2075-0"},
    "MCV": {"system": "http://loinc.org", "code": "787-2"},
    "MCH": {"system": "http://loinc.org", "code": "785-6"},
    "MCHC": {"system": "http://loinc.org", "code": "786-4"},
    "RDW": {"system": "http://loinc.org", "code": "788-0"},
}

_CATEGORY = {
    "vital_signs": ("vital-signs", "Vital Signs"),
    "laboratory": ("laboratory", "Laboratory"),
    "imaging": ("imaging", "Imaging"),
    "ecg": ("procedure", "ECG"),
    "pathology": ("laboratory", "Pathology"),
    "microbiology": ("laboratory", "Microbiology"),
}

_INTERPRETATION = {
    "low": "L", "normal": "N", "high": "H", "abnormal": "A",
    "critical": "LL", "overweight": "H",
}


class ObservationMapper:
    def map(self, obs: dict, patient_id: str) -> Observation:
        dt = obs.get("effective_datetime")
        if dt and isinstance(dt, str):
            dt = dt.replace(" ", "T")
            if "Z" not in dt and "+" not in dt:
                dt = dt + "Z"

        fhir = Observation(
            status="final",
            code=CodeableConcept(text=obs.get("display_name", "")),
            subject={"reference": f"Patient/{patient_id}"},
            effectiveDateTime=dt,
        )

        # Category
        cat_code, cat_display = _CATEGORY.get(obs.get("category", ""), ("laboratory", "Laboratory"))
        fhir.category = [
            CodeableConcept(
                coding=[
                    Coding(
                        system="http://terminology.hl7.org/CodeSystem/observation-category",
                        code=cat_code,
                        display=cat_display,
                    )
                ]
            )
        ]

        # Code (LOINC)
        name = obs.get("display_name", "")
        code_codings = []
        loinc = _LOINC.get(name)
        if loinc:
            code_codings.append(Coding(**loinc))
        code_codings.append(Coding(display=name))
        fhir.code = CodeableConcept(coding=code_codings)

        # Value
        value = obs.get("value")
        unit = obs.get("unit")
        if value is not None:
            try:
                fhir.valueQuantity = Quantity(value=float(value), unit=unit)
            except (ValueError, TypeError):
                fhir.valueString = str(value)

        # Reference range
        ref = obs.get("reference_range")
        if ref:
            fhir.referenceRange = [{"text": ref}]

        # Interpretation
        interp = obs.get("interpretation")
        if interp:
            code = _INTERPRETATION.get(str(interp).lower().strip(), interp.upper()[:1])
            fhir.interpretation = [
                CodeableConcept(
                    coding=[
                        Coding(
                            system="http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation",
                            code=code,
                        )
                    ]
                )
            ]

        # Body site
        body_site = obs.get("body_site")
        if body_site:
            fhir.bodySite = CodeableConcept(text=str(body_site))

        return fhir
