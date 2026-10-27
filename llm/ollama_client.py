import requests

class OllamaClient:

    def __init__(self, host, model):
        self.host = host
        self.model = model

    def generate(self, prompt):

        response = requests.post(
            f"{self.host}/api/generate",
            json={
                "model": self.model,
                "prompt": prompt,
                "stream": False
            }
        )

        return response.json()["response"]