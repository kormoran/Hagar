class ToolRegistry:

    def __init__(self):
        self.tools = {}

    def register(self, name, tool):
        self.tools[name] = tool

    def execute(self, name, **kwargs):

        tool = self.tools.get(name)

        if tool is None:
            raise RuntimeError(
                f"unknown tool {name}"
            )

        return tool(**kwargs)
