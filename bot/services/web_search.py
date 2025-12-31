import httpx
from bs4 import BeautifulSoup


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120 Safari/537.36"
    )
}


async def search_gagala(query: str) -> list[str]:
    query = query.replace(" ", "+")
    url = f"https://www.google.com/search?q={query}"

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(url, headers=HEADERS)
        response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    return [h3.get_text() for h3 in soup.find_all("h3")]