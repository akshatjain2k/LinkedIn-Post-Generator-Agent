import os
from langchain_community.utilities import SerpAPIWrapper
from langchain.tools import tool


@tool
def search_google(query: str) -> str:
    """Search Google for current, real-time information about a topic.
    Use this to find recent news, statistics, trends, and expert insights.
    Run 2-3 different searches to gather comprehensive information.
    """
    api_key = os.getenv("SERPAPI_API_KEY")
    if not api_key:
        raise RuntimeError("SERPAPI_API_KEY is not set. Add it to your .env file.")
    try:
        search = SerpAPIWrapper(serpapi_api_key=api_key)
        return search.run(query)
    except Exception as exc:
        error_str = str(exc).lower()
        if "invalid api key" in error_str or "authentication" in error_str:
            raise RuntimeError(
                "SerpAPI key is invalid. Check SERPAPI_API_KEY in .env."
            ) from exc
        if "quota" in error_str or "limit" in error_str:
            raise RuntimeError(
                "SerpAPI quota exceeded. Check your plan at serpapi.com."
            ) from exc
        raise RuntimeError(f"Google search failed: {exc}") from exc
