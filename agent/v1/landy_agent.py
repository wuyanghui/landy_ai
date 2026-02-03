from prompt.prompt import get_system_prompt
from langchain_core.prompts import ChatPromptTemplate
from schema.schema import Planner, OverallState
from langgraph.types import Command
from langgraph.graph import END
from utility.llm_init import load_llm

def Landy_Planner(state: OverallState):
    user_input = state['user_input']

    system_prompt = get_system_prompt()

    template = ChatPromptTemplate(
        [
            ("system", system_prompt),
            ("human", "{user_input}"),
        ]
    )

    chain = template | load_llm().with_structured_output(Planner)

    response = chain.invoke({
        "user_input": user_input
    })

    if response['planner_decision'] == 'final_output':
        goto = END
    else:
        goto = "Property_Lookup_Agent"
    
    return Command(
        update = {
        'graph_output': response['messages'],
        'preferences': response['preferences']
        },
        goto = goto
    )