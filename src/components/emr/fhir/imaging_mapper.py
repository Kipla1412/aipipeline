"""FHIR ImagingStudy mapper."""

from fhir.resources.imagingstudy import ImagingStudy


class ImagingStudyMapper:
    def map(self, imaging: dict, patient_id: str) -> ImagingStudy:
        return ImagingStudy(
            status="available",
            modality=[{"system": "http://dicom.nema.org/resources/ontology/DCM",
                        "code": imaging.get("modality", "")}],
            subject={"reference": f"Patient/{patient_id}"},
            identifier=[{"system": "urn:dicom:uid", "value": imaging.get("study_uid", "")}]
            if imaging.get("study_uid") else [],
        )
