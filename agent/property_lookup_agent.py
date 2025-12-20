from prompt.prompt import get_property_search_prompt
from langchain_core.prompts import ChatPromptTemplate
from schema.schema import FinalOutput, OverallState
from langgraph.types import Command
from langgraph.graph import END
from utility.llm_init import llm
import json

# Open the file in read mode ('r')
with open('listing.json', 'r') as file:
    # Use json.load() to convert the file content to a Python dictionary
    listing = json.load(file)

def Property_Lookup_Agent(state: OverallState):
    property_search_prompt = get_property_search_prompt()

    template = ChatPromptTemplate(
        [
            ("system", property_search_prompt),
            ("human", "{user_preferences}"),
        ]
    )

    chain = template | llm.with_structured_output(FinalOutput)
    response = chain.invoke({
        "listing": listing,
        "user_preferences": state['preferences'],
    })

    
    return Command(
        update = {
            'graph_output': response['messages'],
            'recommended_listing': response['recommended_listing']
            },
        goto = END
    )