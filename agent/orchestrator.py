from schema.schema import OverallState
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from agent.landy_agent import Landy_Planner
from agent.property_lookup_agent import Property_Lookup_Agent

builder = StateGraph(OverallState)
builder.add_node("Landy_Planner", Landy_Planner)
builder.add_node("Property_Lookup_Agent", Property_Lookup_Agent)

builder.add_edge(START, "Landy_Planner")
builder.add_edge("Property_Lookup_Agent", END)

memory = MemorySaver()
graph = builder.compile(checkpointer=memory)
