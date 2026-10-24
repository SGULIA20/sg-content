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


def test_match_scales_by_fact_unit_crore_and_lakh():
    facts = [{"number": 24400.0, "unit": "crore INR"}, {"number": 2.44, "unit": "lakh crore INR"}, {"number": 316.418, "unit": "crore INR"}]
    assert claims.match("States ne 24,400 crore udhaar maanga", facts, []) == []
    assert claims.match("2.44 lakh crore ka udhaar", facts, []) == []
    assert claims.match("Punjab ko 316 crore mila", facts, []) == []            # 316 vs 316.418 within half a percent? no: 0.13 % → pass
    assert claims.match("Punjab ko 320 crore mila", facts, []) == [320e7]


def test_rounded_numbers_pass_when_the_script_says_about():
    facts = [{"number": 7.247, "unit": "crore shares"}, {"number": 5.54, "unit": "pct"}]
    assert claims.match("lagbhag 7 crore shares diye", facts, []) == []
    assert claims.match("mehngai karib 5.5 percent", facts, []) == []
    assert claims.match("7 crore shares diye", facts, []) == [7e7]                 # no 'about' word: exact match still required


def test_years_with_era_words_are_not_claims():
    assert claims.match("Mahabharat 3102 BCE mein hua, kuch kehte hain 1500 BC", facts=[], library=[]) == []
    assert claims.match("yeh 1200 ईसा पूर्व ki baat hai, mandir 1010 CE mein bana", facts=[], library=[]) == []
    assert claims.match("36 metre neeche deewar mili", facts=[], library=[]) == [36.0]


def test_index_names_and_the_topics_own_number_are_not_claims():
    """21 Oct 2026: a long on '500 rupaye ki SIP' was rejected three times for '500' and 'Nifty 50'."""
    text = "Bhai ki 500 rupaye mahine ki SIP. Nifty 50 aur Nifty 500 TRI mein, Sensex 30 bhi. Return 11 percent maan lo."
    assert claims.match(text, [], [], context=("500 rupaye mahine ki SIP: 20 saal mein kya bana",)) == [11.0]
    assert 500.0 in claims.match(text, [], [])                     # without the topic, 500 still needs a source
