"""
SmartSpend — Expense Categorization Engine (Module 5)
=====================================================
Rule-based classifier that assigns spending categories to expenses using
merchant names and descriptions. Uses a three-tier matching strategy:

1. Exact keyword match (confidence 0.9) — longest match wins
2. Regex pattern match (confidence 0.8)
3. Fuzzy match via custom Levenshtein similarity (confidence 0.6)

Falls back to ("Other", 0.0) for unrecognized merchants.

Categories: Food, Transport, Shopping, Utilities, Entertainment,
            Healthcare, Education, Subscriptions, Other

No external libraries — fuzzy matching uses a custom Levenshtein-like
similarity function implemented from scratch.

IMPORTANT: All keywords use word-boundary matching to prevent false positives
(e.g., "ola" must not match "chocolate", "bus" must not match "business").
Keywords are matched longest-first so "amazon prime" beats "amazon".

Used by create_expense and update_expense Lambda functions via the shared CommonLayer.
"""

import re
import logging
import unicodedata

logger = logging.getLogger(__name__)

# ── Category Rules ──────────────────────────────────────────────────
# Each category has 'keywords' (word-boundary match) and 'patterns' (regex).
# Multi-word brand names are matched longest-first across ALL categories
# so "amazon prime" (Entertainment) wins over "amazon" (Shopping).

CATEGORY_RULES = {
    "Food": {
        "keywords": [
            "swiggy", "zomato", "mcdonald", "dominos", "domino's", "starbucks",
            "kfc", "pizza hut", "burger king", "subway", "haldiram",
            "barbeque nation", "cafe coffee day", "dunkin donuts", "dunkin",
            "baskin robbins", "behrouz biryani", "behrouz", "chai point",
            "restaurant", "food court", "food", "pizza", "burger", "cafe",
            "coffee", "bakery", "biryani", "chicken", "kitchen", "dhaba",
            "canteen", "tiffin", "juice", "ice cream", "dessert", "chai",
            "snack", "diner", "sweets",
        ],
        "patterns": [
            r"\b(eat|dine|dining|meal|lunch|dinner|breakfast|brunch)\b",
            r"\b(grocer|grocery|supermarket|fresh mart|organic)\b",
        ],
    },
    "Transport": {
        "keywords": [
            "uber cab", "ola cab", "ola cabs", "uber", "ola", "rapido",
            "irctc", "metro smart card", "blusmart", "namma yatri",
            "meru cabs", "redbus", "delhi metro", "mumbai local",
            "cab", "taxi", "auto rickshaw", "rickshaw", "metro", "bus stand",
            "bus ticket", "train", "railway", "parking", "fuel", "petrol",
            "diesel", "toll",
        ],
        "patterns": [
            r"\b(commute|travel fare|ride share|rideshare)\b",
            r"\b(gas station|fuel station|ev charging)\b",
            r"\b(cab ride|taxi ride|auto ride|bus fare|train fare)\b",
        ],
    },
    "Shopping": {
        "keywords": [
            "flipkart", "amazon shopping", "amazon", "myntra", "ajio",
            "meesho", "croma", "reliance digital", "big bazaar", "dmart",
            "shoppers stop", "tata cliq", "snapdeal",
            "mart", "bazaar", "retail", "fashion", "clothing", "apparel",
            "electronics", "mall",
        ],
        "patterns": [
            r"\b(purchase|bought|ecommerce|e-commerce)\b",
            r"\b(wholesale|outlet|warehouse)\b",
        ],
    },
    "Utilities": {
        "keywords": [
            "airtel", "jio recharge", "jio", "vodafone", "bsnl",
            "act fibernet", "tata power", "mahanagar gas", "indane gas",
            "bescom", "hathway", "tneb",
            "electricity", "water bill", "broadband", "internet", "wifi",
            "telecom", "mobile recharge", "recharge", "postpaid", "prepaid",
            "bill pay",
        ],
        "patterns": [
            r"\b(utility|utilities|electric bill|power bill|sewage)\b",
            r"\b(phone bill|cell bill|internet bill|gas bill)\b",
        ],
    },
    "Entertainment": {
        "keywords": [
            "netflix", "spotify", "amazon prime", "disney hotstar",
            "bookmyshow", "pvr cinemas", "pvr", "inox", "youtube premium",
            "sonyliv", "zee5", "jiocinema",
            "movie", "cinema", "theatre", "theater", "gaming",
            "concert", "amusement",
        ],
        "patterns": [
            r"\b(streaming|twitch|vod|live show|stand-?up)\b",
            r"\b(arcade|bowling|karaoke|theme park)\b",
        ],
    },
    "Healthcare": {
        "keywords": [
            "apollo pharmacy", "apollo hospital", "medplus", "practo",
            "pharmeasy", "1mg", "netmeds", "dr lal pathlabs", "thyrocare",
            "fortis hospital",
            "pharmacy", "hospital", "clinic", "doctor", "medical",
            "health", "diagnostic", "pathology", "dental", "medicine",
            "wellness",
        ],
        "patterns": [
            r"\b(dr\.?\s|physician|surgeon|therapy|therapist)\b",
            r"\b(prescription|pharma|checkup|check-up)\b",
        ],
    },
    "Education": {
        "keywords": [
            "udemy", "coursera", "unacademy", "byju", "chegg", "skillshare",
            "edx", "simplilearn", "vedantu", "linkedin learning", "pluralsight",
            "course", "tuition", "school", "college", "university",
            "academy", "education", "training", "exam",
        ],
        "patterns": [
            r"\b(tutorial|bootcamp|boot camp|workshop|seminar)\b",
            r"\b(textbook|ebook|e-book|study material)\b",
        ],
    },
    "Subscriptions": {
        "keywords": [
            "apple music", "gaana", "playstation store", "xbox game pass",
            "github", "notion", "figma", "chatgpt plus", "icloud",
            "subscription", "premium plan", "pro plan", "monthly plan",
            "annual plan",
        ],
        "patterns": [
            r"\b(recurring|auto.?renew|membership|saas)\b",
            r"\b(plan renewal|billing cycle)\b",
        ],
    },
}

# ── Pre-computed sorted keyword index ───────────────────────────────
# Built once at import time. Sorted by keyword length descending so
# "amazon prime" is checked before "amazon", "bus ticket" before "bus".
_KEYWORD_INDEX = []
for _cat, _rules in CATEGORY_RULES.items():
    for _kw in _rules["keywords"]:
        _KEYWORD_INDEX.append((_kw, _cat))
_KEYWORD_INDEX.sort(key=lambda x: len(x[0]), reverse=True)


def _normalize(text):
    """
    Normalize input text for matching.

    - Lowercase
    - Strip leading/trailing whitespace
    - Collapse multiple spaces into one
    - Strip accents (é → e)
    - Remove non-alphanumeric chars except spaces and hyphens
    """
    if not text:
        return ""
    # Lowercase and strip
    text = text.strip().lower()
    # Strip accents: NFD decomposition, remove combining chars
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    # Keep alphanumeric, spaces, hyphens, dots, apostrophes
    text = re.sub(r"[^a-z0-9\s\-\.\']", " ", text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _word_boundary_match(keyword, text):
    """
    Check if keyword appears in text with word boundaries.

    Uses regex \\b to prevent 'ola' matching 'chocolate' or
    'bus' matching 'business'.
    """
    pattern = r"\b" + re.escape(keyword) + r"\b"
    return bool(re.search(pattern, text))


def _similarity(s1, s2):
    """
    Custom Levenshtein-like similarity score between two strings.

    Uses edit distance (insertions, deletions, substitutions) normalized
    to a 0.0–1.0 range.  No external libraries.

    Returns:
        float: Similarity score between 0.0 (completely different) and
               1.0 (identical).
    """
    if s1 == s2:
        return 1.0
    len1, len2 = len(s1), len(s2)
    if len1 == 0 or len2 == 0:
        return 0.0

    # Wagner–Fischer algorithm with two-row optimization
    prev = list(range(len2 + 1))
    curr = [0] * (len2 + 1)

    for i in range(1, len1 + 1):
        curr[0] = i
        for j in range(1, len2 + 1):
            cost = 0 if s1[i - 1] == s2[j - 1] else 1
            curr[j] = min(
                prev[j] + 1,       # deletion
                curr[j - 1] + 1,   # insertion
                prev[j - 1] + cost  # substitution
            )
        prev, curr = curr, prev

    distance = prev[len2]
    max_len = max(len1, len2)
    return 1.0 - (distance / max_len)


def categorize_expense(merchant_name, description=""):
    """
    Categorize an expense based on merchant name and optional description.

    Matching strategy (in priority order):
    1. Word-boundary keyword match, longest first → confidence 0.9
    2. Regex pattern match → confidence 0.8
    3. Fuzzy match (similarity ≥ 0.75 against keywords) → confidence 0.6
    4. Fallback → ("Other", 0.0)

    Args:
        merchant_name: The merchant/vendor name string.
        description: Optional expense description for extra context.

    Returns:
        tuple[str, float]: (category, confidence_score) where confidence
            is between 0.0 and 1.0.
    """
    try:
        if not merchant_name or not isinstance(merchant_name, str):
            return ("Other", 0.0)

        merchant_norm = _normalize(merchant_name)
        desc_norm = _normalize(description) if description else ""
        text = f"{merchant_norm} {desc_norm}".strip()

        if not text:
            return ("Other", 0.0)

        # ── Pass 1: Word-boundary keyword match, longest first (0.9) ──
        for keyword, category in _KEYWORD_INDEX:
            if _word_boundary_match(keyword, text):
                return (category, 0.9)

        # ── Pass 2: Regex pattern match (0.8) ──
        for category, rules in CATEGORY_RULES.items():
            for pattern in rules["patterns"]:
                if re.search(pattern, text, re.IGNORECASE):
                    return (category, 0.8)

        # ── Pass 3: Fuzzy match against keywords (0.6) ──
        best_score = 0.0
        best_category = "Other"
        for keyword, category in _KEYWORD_INDEX:
            score = _similarity(merchant_norm, keyword)
            if score > best_score:
                best_score = score
                best_category = category

        if best_score >= 0.75:
            return (best_category, 0.6)

        # ── Fallback ──
        return ("Other", 0.0)

    except Exception as e:
        logger.warning("categorize_expense failed: %s", str(e))
        return ("Other", 0.0)
