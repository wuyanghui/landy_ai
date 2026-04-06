import os
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
import os
from openai import OpenAI
load_dotenv()
client = OpenAI()
openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()

def load_llm(model = "openai/gpt-5.4-mini", **kwargs):
    base_params = {
        "model": model,
        "api_key": os.getenv("AI_GATEWAY_API_KEY"),
        "base_url": "https://ai-gateway.vercel.sh/v1",
        **kwargs  # caller controls all extra params
    }
    return ChatOpenAI(**base_params)

async def aload_llm(model = "openai/gpt-5.4-mini", **kwargs):
    base_params = {
        "model": model,
        "api_key": os.getenv("AI_GATEWAY_API_KEY"),
        "base_url": "https://ai-gateway.vercel.sh/v1",
        **kwargs  # caller controls all extra params
    }
    return ChatOpenAI(**base_params)

def get_embedding(text, model="text-embedding-3-small"):
    text = text.replace("\n", " ")
    return client.embeddings.create(input = [text], model=model).data[0].embedding