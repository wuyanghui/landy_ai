import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _stats(psf, deals, *, band=None, recent=None, types=None, years=None, vs_parent=None, vs_national=None):
    stats = {
        "dealCount": deals,
        "medianPrice": 4_500_000,
        "medianPsf": psf,
        "period": {"from": "2021-01", "to": "2026-05"},
        "byType": types or [],
        "tenure": {"freeholdSharePct": 87, "freeholdDeals": 383, "leaseholdDeals": 55,
                   "freeholdMedianPsf": 753, "leaseholdMedianPsf": 559},
        "landPsf": {"medianPsf": 420, "dealCount": 438},
        "yearlyPsf": years or [],
        "vsParentPct": vs_parent,
        "vsNationalPct": vs_national,
    }
    if band:
        stats["p25Psf"], stats["p75Psf"] = band
    if recent is not None:
        stats["recent"] = recent
    return stats


@pytest.fixture
def shah_alam_page():
    """An industrial area page as GET /api/market/industrial/page?path=selangor/shah-alam returns it (rebuilt data)."""
    return {
        "class": "industrial",
        "level": "area",
        "path": "selangor/shah-alam",
        "name": "Shah Alam",
        "parentPath": "selangor",
        "breadcrumbs": [{"path": "", "name": "Malaysia"}, {"path": "selangor", "name": "Selangor"}],
        "districts": ["Gombak", "Klang", "Petaling"],
        "stats": _stats(
            731, 438, band=(523, 959), vs_parent=41, vs_national=80,
            recent={"medianPsf": 753, "dealCount": 89, "from": "2024-07", "to": "2026-06"},
            types=[
                {"type": "terrace", "label": "Terrace factory", "dealCount": 163, "medianPrice": 1_495_000,
                 "medianPsf": 536, "p25Psf": 379, "p75Psf": 709},
                {"type": "semi-d", "label": "Semi-D factory", "dealCount": 218, "medianPrice": 5_896_500,
                 "medianPsf": 918, "p25Psf": 688, "p75Psf": 1045},
            ],
            years=[
                {"year": 2025, "medianPsf": 718, "dealCount": 35, "provisional": False},
                {"year": 2026, "medianPsf": 823, "dealCount": 24, "provisional": True},
            ],
        ),
        "children": [
            {"path": "selangor/shah-alam/kota-elmina", "level": "scheme", "name": "Kota Elmina", "dealCount": 73,
             "medianPsf": 956, "medianPrice": 6_000_000, "vsNationalPct": 135, "yearlyPsf": []},
        ],
        "coordinates": [101.5378, 3.0736],
        "dataset": {
            "id": "2026-10-19T131055",
            "dataThrough": "2026-06",
            "generatedAt": "2026-10-19",
            "source": {"name": "NAPIC Open Sales Data", "url": "https://napic2.jpph.gov.my/"},
            "thresholds": {"page": 30, "area": 20, "smallArea": 10, "type": 10},
        },
    }


@pytest.fixture
def old_page(shah_alam_page):
    """The same page from a dataset built before the middle-half range and the recent figure existed."""
    page = {**shah_alam_page, "stats": {**shah_alam_page["stats"]}}
    for key in ("p25Psf", "p75Psf", "recent"):
        page["stats"].pop(key, None)
    page["stats"]["byType"] = [
        {k: v for k, v in row.items() if k not in ("p25Psf", "p75Psf")} for row in page["stats"]["byType"]
    ]
    page.pop("coordinates")
    return page


@pytest.fixture
def industrial_index():
    return {
        "class": "industrial",
        "datasetId": "2026-10-19T131055",
        "dataThrough": "2026-06",
        "generatedAt": "2026-10-19",
        "pages": [
            {"path": "", "level": "national", "name": "Malaysia", "dealCount": 11098, "medianPsf": 407},
            {"path": "selangor", "level": "state", "name": "Selangor", "dealCount": 5297, "medianPsf": 517},
            {"path": "johor", "level": "state", "name": "Johor", "dealCount": 1643, "medianPsf": 375},
            {"path": "selangor/shah-alam", "level": "area", "name": "Shah Alam", "dealCount": 438, "medianPsf": 731},
            {"path": "selangor/klang", "level": "area", "name": "Klang", "dealCount": 264, "medianPsf": 378},
            {"path": "selangor/puchong", "level": "area", "name": "Puchong", "dealCount": 407, "medianPsf": 654},
            {"path": "johor/senai", "level": "area", "name": "Senai", "dealCount": 111, "medianPsf": 291},
            {"path": "selangor/shah-alam/kota-elmina", "level": "scheme", "name": "Kota Elmina", "dealCount": 73,
             "medianPsf": 956},
        ],
    }


@pytest.fixture
def commercial_index():
    return {
        "class": "commercial",
        "datasetId": "2026-10-19T131055",
        "dataThrough": "2026-06",
        "generatedAt": "2026-10-19",
        "pages": [
            {"path": "", "level": "national", "name": "Malaysia", "dealCount": 44207, "medianPsf": 313},
            {"path": "selangor", "level": "state", "name": "Selangor", "dealCount": 14064, "medianPsf": 414},
            {"path": "selangor/shah-alam", "level": "area", "name": "Shah Alam", "dealCount": 895, "medianPsf": 504},
        ],
    }
