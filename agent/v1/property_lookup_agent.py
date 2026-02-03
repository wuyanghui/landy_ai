from prompt.prompt import get_property_search_prompt
from langchain_core.prompts import ChatPromptTemplate
from schema.schema import FinalOutput, OverallState
from langgraph.types import Command
from langgraph.graph import END
from utility.llm_init import llm
from utility.property_listing_init import get_property_listing

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
        "listing": get_property_listing(),
        "user_preferences": state['preferences'],
    })

    
    return Command(
        update = {
            'graph_output': response['messages'],
            'recommended_listing': response['recommended_listing']
            },
        goto = END
    )