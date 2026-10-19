from engine import claims


def test_hindi_number_words_match_digits():
    assert claims.numbers_in("India apna assi pratishat tel bahar se khareedta hai") == [80.0]
    assert claims.numbers_in("do hazaar paanch sau rupaye") == [2500.0]
    assert claims.numbers_in("₹1.5 lakh crore ka profit") == [1.5e12]


def test_digits_with_indian_separators_and_percent():
    assert claims.numbers_in("EMI ₹1,50,000 se badh kar 12% hui") == [150000.0, 12.0]


def test_devanagari_words_and_digits():
    assert claims.numbers_in("अस्सी प्रतिशत तेल, ८५ हज़ार करोड़") == [80.0, 85000e7]


def test_plain_small_numbers_and_years():
    assert claims.numbers_in("teen cheezein badalti hain, 2026 mein") == [3.0, 2026.0]


def test_unmatched_number_is_reported():
    assert claims.match("profit 12 pratishat badha", facts=[{"number": 11.0}], library=[]) == [12.0]


def test_matched_within_tolerance_passes():
    assert claims.match("profit 12 pratishat badha", facts=[{"number": 12.04}], library=[]) == []


def test_library_fact_counts_as_source():
    lib = [{"id": "gst-18", "number": 18.0}]
    assert claims.match("GST atharah pratishat hai", facts=[], library=lib) == []


def test_small_counts_are_not_claims():
    # one, two, three used as counters ("teen cheezein") are never facts to source
    assert claims.match("teen cheezein, pehli, doosri, teesri", facts=[], library=[]) == []


def test_load_library_has_sourced_entries():
    lib = claims.load_library()
    assert len(lib) >= 12
    assert all(e["source_url"].startswith("http") and e["number"] is not None for e in lib)
