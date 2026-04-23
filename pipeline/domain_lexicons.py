from __future__ import annotations

from pipeline.domain_types import KinshipDetail, RoleKind

PUBLIC_OFFICE_ROLE_KINDS = frozenset(
    {
        RoleKind.RADNY,
        RoleKind.POSEL,
        RoleKind.SENATOR,
        RoleKind.MINISTER,
        RoleKind.PREZYDENT_MIASTA,
        RoleKind.WOJEWODA,
        RoleKind.WOJT,
        RoleKind.STAROSTA,
        RoleKind.SEKRETARZ_POWIATU,
        RoleKind.MARSZALEK_WOJEWODZTWA,
    }
)

PUBLIC_EMPLOYER_TERMS = frozenset(
    {
        "urząd",
        "samorząd",
        "gmina",
        "gminy",
        "powiat",
        "powiatowe",
        "starostwo",
        "wojewódzki",
        "województwo",
        "marszałkowski",
        "centrum pomocy rodzinie",
        "zarząd dróg",
        "urząd pracy",
        "urząd stanu cywilnego",
    }
)

INVALID_PUBLIC_EMPLOYMENT_ROLE_HEADS = frozenset(
    {
        "decyzja",
        "potrzebny",
        "stary",
        "suwerenny",
        "zatrudnić",
        "wójt",
        "wojt",
        "starosta",
        "sekretarz",
        "marszałek",
        "wojewoda",
    }
)

KINSHIP_BY_LEMMA: dict[str, KinshipDetail] = {
    "żona": KinshipDetail.SPOUSE,
    "małżonka": KinshipDetail.SPOUSE,
    "mąż": KinshipDetail.SPOUSE,
    "małżonek": KinshipDetail.SPOUSE,
    "partnerka": KinshipDetail.PARTNER,
    "partner": KinshipDetail.PARTNER,
    "dziewczyna": KinshipDetail.PARTNER,
    "siostra": KinshipDetail.SIBLING_SISTER,
    "brat": KinshipDetail.SIBLING_BROTHER,
    "córka": KinshipDetail.CHILD_DAUGHTER,
    "syn": KinshipDetail.CHILD_SON,
    "kuzyn": KinshipDetail.COUSIN,
    "kuzynka": KinshipDetail.COUSIN,
    "teść": KinshipDetail.FATHER_IN_LAW,
    "tesc": KinshipDetail.FATHER_IN_LAW,
    "szwagier": KinshipDetail.BROTHER_IN_LAW,
    "szwagierka": KinshipDetail.SISTER_IN_LAW,
    "bratowa": KinshipDetail.SISTER_IN_LAW,
    "bratowy": KinshipDetail.SISTER_IN_LAW,
    "synowa": KinshipDetail.DAUGHTER_IN_LAW,
}

KINSHIP_LEMMAS = frozenset({*KINSHIP_BY_LEMMA, "narzeczona", "narzeczony"})

PUBLIC_SUBJECT_ROLE_LEMMAS = frozenset(
    {
        "wójt",
        "wojt",
        "burmistrz",
        "prezydent",
        "starosta",
        "marszałek",
        "wojewoda",
        "minister",
        "poseł",
        "radny",
    }
)

REFERRAL_TRIGGER_LEMMAS = frozenset({"złożyć", "skierować", "zapowiedzieć"})
REFERRAL_NOUN_LEMMAS = frozenset({"zawiadomienie", "doniesienie", "skarga", "wniosek"})
INVESTIGATION_TRIGGER_LEMMAS = frozenset(
    {
        "zatrzymać",
        "postawić",
        "zarzucić",
        "oskarżyć",
        "podejrzewać",
        "prowadzić",
        "wszcząć",
        "badać",
        "przyjąć",
        "brać",
        "ustawiać",
        "zlecać",
    }
)
INVESTIGATION_NOUN_LEMMAS = frozenset(
    {
        "zarzut",
        "łapówka",
        "korupcja",
        "zatrzymanie",
        "śledztwo",
        "dochodzenie",
        "postępowanie",
    }
)
PROCUREMENT_ABUSE_LEMMAS = frozenset(
    {
        "zamówienie",
        "przetarg",
        "zlecenie",
        "remont",
        "ustawiać",
        "zlecać",
    }
)
ACCOUNTABILITY_INSTITUTION_MARKERS = frozenset(
    {
        "cba",
        "centralne biuro antykorupcyjne",
        "prokuratura",
        "prokuratury",
        "nik",
        "najwyższa izba kontroli",
    }
)
