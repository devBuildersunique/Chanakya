"""Deterministic, synthetic mention-level gold data for UIE relationship evaluation.

Each gold edge is (predicate, subject mention, object mention). A mention uses
"surface#occurrence", with zero-based occurrence in the exact input text.
An empty gold list explicitly means NO RELATION.
"""

SCHEMA = {"Person": ["met", "contacted", "visited", "lives in", "used phone number"]}
PREDICATES = {
    "met": "met",
    "contacted": "contacted",
    "visited": "visited",
    "lives in": "lives_in",
    "used phone number": "used_phone",
}

CASES = [
    ("01", "Rahul Kumar met Ahmed.", [("met", "Rahul Kumar#0", "Ahmed#0")]),
    ("02", "Ahmed met Rahul Kumar.", [("met", "Ahmed#0", "Rahul Kumar#0")]),
    ("03", "Rahul Kumar contacted Ahmed.", [("contacted", "Rahul Kumar#0", "Ahmed#0")]),
    ("04", "Ahmed contacted Rahul Kumar.", [("contacted", "Ahmed#0", "Rahul Kumar#0")]),
    ("05", "Rahul Kumar met Ahmed and Bilal.", [("met", "Rahul Kumar#0", "Ahmed#0"), ("met", "Rahul Kumar#0", "Bilal#0")]),
    ("06", "Rahul Kumar met Ahmed; Bilal contacted Sara.", [("met", "Rahul Kumar#0", "Ahmed#0"), ("contacted", "Bilal#0", "Sara#0")]),
    ("07", "Rahul Kumar met Ahmed. Rahul Kumar contacted Sara.", [("met", "Rahul Kumar#0", "Ahmed#0"), ("contacted", "Rahul Kumar#1", "Sara#0")]),
    ("08", "Rahul Kumar met Ahmed. Ahmed contacted Rahul Kumar.", [("met", "Rahul Kumar#0", "Ahmed#0"), ("contacted", "Ahmed#1", "Rahul Kumar#1")]),
    ("09", "Rahul Kumar did not meet Ahmed.", []),
    ("10", "Rahul Kumar never contacted Ahmed.", []),
    ("11", "Rahul Kumar denied meeting Ahmed.", []),
    ("12", "Rahul Kumar and Ahmed appear in the same report.", []),
    ("13", "Rahul Kumar lives in Kozhikode.", [("lives_in", "Rahul Kumar#0", "Kozhikode#0")]),
    ("14", "Rahul Kumar visited Malappuram.", [("visited", "Rahul Kumar#0", "Malappuram#0")]),
    ("15", "Ahmed visited Kozhikode; Rahul Kumar visited Malappuram.", [("visited", "Ahmed#0", "Kozhikode#0"), ("visited", "Rahul Kumar#0", "Malappuram#0")]),
    ("16", "Rahul Kumar did not visit Malappuram.", []),
    ("17", "Rahul Kumar used phone number 9876543210.", [("used_phone", "Rahul Kumar#0", "9876543210#0")]),
    ("18", "Ahmed used phone number 9876543210; Rahul Kumar used phone number 9123456780.", [("used_phone", "Ahmed#0", "9876543210#0"), ("used_phone", "Rahul Kumar#0", "9123456780#0")]),
    ("19", "Rahul Kumar did not use phone number 9876543210.", []),
    ("20", "Rahul Kumar called Ahmed from phone number 9876543210.", [("contacted", "Rahul Kumar#0", "Ahmed#0"), ("used_phone", "Rahul Kumar#0", "9876543210#0")]),
    ("21", "Rahul Kumar met Ahmed. Sara was in Malappuram.", [("met", "Rahul Kumar#0", "Ahmed#0")]),
    ("22", "Rahul Kumar was in Kozhikode. Ahmed visited Malappuram.", [("visited", "Ahmed#0", "Malappuram#0")]),
    ("23", "Rahul Kumar told Sara that Ahmed met Bilal.", [("met", "Ahmed#0", "Bilal#0")]),
    ("24", "Rahul Kumar said Ahmed contacted Sara.", [("contacted", "Ahmed#0", "Sara#0")]),
    ("25", "Rahul Kumar met Ahmed near Bilal.", [("met", "Rahul Kumar#0", "Ahmed#0")]),
    ("26", "Rahul Kumar contacted Ahmed, not Bilal.", [("contacted", "Rahul Kumar#0", "Ahmed#0")]),
    ("27", "Rahul Kumar asked whether Bilal met Sara.", []),
    ("28", "Rahul Kumar may have contacted Ahmed.", []),
]
