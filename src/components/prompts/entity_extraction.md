# Medical Entity Extraction

Extract medical entity mentions from the user's question.
Return ONLY a JSON object with "labels" (list of entity names mentioned) and "entity_type" (one of: patient, doctor, hospital, disease, medication, procedure, report, or null if unclear).

Examples:
Q: "What medications is Alice Raj taking?"
A: {"labels": ["Alice Raj"], "entity_type": "patient"}

Q: "Who treats cardiomegaly at Mercy Medical Center?"
A: {"labels": ["Cardiomegaly", "Mercy Medical Center"], "entity_type": null}

Q: "List all patients with hypertension"
A: {"labels": ["Hypertension"], "entity_type": "disease"}

Return valid JSON only. No markdown, no explanation.
