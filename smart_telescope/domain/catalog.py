"""Messier deep-sky catalog — lookup by designation or common name."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CatalogObject:
    name: str          # primary designation, e.g. "M42"
    common_name: str   # well-known name, e.g. "Orion Nebula" (may be empty)
    ra_hours: float    # J2000 right ascension in decimal hours
    dec_deg: float     # J2000 declination in decimal degrees
    object_type: str   # EN/RN/PN/SNR/GC/OC/SG/EG/DS/AST/MSC
    magnitude: float   # visual magnitude


# fmt: off
# Full Messier catalog — J2000 coordinates, RA in decimal hours, Dec in degrees.
_CATALOG: list[CatalogObject] = [
    CatalogObject("M1",   "Crab Nebula",         5.5753,  +22.0147, "SNR",  8.4),
    CatalogObject("M2",   "",                   21.5583,   -0.8231, "GC",   6.5),
    CatalogObject("M3",   "",                   13.7028,  +28.3756, "GC",   6.2),
    CatalogObject("M4",   "",                   16.3936,  -26.5256, "GC",   5.6),
    CatalogObject("M5",   "",                   15.3089,   +2.0811, "GC",   5.7),
    CatalogObject("M6",   "Butterfly Cluster",  17.6689,  -32.2131, "OC",   4.2),
    CatalogObject("M7",   "Ptolemy Cluster",    17.8989,  -34.8117, "OC",   3.3),
    CatalogObject("M8",   "Lagoon Nebula",      18.0625,  -24.3839, "EN",   5.8),
    CatalogObject("M9",   "",                   17.3203,  -18.5153, "GC",   7.7),
    CatalogObject("M10",  "",                   16.9522,   -4.0997, "GC",   6.6),
    CatalogObject("M11",  "Wild Duck Cluster",  18.8511,   -6.2711, "OC",   5.8),
    CatalogObject("M12",  "",                   16.7878,   -1.9489, "GC",   6.7),
    CatalogObject("M13",  "Hercules Cluster",   16.6949,  +36.4619, "GC",   5.8),
    CatalogObject("M14",  "",                   17.6253,   -3.2458, "GC",   7.6),
    CatalogObject("M15",  "",                   21.4997,  +12.1669, "GC",   6.2),
    CatalogObject("M16",  "Eagle Nebula",       18.3125,  -13.7864, "EN",   6.4),
    CatalogObject("M17",  "Omega Nebula",       18.3456,  -16.1811, "EN",   6.0),
    CatalogObject("M18",  "",                   18.3328,  -17.1467, "OC",   7.5),
    CatalogObject("M19",  "",                   17.0442,  -26.2681, "GC",   6.8),
    CatalogObject("M20",  "Trifid Nebula",      18.0436,  -23.0189, "EN",   8.5),
    CatalogObject("M21",  "",                   18.0736,  -22.5008, "OC",   5.9),
    CatalogObject("M22",  "",                   18.6042,  -23.9044, "GC",   5.1),
    CatalogObject("M23",  "",                   17.9517,  -19.0125, "OC",   5.5),
    CatalogObject("M24",  "Sagittarius Star Cloud", 18.2828, -18.5517, "MSC", 4.6),
    CatalogObject("M25",  "",                   18.5267,  -19.2369, "OC",   4.6),
    CatalogObject("M26",  "",                   18.7561,   -9.3956, "OC",   8.0),
    CatalogObject("M27",  "Dumbbell Nebula",    19.9939,  +22.7206, "PN",   7.5),
    CatalogObject("M28",  "",                   18.4086,  -24.8697, "GC",   6.8),
    CatalogObject("M29",  "",                   20.3978,  +38.5092, "OC",   7.1),
    CatalogObject("M30",  "",                   21.6728,  -23.1806, "GC",   7.2),
    CatalogObject("M31",  "Andromeda Galaxy",    0.7122,  +41.2692, "SG",   3.4),
    CatalogObject("M32",  "",                    0.7117,  +40.8653, "EG",   8.7),
    CatalogObject("M33",  "Triangulum Galaxy",   1.5644,  +30.6600, "SG",   5.7),
    CatalogObject("M34",  "",                    2.7033,  +42.7250, "OC",   5.2),
    CatalogObject("M35",  "",                    6.1506,  +24.3392, "OC",   5.1),
    CatalogObject("M36",  "",                    5.6044,  +34.1350, "OC",   6.0),
    CatalogObject("M37",  "",                    5.8736,  +32.5508, "OC",   5.6),
    CatalogObject("M38",  "",                    5.4772,  +35.8475, "OC",   6.4),
    CatalogObject("M39",  "",                   21.5269,  +48.4242, "OC",   4.6),
    CatalogObject("M40",  "Winnecke 4",         12.3728,  +58.0850, "DS",   9.0),
    CatalogObject("M41",  "",                    6.7686,  -20.7442, "OC",   4.5),
    CatalogObject("M42",  "Orion Nebula",        5.5883,   -5.3911, "EN",   4.0),
    CatalogObject("M43",  "De Mairan's Nebula",  5.5906,   -5.2681, "EN",   9.0),
    CatalogObject("M44",  "Beehive Cluster",     8.6714,  +19.9806, "OC",   3.7),
    CatalogObject("M45",  "Pleiades",            3.7900,  +24.1167, "OC",   1.6),
    CatalogObject("M46",  "",                    7.6972,  -14.8119, "OC",   6.1),
    CatalogObject("M47",  "",                    7.6114,  -14.4894, "OC",   4.4),
    CatalogObject("M48",  "",                    8.2275,   -5.7275, "OC",   5.8),
    CatalogObject("M49",  "",                   12.4958,   +8.0003, "EG",   8.4),
    CatalogObject("M50",  "",                    7.0419,   -8.3667, "OC",   5.9),
    CatalogObject("M51",  "Whirlpool Galaxy",   13.4978,  +47.1947, "SG",   8.4),
    CatalogObject("M52",  "",                   23.4044,  +61.5917, "OC",   6.9),
    CatalogObject("M53",  "",                   13.2156,  +18.1683, "GC",   7.6),
    CatalogObject("M54",  "",                   18.9178,  -30.4797, "GC",   7.7),
    CatalogObject("M55",  "",                   19.6672,  -30.9614, "GC",   6.3),
    CatalogObject("M56",  "",                   19.2764,  +30.1850, "GC",   8.3),
    CatalogObject("M57",  "Ring Nebula",        18.8939,  +33.0289, "PN",   8.8),
    CatalogObject("M58",  "",                   12.6289,  +11.8181, "SG",   9.7),
    CatalogObject("M59",  "",                   12.7003,  +11.6470, "EG",   9.6),
    CatalogObject("M60",  "",                   12.7275,  +11.5528, "EG",   8.8),
    CatalogObject("M61",  "",                   12.3650,   +4.4742, "SG",   9.7),
    CatalogObject("M62",  "",                   17.0217,  -30.1139, "GC",   6.6),
    CatalogObject("M63",  "Sunflower Galaxy",   13.2636,  +42.0297, "SG",   8.6),
    CatalogObject("M64",  "Black Eye Galaxy",   12.9467,  +21.6808, "SG",   8.5),
    CatalogObject("M65",  "",                   11.3153,  +13.0914, "SG",   9.3),
    CatalogObject("M66",  "",                   11.3369,  +12.9914, "SG",   9.0),
    CatalogObject("M67",  "",                    8.8561,  +11.8142, "OC",   6.9),
    CatalogObject("M68",  "",                   12.6586,  -26.7444, "GC",   7.8),
    CatalogObject("M69",  "",                   18.5239,  -32.3481, "GC",   7.7),
    CatalogObject("M70",  "",                   18.7214,  -32.2897, "GC",   7.9),
    CatalogObject("M71",  "",                   19.8964,  +18.7783, "GC",   6.1),
    CatalogObject("M72",  "",                   20.8914,  -12.5369, "GC",   9.3),
    CatalogObject("M73",  "",                   20.9792,  -12.6308, "AST",  9.0),
    CatalogObject("M74",  "Phantom Galaxy",      1.6108,  +15.7836, "SG",   9.4),
    CatalogObject("M75",  "",                   20.1011,  -21.9219, "GC",   8.6),
    CatalogObject("M76",  "Little Dumbbell",     1.7028,  +51.5753, "PN",  10.1),
    CatalogObject("M77",  "Cetus A",             2.7119,   -0.0133, "SG",   8.9),
    CatalogObject("M78",  "",                    5.7794,   +0.0567, "EN",   8.3),
    CatalogObject("M79",  "",                    5.4039,  -24.5239, "GC",   7.7),
    CatalogObject("M80",  "",                   16.2836,  -22.9756, "GC",   7.3),
    CatalogObject("M81",  "Bode's Galaxy",       9.9256,  +69.0653, "SG",   6.9),
    CatalogObject("M82",  "Cigar Galaxy",        9.9258,  +69.6789, "SG",   8.4),
    CatalogObject("M83",  "Southern Pinwheel",  13.6169,  -29.8658, "SG",   7.6),
    CatalogObject("M84",  "",                   12.4183,  +12.8872, "EG",   9.1),
    CatalogObject("M85",  "",                   12.4231,  +18.1908, "EG",   9.2),
    CatalogObject("M86",  "",                   12.4364,  +12.9456, "EG",   8.9),
    CatalogObject("M87",  "Virgo A",            12.5136,  +12.3911, "EG",   8.6),
    CatalogObject("M88",  "",                   12.5325,  +14.4214, "SG",   9.6),
    CatalogObject("M89",  "",                   12.5944,  +12.5564, "EG",   9.8),
    CatalogObject("M90",  "",                   12.6133,  +13.1631, "SG",   9.5),
    CatalogObject("M91",  "",                   12.5914,  +14.4964, "SG",  10.2),
    CatalogObject("M92",  "",                   17.2853,  +43.1361, "GC",   6.4),
    CatalogObject("M93",  "",                    7.7444,  -23.8594, "OC",   6.2),
    CatalogObject("M94",  "",                   12.8481,  +41.1197, "SG",   8.2),
    CatalogObject("M95",  "",                   10.7278,  +11.7033, "SG",   9.7),
    CatalogObject("M96",  "",                   10.7797,  +11.8194, "SG",   9.2),
    CatalogObject("M97",  "Owl Nebula",         11.2464,  +55.0186, "PN",   9.9),
    CatalogObject("M98",  "",                   12.2314,  +14.9003, "SG",  10.1),
    CatalogObject("M99",  "",                   12.3133,  +14.4169, "SG",   9.9),
    CatalogObject("M100", "",                   12.3819,  +15.8222, "SG",   9.3),
    CatalogObject("M101", "Pinwheel Galaxy",    14.0542,  +54.3489, "SG",   7.9),
    CatalogObject("M102", "Spindle Galaxy",     15.1133,  +55.7644, "SG",  10.0),
    CatalogObject("M103", "",                    1.5558,  +60.6597, "OC",   7.4),
    CatalogObject("M104", "Sombrero Galaxy",    12.6669,  -11.6231, "SG",   8.0),
    CatalogObject("M105", "",                   10.7983,  +12.5822, "EG",   9.3),
    CatalogObject("M106", "",                   12.3161,  +47.3039, "SG",   8.4),
    CatalogObject("M107", "",                   16.5419,  -13.0533, "GC",   7.9),
    CatalogObject("M108", "",                   11.1894,  +55.6739, "SG",  10.0),
    CatalogObject("M109", "",                   11.9594,  +53.3747, "SG",   9.8),
    CatalogObject("M110", "",                    0.6750,  +41.6856, "EG",   8.5),
]
# fmt: on

# Build index for fast lookup
_BY_NAME: dict[str, CatalogObject] = {obj.name.upper(): obj for obj in _CATALOG}


def search(query: str, limit: int = 10) -> list[CatalogObject]:
    """Return up to *limit* catalog objects matching *query*.

    Matches by designation prefix (e.g. "m4" → M4, M42, M43…) and
    substring in common name (case-insensitive). Designation matches
    are ranked before common-name matches.
    """
    q = query.strip().upper().replace(" ", "")
    if not q:
        return []

    exact: list[CatalogObject] = []
    desig_prefix: list[CatalogObject] = []
    name_sub: list[CatalogObject] = []

    q_lower = q.lower()

    for obj in _CATALOG:
        if obj.name.upper() == q:
            exact.append(obj)
        elif obj.name.upper().startswith(q):
            desig_prefix.append(obj)
        elif q_lower in obj.common_name.lower():
            name_sub.append(obj)

    results = exact + desig_prefix + name_sub
    return results[:limit]


def get_all() -> list[CatalogObject]:
    return list(_CATALOG)


def get_by_name(name: str) -> CatalogObject | None:
    return _BY_NAME.get(name.strip().upper().replace(" ", ""))
