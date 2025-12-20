from typing_extensions import TypedDict, Literal, Dict, Optional, List

class OverallState(TypedDict):
    user_input: str
    preferences: Optional[Dict[str, str]]
    recommended_listing: Optional[List["Listing"]]
    graph_output: str

class Preference(TypedDict):
    buy_rent: Optional[Literal['Buy', 'Rent']]
    location: Optional[str]
    size: Optional[str]
    business_nature: Optional[str]
    power_requirement: Optional[str]
    floor_loading_capacity: Optional[str]
    ceiling_height: Optional[str]
    budget: Optional[str]

class Planner(TypedDict):
    planner_decision: Literal['final_output', 'property_listing_lookup']
    rephrased_query: str
    preferences: Preference
    messages: str

class Listing(TypedDict):
    location: Optional[str]
    built_up_area_sqft: Optional[str]
    land_area_sqft: Optional[str]
    zoning_type: Optional[str]
    power_capacity_kva: Optional[str]
    floor_loading_ton_per_sqm: Optional[str]
    clear_height_m: Optional[str]
    asking_price: Optional[str]
    source: Optional[str]
    
class FinalOutput(TypedDict):
    recommended_listing: Optional[List[Listing]]
    messages: str