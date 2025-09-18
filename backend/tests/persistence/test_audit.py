import json
from app.persistence.audit import write_audit_json


def test_write_audit_json_writes_schema_and_fields(tmp_path):
    out_dir = tmp_path / "audit"
    path = write_audit_json(
        bank="FABMISR",
        file_id="30029.jpg",
        decision={
            "decision": "review",
            "stp": False,
            "overall_conf": 0.932,
            "low_conf_fields": ["name"],
            "reasons": ["low_confidence:name:0.932<thr0.995"],
        },
        per_field={
            "name": {
                "field_conf": 0.932,
                "loc_conf": 0.989,
                "ocr_conf": 0.940,
                "parse_ok": True,
                "parse_norm": "شركة بالم زليه للتعمير",
                "ocr_text": "شركة بالم زليه للتعمير",
                "ocr_lang": "ar",
                "meets_threshold": False,
                "validation": {"ok": True, "code": "OK"},
            }
        },
        out_dir=str(out_dir),
        source_csv="backend/reports/pipeline/FABMISR_pipeline_eval.csv",
        correlation_id="test-corr-123",
        extra_meta={"env": "test"},
    )

    assert path.endswith("30029.jpg.json")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["schema_version"] == 1
    assert data["bank"] == "FABMISR"
    assert data["file"] == "30029.jpg"
    assert data["decision"]["decision"] == "review"
    assert isinstance(data["fields"], dict)
    assert "name" in data["fields"]
    assert data["fields"]["name"]["meets_threshold"] is False
    assert data["correlation_id"] == "test-corr-123"
    assert data["meta"]["env"] == "test"
