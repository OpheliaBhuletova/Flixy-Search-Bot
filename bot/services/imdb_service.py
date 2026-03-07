import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from imdb import IMDb

from bot.config import settings

imdb = IMDb()

GENRE_EMOJI = {
    "Action": "🔫",
    "Adventure": "🌋",
    "Animation": "🐭",
    "Biography": "👤",
    "Comedy": "😂",
    "Crime": "🕵️",
    "Documentary": "🎥",
    "Drama": "🎭",
    "Family": "👨‍👩‍👧‍👦",
    "Fantasy": "🧙",
    "History": "📜",
    "Horror": "👻",
    "Music": "🎵",
    "Musical": "🎶",
    "Mystery": "🕵️‍♂️",
    "Romance": "💕",
    "Sci-Fi": "🚀",
    "Sport": "🏆",
    "Thriller": "😱",
    "War": "⚔️",
    "Western": "🤠",
}

COUNTRY_FLAGS = {
    "United States": "🇺🇸",
    "USA": "🇺🇸",
    "India": "🇮🇳",
    "United Kingdom": "🇬🇧",
    "UK": "🇬🇧",
    "Canada": "🇨🇦",
    "Australia": "🇦🇺",
    "Germany": "🇩🇪",
    "France": "🇫🇷",
    "Spain": "🇪🇸",
    "Italy": "🇮🇹",
    "Japan": "🇯🇵",
    "China": "🇨🇳",
    "South Korea": "🇰🇷",
    "Russia": "🇷🇺",
    "Brazil": "🇧🇷",
    "Mexico": "🇲🇽",
}


def list_to_str(data):
    if not data:
        return "N/A"
    if settings.MAX_LIST_ELM:
        data = data[:int(settings.MAX_LIST_ELM)]
    return ", ".join(map(str, data))


def _genre_emoji(genre: str) -> str:
    return GENRE_EMOJI.get(genre, "🎬")


def _country_flag(country: str) -> str:
    return COUNTRY_FLAGS.get(country, "")


def _format_runtime(runtimes: Optional[List[str]]) -> str:
    if not runtimes:
        return "N/A"
    runtime = str(runtimes[0])
    if runtime.isdigit():
        minutes = int(runtime)
        hours = minutes // 60
        mins = minutes % 60
        parts = []
        if hours:
            parts.append(f"{hours}h")
        if mins:
            parts.append(f"{mins}min")
        return " ".join(parts) if parts else f"{minutes}min"
    return runtime


def _parse_release_info(release_str: Optional[str]) -> Dict[str, str]:
    """Extract release date and country from a string like '16 July 2010 (USA)'."""
    if not release_str:
        return {"date": "N/A", "country": "N/A"}

    match = re.match(r"^(?P<date>.+?)\s*\((?P<country>.+)\)$", release_str)
    if match:
        date_str = match.group("date").strip()
        country = match.group("country").strip()
    else:
        parts = release_str.split("(")
        date_str = parts[0].strip()
        country = parts[1].replace(")", "").strip() if len(parts) > 1 else "N/A"

    for fmt in ["%d %B %Y", "%B %d %Y", "%Y-%m-%d", "%Y"]:
        try:
            dt = datetime.strptime(date_str, fmt)
            return {"date": dt.strftime("%d / %m / %Y"), "country": country}
        except Exception:
            continue

    return {"date": date_str, "country": country}


async def get_poster(
    query: str, *, bulk: bool = False, imdb_id: bool = False, id: bool = False, file=None
):
    if id:
        imdb_id = True
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


def _normalize_imdb_id(query: str) -> Optional[str]:
    """Return a cleaned IMDb ID (digits only) if query looks like an IMDb ID."""
    q = query.strip().lower()
    if q.startswith("tt"):
        q = q[2:]
    q = re.sub(r"\D", "", q)
    return q if q else None


async def get_imdb_info(query: str, *, imdb_id: bool = False, id: bool = False) -> Optional[Dict[str, Any]]:
    """Return structured movie info for /imdbinfo."""
    # Allow /imdbinfo <tt1234567> or <1234567>
    if not imdb_id and not id:
        normalized = _normalize_imdb_id(query)
        if normalized and len(normalized) >= 6:
            imdb_id = True
            query = normalized

    if id:
        imdb_id = True
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

    release = _parse_release_info(
        movie.get("original release date") or movie.get("original air date")
    )

    genres = movie.get("genres") or []
    genre_line = " ".join(f"{_genre_emoji(g)} #{g}" for g in genres) or "N/A"

    languages = movie.get("languages") or []
    languages_line = " ".join(f"#{lang}" for lang in languages) or "N/A"

    countries = movie.get("countries") or []
    country = countries[0] if countries else "N/A"
    country_line = f"{_country_flag(country)} #{country}" if country and country != "N/A" else "N/A"

    aka = movie.get("akas") or []
    aka_line = ", ".join(aka) if aka else "N/A"

    directors = movie.get("directors") or []
    writers = movie.get("writers") or []
    cast = movie.get("cast") or []

    def _person_link(person: Any) -> str:
        pid = getattr(person, "personID", None)
        name = getattr(person, "name", str(person))
        if pid:
            return f"{name} (https://www.imdb.com/name/nm{pid})"
        return name

    directors_line = " ".join(_person_link(d) for d in directors[:5]) or "N/A"
    writers_line = " ".join(_person_link(w) for w in writers[:5]) or "N/A"
    stars_line = " ".join(_person_link(a) for a in cast[:7]) or "N/A"

    runtime = _format_runtime(movie.get("runtimes"))

    return {
        "title": movie.get("title"),
        "year": movie.get("year"),
        "url": f"https://www.imdb.com/title/tt{imdb_id}",
        "aka": aka_line,
        "rating": movie.get("rating") or "N/A",
        "votes": movie.get("votes") or "N/A",
        "runtime": runtime,
        "release_date": release.get("date"),
        "release_country": release.get("country"),
        "release_link": f"https://www.imdb.com/title/tt{imdb_id}/releaseinfo",
        "genres_line": genre_line,
        "languages_line": languages_line,
        "country_line": country_line,
        "plot": plot,
        "directors_line": directors_line,
        "writers_line": writers_line,
        "stars_line": stars_line,
    }
