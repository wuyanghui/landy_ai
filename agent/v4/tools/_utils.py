from typing import List

FACTORY_EXPANSION_MAP = {
    "factory": [
        "factory",
        "cluster-factory",
        "detached-factory",
        "semi-d-factory",
        "terrace-factory",
    ]
}


def expand_property_category(categories: List[str]) -> List[str]:
    expanded: set = set()
    for cat in categories:
        if cat in FACTORY_EXPANSION_MAP:
            expanded.update(FACTORY_EXPANSION_MAP[cat])
        else:
            expanded.add(cat)
    return list(expanded)
