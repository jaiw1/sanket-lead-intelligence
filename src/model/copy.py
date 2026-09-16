# -*- coding: utf-8 -*-
"""What the RM reads: reason chips, negative chips, and six-product call material.

Three kinds of sentence, and the difference between them is the product:

**Reasons** answer *why this customer, now*.  Each one is attached to a feature
whose SHAP contribution at this row is positive, so the chip is evidence rather
than decoration: if the model did not use the signal, the RM is not told about it.

**Negative chips** (SM-3) answer *why this might still not close*.  They are the
four window-shopper signals the mentors named, plus the two browsing tells and
contact fatigue.  They fire only when the behaviour is actually present **and**
the model docked the score for it, and the queue shows them next to the reasons
rather than hiding them — an RM who is told "this one balked at the fee last
time" makes a different call than one who is not.

**Pitch material** is the opener, the why-now, one likely objection and its
answer, in English or Hindi, for all six products.  Before SM-1 there were three.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# positive reasons
# --------------------------------------------------------------------------- #

#: feature -> (row -> sentence or None).  A chip is offered only if the feature's
#: contribution to *this* row's score was positive.
REASON = {
    "rent_ratio_6m": lambda r: (
        f"Rent debit up {int((r.rent_ratio_6m - 1) * 100)}% in 6 months — outgrowing the current home"
        if _num(r.rent_ratio_6m) > 1.12 else None),
    "bal_gr_6m": lambda r: (
        f"Average balance up {int((r.bal_gr_6m - 1) * 100)}% in 6 months — building a down-payment"
        if _num(r.bal_gr_6m) > 1.25 else None),
    "dwell_product_3m": lambda r: (
        f"{int(r.dwell_product_3m)} min on this product's pages in the last 90 days"
        if _num(r.dwell_product_3m) > 5 else None),
    "fuel_ratio_3m": lambda r: (
        f"Fuel + cab spend up {int((r.fuel_ratio_3m - 1) * 100)}% quarter-on-quarter — commute pain"
        if _num(r.fuel_ratio_3m) > 1.35 else None),
    "has_auto_emi": lambda r: (
        "No existing vehicle EMI anywhere in banking history" if _num(r.has_auto_emi) == 0 else None),
    "emi_share": lambda r: (
        f"Outside EMIs eat {int(r.emi_share * 100)}% of income — consolidation candidate"
        if _num(r.emi_share) > 0.14 else None),
    "other_bank_emi_share": lambda r: (
        f"{int(r.other_bank_emi_share * 100)}% of their EMI outflow goes to other lenders — winnable balance transfer"
        if _num(r.other_bank_emi_share) > 0.5 else None),
    "minbal_ratio": lambda r: (
        "Balance dips sharply before salary day — monthly squeeze" if _num(r.minbal_ratio) < 0.22 else None),
    "fd_drop": lambda r: (
        "Broke a fixed deposit recently — mobilising funds" if _num(r.fd_drop) == 1 else None),
    "credits_gr_6m": lambda r: (
        f"Credits up {int((r.credits_gr_6m - 1) * 100)}% in 6 months — rising income"
        if _num(r.credits_gr_6m) > 1.12 else None),
    "credits_cv_6m": lambda r: (
        "Volatile month-to-month income — scored on behavioural median, not payslip"
        if _num(r.credits_cv_6m) > 0.25 else None),
    "school_share": lambda r: (
        f"School / college fees are {int(r.school_share * 100)}% of monthly income — fee-season pressure"
        if _num(r.school_share) > 0.08 else None),
    "bonus_share_3m": lambda r: (
        "Large irregular credit landed in the last quarter — bonus or settlement"
        if _num(r.bonus_share_3m) > 0.30 else None),
    "kyc_event_6m": lambda r: (
        "Address or nominee updated recently — a life event is in progress"
        if _num(r.kyc_event_6m) >= 1 else None),
    # --- the application journey: why this one is a drop-off worth a call --- #
    "journey_stage_idx": lambda r: (
        f"Got as far as the {_STAGE.get(str(r.journey_stage_reached), str(r.journey_stage_reached))} "
        f"stage before walking away" if _num(r.journey_stage_idx) >= 4 else None),
    "journey_fee_paid": lambda r: (
        "Already paid the ₹1,000 processing fee on the abandoned application — money is committed"
        if _num(r.journey_fee_paid) == 1 else None),
    "days_since_abandon": lambda r: (
        f"Abandoned only {int(r.days_since_abandon)} days ago — still warm"
        if 0 <= _num(r.days_since_abandon) <= 45 else None),
    "journey_attempts": lambda r: (
        f"{int(r.journey_attempts)} separate applications on file — persistent need"
        if _num(r.journey_attempts) >= 2 else None),
    "journey_amount_requested": lambda r: (
        f"Asked for ₹{int(r.journey_amount_requested):,} last time — the need is sized"
        if _num(r.journey_amount_requested) > 0 else None),
    "is_dropoff_product": lambda r: (
        "This is the product they abandoned — pick the conversation back up where it stopped"
        if _num(r.is_dropoff_product) == 1 else None),
    "last_contact_days": lambda r: (
        "No contact on file in the last year — no campaign fatigue to work against"
        if _num(r.last_contact_days) > 365 else
        (f"No contact for {int(r.last_contact_days)} days — no fatigue to work against"
         if _num(r.last_contact_days) > 120 else None)),
}

_STAGE = {"start": "Start", "eligibility": "Eligibility", "kyc": "KYC", "docs": "Documents",
          "fee": "Fee", "offer": "Offer", "accept": "Acceptance", "disburse": "Disbursement"}


def _num(x) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return float("nan")
    return v


def reasons_for(row, contribs: dict[str, float], k: int = 3) -> list[str]:
    """Top ``k`` reason chips, ordered by the feature's contribution to this row."""
    out: list[str] = []
    for c, v in sorted(contribs.items(), key=lambda x: -x[1]):
        if v <= 0 or c not in REASON:
            continue
        try:
            s = REASON[c](row)
        except (AttributeError, TypeError, ValueError):
            s = None
        if s and s not in out:
            out.append(s)
        if len(out) >= k:
            break
    return out


# --------------------------------------------------------------------------- #
# negative chips  (SM-3)
# --------------------------------------------------------------------------- #

#: feature -> (row -> sentence or None).  These are the mentors' four window-shopper
#: signals plus the browsing and fatigue tells.  A chip fires only when the
#: behaviour is present *and* the model's contribution for it is negative.
NEGATIVE = {
    "journey_blank_field_ratio": lambda r: (
        f"Left {int(round(_num(r.journey_blank_field_ratio) * 100))}% of the application fields blank"
        if _num(r.journey_blank_field_ratio) >= 0.25 else None),
    "journey_refused_income": lambda r: (
        "Would not share income details" if _num(r.journey_refused_income) == 1 else None),
    "journey_fee_balk": lambda r: (
        "Balked at the ₹1,000 processing fee when it was quoted"
        if _num(r.journey_fee_balk) == 1 else None),
    "journey_doc_refusal": lambda r: (
        "Refused to submit documents" if _num(r.journey_doc_refusal) == 1 else None),
    "journey_multi_product_revisits": lambda r: (
        f"Shopping around — {int(r.journey_multi_product_revisits)} other products browsed or applied for"
        if _num(r.journey_multi_product_revisits) >= 1 else None),
    "journey_docs_shortfall": lambda r: (
        "Supplied only part of the document checklist" if _num(r.journey_docs_shortfall) == 1 else None),
    "journey_stated_income_ratio": lambda r: (
        f"Stated income {int(round((_num(r.journey_stated_income_ratio) - 1) * 100))}% above what the account shows"
        if _num(r.journey_stated_income_ratio) > 1.08 else None),
    "contacts_30d": lambda r: (
        f"Contacted {int(r.contacts_30d)} times in the last 30 days — campaign fatigue"
        if _num(r.contacts_30d) >= 2 else None),
    "journey_open_now": lambda r: (
        "Another application is still open — do not double-pitch"
        if _num(r.journey_open_now) == 1 else None),
}

#: Chips that are shown even when the model happened not to dock the score for
#: them: the mentors named these four as the things an RM must be told.
ALWAYS_SHOW = ("journey_blank_field_ratio", "journey_refused_income",
               "journey_fee_balk", "journey_doc_refusal")


def negative_chips(row, contribs: dict[str, float], k: int = 4) -> list[dict]:
    """The "why this might not close" chips, with the score they cost.

    ``impact`` is the feature's SHAP contribution in log-odds at this row: a
    negative number the RM can see, not an adjective.
    """
    out: list[dict] = []
    for c, fn in NEGATIVE.items():
        v = contribs.get(c, 0.0)
        if v > 0 and c not in ALWAYS_SHOW:
            continue
        try:
            s = fn(row)
        except (AttributeError, TypeError, ValueError):
            s = None
        if s:
            out.append(dict(signal=c, text=s, impact=round(float(v), 4),
                            mentor_signal=c in ALWAYS_SHOW))
    out.sort(key=lambda d: (not d["mentor_signal"], d["impact"]))
    return out[:k]


# --------------------------------------------------------------------------- #
# call material — all six products, English and Hindi
# --------------------------------------------------------------------------- #

#: (opener, why_now, objection, answer).  ``{emi:,}`` is the customer's own
#: behavioural EMI headroom, not a product brochure number.
PITCH_EN = {
    "home": ("Namaste! I'm calling from your bank. I noticed you've been managing a growing rent commitment — many customers at that point find an EMI works out comparable to rent.",
             "Based on your account behaviour you'd be comfortable around ₹{emi:,}/month — would a quick eligibility check be useful? No paperwork at this stage.",
             "Would an EMI really match my rent?",
             "On your observed retained income, a ₹{emi:,} EMI stays within the comfort band we computed — and unlike rent, it builds your own asset."),
    "auto": ("Namaste! Quick one — your commuting spend has climbed noticeably these past months. A lot of customers at that point are weighing their own vehicle.",
             "With your track record you're pre-qualified for an auto loan; EMI near ₹{emi:,} fits your monthly headroom. Want me to hold a rate quote for you?",
             "I'm not sure I want the EMI burden.",
             "Your cab + fuel outflow is already near that EMI — this shifts the same money from expense to ownership."),
    "personal": ("Namaste! I handle personal banking for your branch. I noticed some months get tight before salary day — you're not alone, and there are cleaner ways to handle it.",
                 "We can consolidate outside EMIs into one at a lower rate, or set a small credit line ~₹{emi:,}/month equivalent. Shall I check your pre-approved amount?",
                 "Another loan sounds like more stress.",
                 "This replaces costlier debt you're already servicing — one EMI, lower rate, and your salary month breathes again."),
    "gold": ("Namaste! I'm calling from your branch. You started an application with us and didn't finish it — if what you needed was quick funds, a gold loan is the fastest route we have.",
             "Against household jewellery we can disburse the same day, and the EMI sits near ₹{emi:,}/month on your headroom. No income proof, no long file.",
             "I don't want to pledge my family's jewellery.",
             "It stays insured in the branch vault and comes back the day you close — most customers use it as a 6-to-12-month bridge, not a sale."),
    "education": ("Namaste! I look after education loans at your branch. Fee season is close and your account shows fee outflows building — worth a two-minute conversation.",
                  "An education loan covers tuition plus living costs, with repayment starting after the course; on your headroom the EMI lands near ₹{emi:,}/month. Shall I check eligibility?",
                  "We are managing the fees ourselves for now.",
                  "Most families do — until the second year. Sanctioning now costs nothing and stops you breaking a deposit later; interest is charged only on what you draw."),
    "lap": ("Namaste! I'm from your bank's secured-lending desk. You hold property and you'd started a loan enquiry with us — a loan against it is usually the cheapest money available to you.",
            "You keep the property and use it to borrow long-tenor at a secured rate; on your account behaviour ₹{emi:,}/month is comfortable. Would a valuation call help?",
            "I don't want to mortgage my house.",
            "It stays yours and you stay in it — the bank holds a lien, not the keys, and the rate is a third of what an unsecured loan of that size would cost."),
}

PITCH_HI = {
    "home": ("नमस्ते! मैं आपके बैंक से बात कर रहा हूँ। हमने देखा कि आपका किराया पिछले कुछ महीनों में बढ़ा है — ऐसे कई ग्राहकों को होम लोन की EMI किराए के बराबर ही बैठती है।",
             "आपके खाते के व्यवहार के अनुसार लगभग ₹{emi:,}/माह आपके लिए आरामदायक रहेगा — क्या मैं एक झटपट पात्रता जाँच कर दूँ? अभी कोई कागज़ी कार्यवाही नहीं।",
             "क्या सच में EMI मेरे किराए के बराबर बैठेगी?",
             "आपकी उपलब्ध आय के हिसाब से ₹{emi:,} की EMI आरामदायक दायरे में रहती है — और किराए के विपरीत, यह आपकी अपनी संपत्ति बनाती है।"),
    "auto": ("नमस्ते! एक छोटी सी बात — पिछले कुछ महीनों में आपका आने-जाने का खर्च काफ़ी बढ़ा है। ऐसे कई ग्राहक इस समय अपनी गाड़ी लेने पर विचार करते हैं।",
             "आपके रिकॉर्ड के अनुसार आप ऑटो लोन के लिए पूर्व-योग्य हैं; लगभग ₹{emi:,} की EMI आपकी मासिक क्षमता में बैठती है। क्या मैं आपके लिए एक दर-उद्धरण रोक रखूँ?",
             "मुझे यकीन नहीं कि मैं EMI का बोझ लेना चाहता हूँ।",
             "आपका कैब और ईंधन खर्च पहले से ही उस EMI के आसपास है — यह उसी पैसे को खर्च से मालिकाना हक़ में बदल देता है।"),
    "personal": ("नमस्ते! मैं आपकी शाखा की व्यक्तिगत बैंकिंग संभालता हूँ। हमने देखा कि वेतन से पहले कुछ महीने तंग हो जाते हैं — आप अकेले नहीं हैं, और इसे संभालने के बेहतर तरीके हैं।",
                 "हम आपके बाहरी EMIs को कम दर पर एक में समेट सकते हैं, या लगभग ₹{emi:,}/माह के बराबर एक छोटी क्रेडिट लाइन रख सकते हैं। क्या मैं आपकी पूर्व-स्वीकृत राशि जाँच दूँ?",
                 "एक और लोन तो और तनाव जैसा लगता है।",
                 "यह उस महँगे कर्ज़ की जगह लेता है जो आप पहले से चुका रहे हैं — एक EMI, कम दर, और आपका वेतन-माह राहत की साँस लेता है।"),
    "gold": ("नमस्ते! मैं आपकी शाखा से बोल रहा हूँ। आपने हमारे साथ एक आवेदन शुरू किया था पर पूरा नहीं किया — अगर ज़रूरत जल्दी पैसों की थी, तो गोल्ड लोन हमारा सबसे तेज़ रास्ता है।",
             "घर के गहनों पर हम उसी दिन राशि दे सकते हैं, और आपकी क्षमता के अनुसार EMI लगभग ₹{emi:,}/माह बैठेगी। न आय प्रमाण, न लंबी फ़ाइल।",
             "मैं परिवार के गहने गिरवी नहीं रखना चाहता।",
             "गहने शाखा की तिजोरी में बीमित रहते हैं और लोन बंद करते ही वापस मिल जाते हैं — ज़्यादातर ग्राहक इसे 6–12 महीने का पुल मानते हैं, बिक्री नहीं।"),
    "education": ("नमस्ते! मैं आपकी शाखा में शिक्षा ऋण देखता हूँ। फ़ीस का मौसम पास है और आपके खाते में फ़ीस के भुगतान बढ़ रहे हैं — दो मिनट की बात बनती है।",
                  "शिक्षा ऋण में ट्यूशन के साथ रहने का खर्च भी आता है, और चुकौती कोर्स पूरा होने के बाद शुरू होती है; आपकी क्षमता पर EMI लगभग ₹{emi:,}/माह रहेगी। क्या पात्रता जाँच लूँ?",
                  "अभी हम फ़ीस खुद संभाल रहे हैं।",
                  "ज़्यादातर परिवार यही करते हैं — दूसरे साल तक। अभी स्वीकृति लेने का कोई शुल्क नहीं और बाद में FD तुड़वाने की नौबत नहीं आती; ब्याज सिर्फ़ निकाली गई राशि पर लगता है।"),
    "lap": ("नमस्ते! मैं आपके बैंक के सुरक्षित-ऋण डेस्क से हूँ। आपके नाम संपत्ति है और आपने हमसे ऋण की पूछताछ शुरू की थी — संपत्ति पर ऋण आम तौर पर आपके लिए सबसे सस्ता पैसा होता है।",
            "संपत्ति आपकी ही रहती है और उसी पर लंबी अवधि का सुरक्षित दर वाला ऋण मिलता है; आपके खाते के व्यवहार पर ₹{emi:,}/माह आरामदायक है। क्या मूल्यांकन के लिए कॉल तय करूँ?",
            "मैं अपना घर गिरवी नहीं रखना चाहता।",
            "घर आपका ही रहता है और आप उसी में रहते हैं — बैंक के पास केवल भार (lien) होता है, चाबी नहीं; और दर उतनी ही राशि के असुरक्षित ऋण की एक-तिहाई होती है।"),
}

NBA = {
    "hot": "Call within 48h (Tue–Thu 11:00–13:00 windows convert best). Open with the observed change, not the product.",
    "warm": "WhatsApp opt-in nudge this week with a personalised calculator link; call on click-through.",
    "cold": "Keep in monthly digest; re-score after next salary cycle. Do not call — protect goodwill.",
}

#: Fallbacks when no fact fires — keyed by the strongest product-level contributor.
MENU_REASON_FALLBACK = {
    "emi_headroom_ratio": "their EMI headroom comfortably carries this ticket",
    "dwell_product_share": "most of their product browsing was here",
    "product_window_days": "closes inside a {days}-day window, so the lead stays fresh",
    "product": "next closest to the product they abandoned",
}


def menu_reason(row, product: str, contribs: dict[str, float],
                labels: dict[str, str], window_days: int) -> str:
    """Why this product sits in this slot — a fact first, a contribution second.

    Facts beat attributions here on purpose: "the application they abandoned" is
    something an RM can say on the phone, and "the model's third feature had a
    positive SHAP value" is not.
    """
    dwell = _num(getattr(row, f"dwell_{product}_3m", float("nan")))
    if str(getattr(row, "dropoff_product", "")) == product:
        return "the application they abandoned"
    if dwell > 5:
        return f"{int(dwell)} min on this product's pages in the last 90 days"
    if str(getattr(row, "journey_last_product", "")) == product:
        return "the product of their most recent application"
    if str(getattr(row, "last_campaign_product", "")) == product:
        return "the product we last pitched them"
    best, bestv = None, 0.0
    for c, v in contribs.items():
        if c in MENU_REASON_FALLBACK and v > bestv:
            best, bestv = c, v
    if best is None:
        drop = labels.get(str(getattr(row, "dropoff_product", "")), "the product they left")
        return f"customers who walk away from {drop.lower()} most often take this next"
    return MENU_REASON_FALLBACK[best].format(days=window_days)


#: Shown on the Model & Trust screen.  Unchanged in substance since the first
#: build; the last line is what SK-17 enforces and runner 07 grades.
EXCLUDED_FEATURES = [
    "Gender, religion, caste, marital status — excluded outright by policy.",
    "Pin-code / neighbourhood — an income proxy that quietly discriminates.",
    "Credit-bureau score — needs purpose-specific consent; pulled only at application stage, never for prospecting.",
    "Anyone the suppression rule holds back — no consent, DND, dormant, bereaved, called in the last 7 days, already applying — is scored but never queued.",
    "Anything timestamped after the moment the queue is picked up — including whether we actually called, and what happened next.",
]
