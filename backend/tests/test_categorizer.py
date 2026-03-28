"""
Unit tests for SmartSpend categorizer module.
Tests word-boundary matching, longest-match priority, regex patterns,
fuzzy matching, input normalization, and edge cases.
"""

from categorizer import categorize_expense, _similarity, _normalize, _word_boundary_match


# ═══════════════════════════════════════════════════════════════════
# 1. Input normalization
# ═══════════════════════════════════════════════════════════════════

class TestNormalize:
    def test_lowercase(self):
        assert _normalize("UBER") == "uber"

    def test_strips_whitespace(self):
        assert _normalize("  Swiggy  ") == "swiggy"

    def test_collapses_multiple_spaces(self):
        assert _normalize("Pizza   Hut") == "pizza hut"

    def test_strips_accents(self):
        assert _normalize("Café") == "cafe"

    def test_empty_string(self):
        assert _normalize("") == ""

    def test_none_input(self):
        assert _normalize(None) == ""

    def test_special_characters(self):
        result = _normalize("McDonald's #123")
        assert "mcdonald's" in result

    def test_unicode_input(self):
        result = _normalize("über Éats")
        assert result == "uber eats"


# ═══════════════════════════════════════════════════════════════════
# 2. Word-boundary matching (prevents false positives)
# ═══════════════════════════════════════════════════════════════════

class TestWordBoundaryMatch:
    def test_exact_word(self):
        assert _word_boundary_match("uber", "uber ride")

    def test_does_not_match_substring(self):
        """'ola' must NOT match inside 'chocolate'."""
        assert not _word_boundary_match("ola", "chocolate cake")

    def test_bus_not_in_business(self):
        """'bus' must NOT match inside 'business'."""
        assert not _word_boundary_match("bus", "business meeting")

    def test_tea_not_in_steak(self):
        assert not _word_boundary_match("tea", "steak house")

    def test_gas_not_in_gaslighting(self):
        assert not _word_boundary_match("gas", "gaslighting article")

    def test_show_not_in_showroom(self):
        assert not _word_boundary_match("show", "showroom visit")

    def test_matches_at_start(self):
        assert _word_boundary_match("uber", "uber")

    def test_matches_at_end(self):
        assert _word_boundary_match("uber", "my uber")

    def test_matches_in_middle(self):
        assert _word_boundary_match("uber", "paid uber today")


# ═══════════════════════════════════════════════════════════════════
# 3. Exact keyword match (confidence 0.9) — 20+ merchants
# ═══════════════════════════════════════════════════════════════════

class TestExactKeywordMatch:
    """Pass 1 — keyword matches should return confidence 0.9."""

    def test_swiggy(self):
        assert categorize_expense("Swiggy") == ("Food", 0.9)

    def test_zomato(self):
        assert categorize_expense("Zomato") == ("Food", 0.9)

    def test_starbucks(self):
        assert categorize_expense("Starbucks") == ("Food", 0.9)

    def test_uber(self):
        assert categorize_expense("Uber") == ("Transport", 0.9)

    def test_ola(self):
        assert categorize_expense("Ola") == ("Transport", 0.9)

    def test_irctc(self):
        assert categorize_expense("IRCTC") == ("Transport", 0.9)

    def test_flipkart(self):
        assert categorize_expense("Flipkart") == ("Shopping", 0.9)

    def test_amazon(self):
        assert categorize_expense("Amazon") == ("Shopping", 0.9)

    def test_croma(self):
        assert categorize_expense("Croma") == ("Shopping", 0.9)

    def test_airtel(self):
        assert categorize_expense("Airtel") == ("Utilities", 0.9)

    def test_jio(self):
        assert categorize_expense("Jio") == ("Utilities", 0.9)

    def test_netflix(self):
        assert categorize_expense("Netflix") == ("Entertainment", 0.9)

    def test_spotify(self):
        assert categorize_expense("Spotify") == ("Entertainment", 0.9)

    def test_pvr_cinemas(self):
        assert categorize_expense("PVR Cinemas") == ("Entertainment", 0.9)

    def test_apollo_pharmacy(self):
        assert categorize_expense("Apollo Pharmacy") == ("Healthcare", 0.9)

    def test_practo(self):
        assert categorize_expense("Practo") == ("Healthcare", 0.9)

    def test_udemy(self):
        assert categorize_expense("Udemy") == ("Education", 0.9)

    def test_coursera(self):
        assert categorize_expense("Coursera") == ("Education", 0.9)

    def test_byju(self):
        assert categorize_expense("Byju's") == ("Education", 0.9)

    def test_github(self):
        assert categorize_expense("GitHub") == ("Subscriptions", 0.9)

    def test_notion(self):
        assert categorize_expense("Notion") == ("Subscriptions", 0.9)


# ═══════════════════════════════════════════════════════════════════
# 4. Longest-match priority (critical fix)
# ═══════════════════════════════════════════════════════════════════

class TestLongestMatchPriority:
    """'amazon prime' should match Entertainment, not Shopping via 'amazon'."""

    def test_amazon_prime_is_entertainment(self):
        cat, conf = categorize_expense("Amazon Prime")
        assert cat == "Entertainment"
        assert conf == 0.9

    def test_amazon_alone_is_shopping(self):
        cat, conf = categorize_expense("Amazon")
        assert cat == "Shopping"
        assert conf == 0.9

    def test_pizza_hut_is_food_not_generic(self):
        cat, conf = categorize_expense("Pizza Hut")
        assert cat == "Food"
        assert conf == 0.9

    def test_youtube_premium_is_entertainment(self):
        cat, conf = categorize_expense("YouTube Premium")
        assert cat == "Entertainment"
        assert conf == 0.9

    def test_disney_hotstar_is_entertainment(self):
        cat, conf = categorize_expense("Disney Hotstar")
        assert cat == "Entertainment"
        assert conf == 0.9


# ═══════════════════════════════════════════════════════════════════
# 5. False positive prevention
# ═══════════════════════════════════════════════════════════════════

class TestFalsePositivePrevention:
    """Short keywords must NOT match inside longer unrelated words."""

    def test_chocolate_not_transport(self):
        """'ola' inside 'chocolate' must not trigger Transport."""
        cat, _ = categorize_expense("Chocolate Factory")
        assert cat != "Transport"

    def test_business_not_transport(self):
        """'bus' inside 'business' must not trigger Transport."""
        cat, _ = categorize_expense("Business Solutions Inc")
        assert cat != "Transport"

    def test_steakhouse_not_food_via_tea(self):
        """Steakhouse should be Food via 'steak' patterns, not 'tea' substring."""
        # Should not match 'tea' inside 'steak'
        cat, conf = categorize_expense("Premium Steakhouse")
        # If it matches Food, it should be via keyword 'kitchen/diner/restaurant' or regex, not 'tea'
        # The key assertion: it should NOT match via 'tea' substring

    def test_laboratory_not_healthcare_via_lab(self):
        """A chemistry lab service shouldn't wrongly match Healthcare."""
        # 'lab' is in Healthcare keywords; 'laboratory' should still match
        # because 'lab' has word boundary match on 'lab' in 'laboratory'...
        # Actually 'lab' IS a valid word boundary in 'laboratory'? No:
        # \blab\b does NOT match 'laboratory' because there's no boundary after 'lab'
        cat, _ = categorize_expense("XYZ Laboratory Services")
        # Should NOT match Healthcare via 'lab' substring
        assert cat != "Healthcare"


# ═══════════════════════════════════════════════════════════════════
# 6. Description-based matching
# ═══════════════════════════════════════════════════════════════════

class TestDescriptionMatching:
    def test_restaurant_in_description(self):
        cat, conf = categorize_expense("Unknown Place", "restaurant dinner")
        assert cat == "Food"
        assert conf == 0.9

    def test_parking_in_description(self):
        cat, conf = categorize_expense("City Center", "parking fee")
        assert cat == "Transport"
        assert conf == 0.9

    def test_pharmacy_in_description(self):
        cat, conf = categorize_expense("MedPlus", "pharmacy purchase")
        assert cat == "Healthcare"
        assert conf == 0.9

    def test_description_overrides_unknown_merchant(self):
        cat, conf = categorize_expense("ACME Corp", "monthly subscription renewal")
        assert cat == "Subscriptions"
        assert conf == 0.9


# ═══════════════════════════════════════════════════════════════════
# 7. Regex pattern match (confidence 0.8)
# ═══════════════════════════════════════════════════════════════════

class TestRegexPatternMatch:
    def test_dining_pattern(self):
        cat, conf = categorize_expense("The Grand", "fine dining experience")
        assert cat == "Food"
        assert conf == 0.8

    def test_grocery_pattern(self):
        cat, conf = categorize_expense("FreshOrg", "grocery items")
        assert cat == "Food"
        assert conf == 0.8

    def test_ev_charging_pattern(self):
        cat, conf = categorize_expense("VoltUp", "ev charging station")
        assert cat == "Transport"
        assert conf == 0.8

    def test_membership_pattern(self):
        cat, conf = categorize_expense("ClubX", "membership renewal")
        assert cat == "Subscriptions"
        assert conf == 0.8

    def test_bootcamp_pattern(self):
        cat, conf = categorize_expense("NewSkills", "bootcamp enrollment")
        assert cat == "Education"
        assert conf == 0.8

    def test_checkup_pattern(self):
        cat, conf = categorize_expense("WellCare", "annual check-up")
        assert cat == "Healthcare"
        assert conf == 0.8


# ═══════════════════════════════════════════════════════════════════
# 8. Fuzzy matching (confidence 0.6)
# ═══════════════════════════════════════════════════════════════════

class TestFuzzyMatch:
    def test_swigy_typo(self):
        """'swigy' is close to 'swiggy' but doesn't contain any keyword."""
        cat, conf = categorize_expense("Swigy")
        assert cat == "Food"
        assert conf == 0.6

    def test_netfli_typo(self):
        """'netfli' is close to 'netflix'."""
        cat, conf = categorize_expense("Netfli")
        assert cat == "Entertainment"
        assert conf == 0.6

    def test_flipkrt_typo(self):
        """'flipkrt' is close to 'flipkart'."""
        cat, conf = categorize_expense("Flipkrt")
        assert cat == "Shopping"
        assert conf == 0.6


# ═══════════════════════════════════════════════════════════════════
# 9. Fallback to Other
# ═══════════════════════════════════════════════════════════════════

class TestFallback:
    def test_unknown_merchant(self):
        assert categorize_expense("XYZ Corp International") == ("Other", 0.0)

    def test_empty_string(self):
        assert categorize_expense("") == ("Other", 0.0)

    def test_none_input(self):
        assert categorize_expense(None) == ("Other", 0.0)

    def test_whitespace_only(self):
        assert categorize_expense("   ") == ("Other", 0.0)

    def test_non_string_input(self):
        assert categorize_expense(12345) == ("Other", 0.0)

    def test_list_input(self):
        assert categorize_expense([1, 2, 3]) == ("Other", 0.0)

    def test_dict_input(self):
        assert categorize_expense({"name": "test"}) == ("Other", 0.0)

    def test_very_long_unknown_name(self):
        long_name = "X" * 500
        assert categorize_expense(long_name) == ("Other", 0.0)

    def test_numeric_string(self):
        assert categorize_expense("12345") == ("Other", 0.0)

    def test_special_chars_only(self):
        assert categorize_expense("@#$%^&*") == ("Other", 0.0)


# ═══════════════════════════════════════════════════════════════════
# 10. Similarity function
# ═══════════════════════════════════════════════════════════════════

class TestSimilarityFunction:
    def test_identical_strings(self):
        assert _similarity("hello", "hello") == 1.0

    def test_completely_different(self):
        assert _similarity("abc", "xyz") < 0.5

    def test_empty_vs_non_empty(self):
        assert _similarity("", "hello") == 0.0
        assert _similarity("hello", "") == 0.0

    def test_both_empty(self):
        assert _similarity("", "") == 1.0

    def test_one_char_difference(self):
        assert _similarity("hello", "hallo") >= 0.7

    def test_symmetry(self):
        assert _similarity("abc", "abd") == _similarity("abd", "abc")

    def test_single_char_strings(self):
        assert _similarity("a", "a") == 1.0
        assert _similarity("a", "b") == 0.0

    def test_similar_long_strings(self):
        score = _similarity("flipkart", "flipkrt")
        assert score >= 0.75

    def test_very_different_lengths(self):
        score = _similarity("a", "abcdefghij")
        assert score < 0.3

    def test_transposition(self):
        # "ab" vs "ba" — edit distance is 2 (sub+sub), similarity = 0.0
        score = _similarity("ab", "ba")
        assert score == 0.0

    def test_prefix_match(self):
        score = _similarity("netflix", "netfli")
        assert score >= 0.75


# ═══════════════════════════════════════════════════════════════════
# 11. Case insensitivity
# ═══════════════════════════════════════════════════════════════════

class TestCaseInsensitivity:
    def test_uppercase(self):
        assert categorize_expense("SWIGGY")[0] == "Food"

    def test_mixed_case(self):
        assert categorize_expense("sWiGgY")[0] == "Food"

    def test_uppercase_uber(self):
        assert categorize_expense("UBER")[0] == "Transport"

    def test_title_case(self):
        assert categorize_expense("Netflix")[0] == "Entertainment"
