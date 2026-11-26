import pytest

httpx = pytest.importorskip("httpx")  
from fastapi.testclient import TestClient  

from app.main import app  


def test_http_核证放量隔离边缘协同(db_path):
    with TestClient(app) as client:
        v = client.post("/api/入轨", json={"版本": [{
            "开关键": "api.skew",
            "版本号": 1,
            "版本键": "api.skew@1",
        }]})
        assert v.status_code == 200, v.text

        b = client.post("/api/分桶", json={
            "桶键": "api.skew-bucket",
            "开关键": "api.skew",
        })
        assert b.status_code == 200, b.text

        d = client.post("/api/下发", json={
            "票号": "票-api-skew",
            "版本键": "api.skew@1",
            "桶键": "api.skew-bucket",
        })
        assert d.status_code == 200, d.text

        for edge, seen, result in [
            ("edge-a", "api.skew@1", "确认"),
            ("edge-b", "api.skew@1", "确认"),
            ("edge-c", "api.skew@0", "确认"),
        ]:
            r = client.post("/api/回读", json={
                "票号": "票-api-skew",
                "边缘键": edge,
                "所见版本键": seen,
                "结果": result,
            })
            assert r.status_code == 200, r.text

        cert = client.get("/api/核证?票号=票-api-skew")
        assert cert.status_code == 200
        body = cert.json()
        assert body["确认集"] == ["edge-a", "edge-b"]
        assert body["偏差集"] == ["edge-c"]
        assert body["隔离集"] == ["edge-c"]
        assert body["valid"] is True

        iso = client.get("/api/隔离边缘").json()
        assert [x["边缘键"] for x in iso] == ["edge-c"]

        release = client.post("/api/放量", json={"票号": "票-api-skew"})
        assert release.status_code == 200, release.text
        rb = release.json()
        assert rb["放量调用成败"] is True
        assert rb["隔离边缘是否非空"] is True
        assert rb["状态"] == "部分放量"

        tickets = client.get("/api/下发票").json()
        ticket = next(x for x in tickets if x["票号"] == "票-api-skew")
        assert ticket["状态"] == "部分放量"
        assert ticket["隔离集合"] == ["edge-c"]

        verdict = client.post("/api/贯验")
        assert verdict.status_code == 200
        assert verdict.json()["是否通过"] is True
