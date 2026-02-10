from fastmcp import FastMCP
from src.tools.search_tool import query_stcced
import asyncio

mcp = FastMCP("STCCED_Auditor_Server")

@mcp.tool()
def search_trade_classification(query: str) -> str:
    return query_stcced(query)

@mcp.prompt()
def get_decomposition_strategy(prompt_name: str) -> str:
    path = f"prompts/{prompt_name}.md"
    if not os.path.exists(path):
        return f"Strategy '{prompt_name}' not found. Please use a valid prompt name."
    
    with open(path, "r") as f:
        return f.read()

if __name__ == "__main__":
    mcp.run()