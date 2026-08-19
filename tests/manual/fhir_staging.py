from src.components.fhir_staging.client import FhirStagingClient
import json

def main():
    print("=" * 60)
    print("FHIR Staging API Test")
    print("=" * 60)

    with FhirStagingClient() as client:

        print("\n--- Pending records ---")

        records = client.list_pending_records()

        print(f"Found {len(records)} pending record(s)")

        for record in records:
            print("\nRecord:")
            print(f"  staging_record_id: {record.get('staging_record_id')}")
            print(f"  file_id:           {record.get('file_id')}")
            print(f"  filename:          {record.get('attachment_title')}")
            print(f"  patient_id:        {record.get('patient_id')}")
            print(f"  service_request:   {record.get('service_request_id')}")
            print(f"  status:             {record.get('status')}")

        record = records[0]

        record_id = record.get("staging_record_id") or record.get("id")

        print(f"\nUpdating record {record_id} → processing")

        updated = client.update_status(
            record_id,
            "processing",
        )

        print("\nUpdated record:")
        print(json.dumps(updated, indent=2, default=str))

if __name__ == "__main__":
    main()