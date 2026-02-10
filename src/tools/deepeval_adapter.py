import os
from deepeval.models.base_model import DeepEvalBaseLLM
from langchain_groq import ChatGroq

class GroqDeepEvalLLM(DeepEvalBaseLLM):
    def __init__(self, model_name=None):
        RUN_MODE = os.getenv("RUN_MODE", "cloud")
        if RUN_MODE == "local":
            self.model_name = model_name or os.getenv("LOCAL_GROQ_MODEL")
            from langchain_ollama import ChatOllama
            self.llm = ChatOllama(model=self.model_name, base_url=os.getenv("OLLAMA_BASE_URL"), format="json")
        else:
            self.model_name = model_name or os.getenv("CLOUD_GROQ_MODEL")
            self.llm = ChatGroq(model=self.model_name)

    def load_model(self):
        return self.llm

    def generate(self, prompt: str) -> str:
        return self.llm.invoke(prompt).content

    async def a_generate(self, prompt: str) -> str:
        res = await self.llm.ainvoke(prompt)
        return res.content

    def get_model_name(self):
        return self.model_name