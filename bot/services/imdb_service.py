import re
from imdb import IMDb
from bot.config import settings

imdb = IMDb()


def list_to_str(data):
    if not data:
        return "N/A"
    if settings.MAX_LIST_ELM:
        data = data[:int(settings.MAX_LIST_ELM)]
    return ", ".join(map(str, data))


async def get_poster(query: str, *, bulk=False, imdb_id=False, file=None):
    if not imdb_id:
        query = query.lower().strip()
        year = re.findall(r"[1-2]\d{3}", query)
        title = query.replace(year[0], "").strip() if year else query

        results = imdb.search_movie(title, results=10)
        if not results:
            return None

        if year:
            results = [r for r in results if str(r.get("year")) == year[0]]

        movie = results[0]
        imdb_id = movie.movieID

    movie = imdb.get_movie(imdb_id)

    plot = movie.get("plot outline") if settings.LONG_IMDB_DESCRIPTION else (
        movie.get("plot")[0] if movie.get("plot") else "N/A"
    )

    return {
        "title": movie.get("title"),
        "year": movie.get("year"),
        "rating": movie.get("rating"),
        "genres": list_to_str(movie.get("genres")),
        "poster": movie.get("full-size cover url"),
        "plot": plot[:800] + "..." if plot and len(plot) > 800 else plot,
        "url": f"https://www.imdb.com/title/tt{imdb_id}",
    }