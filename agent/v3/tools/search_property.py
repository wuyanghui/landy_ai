from dotenv import load_dotenv
import os
import numpy as np
from typing import Literal, List, Optional, Dict, Any
load_dotenv()
UPSTASH_VECTOR_REST_READONLY_TOKEN=os.getenv('UPSTASH_VECTOR_REST_READONLY_TOKEN')
UPSTASH_VECTOR_REST_TOKEN=os.getenv('UPSTASH_VECTOR_REST_TOKEN')
UPSTASH_VECTOR_REST_URL=os.getenv('UPSTASH_VECTOR_REST_URL')

from upstash_vector import Index

index = Index(
    url=UPSTASH_VECTOR_REST_URL,
    token=UPSTASH_VECTOR_REST_TOKEN
    )

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
    expanded = set()

    for cat in categories:
        if cat in FACTORY_EXPANSION_MAP:
            expanded.update(FACTORY_EXPANSION_MAP[cat])
        else:
            expanded.add(cat)

    return list(expanded)

from langchain_core.tools import tool
from typing import Literal, List, Optional, Dict, Any



@tool
def search_properties(
    query: str,
    offer_type: Optional[Literal['sale', 'rent']] = None,
    tenure: Optional[Literal['leasehold', 'freehold']] = None,
    property_category: Optional[List[Literal['agricultural-land', 'cluster-factory', 'detached-factory',
       'factory', 'industrial-land', 'semi-d-factory', 'shoplot',
       'showroom', 'terrace-factory', 'warehouse']]] = None,
    locality: Optional[List[Literal[
        'Balakong', 'Bandar Baru Bangi', 'Bangi', 'Banting', 'Beranang',
        'Cheras', 'Dengkil', 'Dengkil, Sepang', 'Hulu Langat', 'Klang',
        'Kuala Langat', 'Kuala Lumpur',
        'Lapangan Terbang Antarabangsa Kuala Lumpur', 'Nilai',
        'Olak Lempit', 'Petaling Jaya', 'Semenyih', 'Sepang', 'Seputeh',
        'Seremban', 'Seri Kembangan', 'Shah Alam', 'Shah Alam, Petaling',
        'Subang Jaya', 'Telok Panglima Garang',
        'Teluk Panglima Garang, Kuala Langat'
    ]]] = None,
    region: Optional[List[Literal['Selangor', 'Kuala Lumpur', 'Negeri Sembilan']]] = None,
    price_min: Optional[float] = None,
    price_max: Optional[float] = None,
    built_up_sqft_min: Optional[float] = None,
    built_up_sqft_max: Optional[float] = None,
    land_sqft_min: Optional[float] = None,
    land_sqft_max: Optional[float] = None,
    ceiling_height_min: Optional[float] = None,
    floor_loading_min: Optional[float] = None,
    pool_hint: str = "medium",
) -> Dict[str, Any]:
    """
    Search industrial property listings using Upstash Vector hybrid search.
    """
    print(property_category)
    print(query)
    print(region)
    print(locality)
    top_k = {"narrow": 30, "medium": 60, "broad": 100}.get(pool_hint, 60)

    clauses = []

    # ---- helpers ----
    def or_clause(field: str, values: List[str]):
        return "(" + " OR ".join([f'{field} = "{v}"' for v in values]) + ")"

    # ---- filters ----
    if offer_type:
        clauses.append(f'offer_type = "{offer_type}"')

    if tenure:
        clauses.append(f'tenure = "{tenure}"')

    if property_category:
        expanded_categories = expand_property_category(property_category)

        category_clause = "(" + " OR ".join(
            [f'main_category = "{v}" OR sub_categories = "{v}"' for v in expanded_categories]
        ) + ")"

        clauses.append(category_clause)

    if locality:
        # partial match OR exact match depending on your schema
        clauses.append("(" + " OR ".join(
            [f'locality GLOB "*{loc}*"' for loc in locality]
        ) + ")")

    if region:
        clauses.append(or_clause("region", region))

    if price_min is not None:
        clauses.append(f"price >= {price_min}")

    if price_max is not None:
        clauses.append(f"price <= {price_max}")

    if built_up_sqft_min is not None:
        clauses.append(f"built_up_sqft >= {built_up_sqft_min}")

    if built_up_sqft_max is not None:
        clauses.append(f"built_up_sqft <= {built_up_sqft_max}")

    if land_sqft_min is not None:
        clauses.append(f"land_sqft >= {land_sqft_min}")

    if land_sqft_max is not None:
        clauses.append(f"land_sqft <= {land_sqft_max}")

    if ceiling_height_min is not None:
        clauses.append(f"ceiling_height >= {ceiling_height_min}")

    if floor_loading_min is not None:
        clauses.append(f"floor_loading >= {floor_loading_min}")

    # always enforce active
    clauses.append('listing_status = "active"')

    filter_str = " AND ".join(clauses) if clauses else None

    # ---- query ----
    kwargs = dict(
        data=query,
        top_k=top_k,
        include_metadata=True
    )

    if filter_str:
        kwargs["filter"] = filter_str

    raw = index.query(**kwargs)

    # ---- dedupe ----
    seen: set[str] = set()
    results = []

    for r in raw:
        meta = r.metadata or {}
        pid = meta.get("property_id")

        # ---- enforce strict property_id ----
        if not pid:
            continue

        if pid in seen:
            continue

        seen.add(pid)

        results.append({
            "property_id": pid,
            "title": meta.get("title"),
            "slug": meta.get("slug"),
            "offer_type": meta.get("offer_type"),
            "price": meta.get("price"),
            "price_currency": meta.get("price_currency"),
            "locality": meta.get("locality"),
            "region": meta.get("region"),
            "full_address": meta.get("full_address"),
            "main_category": meta.get("main_category"),
            "sub_categories": meta.get("sub_categories"),
            "tenure": meta.get("tenure"),
            "land_sqft": meta.get("land_sqft"),
            "built_up_sqft": meta.get("built_up_sqft"),
            "ceiling_height": meta.get("ceiling_height"),
            "ceiling_height_unit": meta.get("ceiling_height_unit"),
            "floor_loading": meta.get("floor_loading"),
            "power_supply": meta.get("power_supply"),
            "occupancy_status": meta.get("occupancy_status"),
            "matched_text": (meta.get("parent_text") or ""),
            "score": r.score,
        })
    try:
        locality_list = np.unique([x['locality'] for x in results])
    except:
        locality_list = []
    try:
        region_list = np.unique([x['region'] for x in results])
    except:
        region_list = []
    try:
        category_list = np.unique([x['main_category'] for x in results])
    except:
        category_list = []
    try:
        property_listing_id = [x['property_id'] for x in results]
    except:
        property_listing_id = []    

    return {
        "total_found": len(results),
        "property_listing_id": property_listing_id,
        "property_listing_result": results,
        "comments": f"""Suggestion for breakdown by:
        -Locality: {locality_list}
        -Region: {region_list}
        -Property Category: {category_list}
        """
    }

from upstash_vector import AsyncIndex  # <--- Switch to AsyncIndex

# Initialize AsyncIndex outside the function for reuse
async_index = AsyncIndex(
    url=os.getenv('UPSTASH_VECTOR_REST_URL'),
    token=os.getenv('UPSTASH_VECTOR_REST_TOKEN')
)

@tool
async def asearch_properties( # <--- Change to async def
    query: str,
    offer_type: Optional[Literal['sale', 'rent']] = None,
    tenure: Optional[Literal['leasehold', 'freehold']] = None,
    property_category: Optional[List[Literal['agricultural-land', 'cluster-factory', 'detached-factory',
       'factory', 'industrial-land', 'semi-d-factory', 'shoplot',
       'showroom', 'terrace-factory', 'warehouse']]] = None,
    locality: Optional[List[Literal[
        'Balakong', 'Bandar Baru Bangi', 'Bangi', 'Banting', 'Beranang',
        'Cheras', 'Dengkil', 'Dengkil, Sepang', 'Hulu Langat', 'Klang',
        'Kuala Langat', 'Kuala Lumpur',
        'Lapangan Terbang Antarabangsa Kuala Lumpur', 'Nilai',
        'Olak Lempit', 'Petaling Jaya', 'Semenyih', 'Sepang', 'Seputeh',
        'Seremban', 'Seri Kembangan', 'Shah Alam', 'Shah Alam, Petaling',
        'Subang Jaya', 'Telok Panglima Garang',
        'Teluk Panglima Garang, Kuala Langat'
    ]]] = None,
    region: Optional[List[Literal['Selangor', 'Kuala Lumpur', 'Negeri Sembilan']]] = None,
    price_min: Optional[float] = None,
    price_max: Optional[float] = None,
    built_up_sqft_min: Optional[float] = None,
    built_up_sqft_max: Optional[float] = None,
    land_sqft_min: Optional[float] = None,
    land_sqft_max: Optional[float] = None,
    ceiling_height_min: Optional[float] = None,
    floor_loading_min: Optional[float] = None,
    pool_hint: str = "medium",
) -> Dict[str, Any]:
    """
    Search industrial property listings using Upstash Vector hybrid search.
    """
    top_k = {"narrow": 30, "medium": 60, "broad": 100}.get(pool_hint, 60)
    clauses = []

    def or_clause(field: str, values: List[str]):
        return "(" + " OR ".join([f'{field} = "{v}"' for v in values]) + ")"

    # Filter Logic (Stays the same as your sync version)
    if offer_type:
        clauses.append(f'offer_type = "{offer_type}"')
    if tenure:
        clauses.append(f'tenure = "{tenure}"')
    if property_category:
        expanded_categories = expand_property_category(property_category)
        category_clause = "(" + " OR ".join(
            [f'main_category = "{v}" OR sub_categories = "{v}"' for v in expanded_categories]
        ) + ")"
        clauses.append(category_clause)
    if locality:
        clauses.append("(" + " OR ".join([f'locality GLOB "*{loc}*"' for loc in locality]) + ")")
    if region:
        clauses.append(or_clause("region", region))
    if price_min is not None: clauses.append(f"price >= {price_min}")
    if price_max is not None: clauses.append(f"price <= {price_max}")
    if built_up_sqft_min is not None: clauses.append(f"built_up_sqft >= {built_up_sqft_min}")
    if built_up_sqft_max is not None: clauses.append(f"built_up_sqft <= {built_up_sqft_max}")
    if land_sqft_min is not None: clauses.append(f"land_sqft >= {land_sqft_min}")
    if land_sqft_max is not None: clauses.append(f"land_sqft <= {land_sqft_max}")
    if ceiling_height_min is not None: clauses.append(f"ceiling_height >= {ceiling_height_min}")
    if floor_loading_min is not None: clauses.append(f"floor_loading >= {floor_loading_min}")

    clauses.append('listing_status = "active"')
    filter_str = " AND ".join(clauses) if clauses else None

    # ---- ASYNC QUERY ----
    kwargs = dict(
        data=query,
        top_k=top_k,
        include_metadata=True
    )
    if filter_str:
        kwargs["filter"] = filter_str

    # Use await with the async index
    raw = await async_index.query(**kwargs) 

    # ---- Processing results (Stays sync since it's just data manipulation) ----
    seen: set[str] = set()
    results = []

    for r in raw:
        meta = r.metadata or {}
        pid = meta.get("property_id")
        if not pid or pid in seen:
            continue
        seen.add(pid)

        results.append({
            "property_id": pid,
            "title": meta.get("title"),
            "slug": meta.get("slug"),
            "offer_type": meta.get("offer_type"),
            "price": meta.get("price"),
            "locality": meta.get("locality"),
            "region": meta.get("region"),
            "main_category": meta.get("main_category"),
            "sub_categories": meta.get("sub_categories"),
            "tenure": meta.get("tenure"),
            "land_sqft": meta.get("land_sqft"),
            "built_up_sqft": meta.get("built_up_sqft"),
            "ceiling_height": meta.get("ceiling_height"),
            "floor_loading": meta.get("floor_loading"),
            "matched_text": (meta.get("parent_text") or ""),
            "score": r.score,
        })

    # Metadata lists for the summary
    def get_unique(key):
        try: return np.unique([x[key] for x in results]).tolist()
        except: return []

    return {
        "total_found": len(results),
        "property_listing_id": [x['property_id'] for x in results],
        "property_listing_result": results,
        "comments": f"""Suggestion for breakdown by:
        -Locality: {get_unique('locality')}
        -Region: {get_unique('region')}
        -Property Category: {get_unique('main_category')}
        """
    }