import os

from dotenv import load_dotenv
load_dotenv()

from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

_API_KEY = os.environ.get("GROQ_API_KEY", "")
_MODEL   = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")


def call_llm(system_prompt: str, human_template: str, variables: dict) -> dict | list:
    if not _API_KEY:
        raise RuntimeError("GROQ_API_KEY not set")
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", human_template),
    ])
    llm   = ChatGroq(api_key=_API_KEY, model=_MODEL, temperature=0)
    chain = prompt | llm | JsonOutputParser()
    return chain.invoke(variables)
