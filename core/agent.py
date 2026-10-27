class Agent:

    def __init__(
        self,
        llm,
        tool_registry,
        vault
    ):

        self.llm = llm
        self.tools = tool_registry
        self.vault = vault

    def ask(self, question):

        prompt = f"""
Sei un assistente locale.

Domanda:
{question}
"""

        return self.llm.generate(prompt)