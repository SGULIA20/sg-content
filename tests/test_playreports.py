from engine import playreports as pr


def test_summarise_totals_countries_rating_and_conversion():
    installs = [{"Date": f"2026-10-{d:02d}", "Daily Device Installs": "2", "Daily Device Uninstalls": "1", "Active Device Installs": str(10 + d)} for d in range(1, 11)]
    countries = [{"Date": "2026-10-05", "Country": "IN", "Daily Device Installs": "7"}, {"Date": "2026-10-06", "Country": "NG", "Daily Device Installs": "3"},
                 {"Date": "2026-10-07", "Country": "IN", "Daily Device Installs": "5"}]
    ratings = [{"Date": "2026-10-01", "Total Average Rating": "4.0"}, {"Date": "2026-10-09", "Total Average Rating": "4.5"}]
    store = [{"Date": "2026-10-02", "Store Listing Visitors": "100", "Store Listing Acquisitions": "20"}, {"Date": "2026-10-03", "Store Listing Visitors": "100", "Store Listing Acquisitions": "10"}]
    text = pr.summarise("scoremybiz", installs, countries, ratings, store)
    assert "installs 20, uninstalls 10, active devices 20 (last 10 days)" in text
    assert "by country: IN 12, NG 3" in text and "rating 4.50 stars" in text
    assert "listing visitors 200, acquisitions 30, conversion 15.0%" in text


def test_summarise_skips_sections_without_data():
    assert pr.summarise("waypoint", [], [], [], []) == "waypoint"


def test_latest_files_picks_the_newest_months_for_one_package():
    objs = [f"stats/installs/installs_com.x.app_2026{m:02d}_overview.csv" for m in (8, 9, 10)] + ["stats/installs/installs_com.y.app_202610_overview.csv"]
    assert pr._latest_files(objs, "com.x.app", "installs", "_overview.csv") == objs[1:3]


def test_token_request_is_a_signed_jwt_for_the_reader_account(tmp_path, monkeypatch):
    import json, subprocess
    key_pem = subprocess.run(["openssl", "genrsa", "2048"], capture_output=True, text=True, check=True).stdout
    kf = tmp_path / "k.json"; kf.write_text(json.dumps({"client_email": "r@p.iam.gserviceaccount.com", "private_key": key_pem}))
    seen = {}
    class R:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'{"access_token": "tok123"}'
    def post(req):
        seen["body"] = req.data.decode(); return R()
    assert pr.access_token(pr.SCOPE_STORAGE, kf, post=post) == "tok123"
    assert "grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Ajwt-bearer" in seen["body"] and seen["body"].count(".") >= 2
