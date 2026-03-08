import re
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx

from bot.config import settings

GENRE_EMOJI = {
    "Action": "",
    "Adventure": "",
    "Animation": "",
    "Biography": "",
    "Comedy": "",
    "Crime": "️",
    "Documentary": "",
    "Drama": "",
    "Family": "‍‍‍",
    "Fantasy": "",
    "History": "",
    "Horror": "",
    "Music": "",
    "Musical": "",
    "Mystery": "️‍♂️",
    "Romance": "",
    "Sci-Fi": "",
    "Sport": "",
    "Thriller": "",
    "War": "⚔️",
    "Western": "",
}

COUNTRY_FLAGS = {
    "United States": "",
    "USA": "",
    "India": "",
    "United Kingdom": "",
    "UK": "",
    "Canada": "",
    "Australia": "",
    "Germany": "",
    "France": "",
    "Spain": "",
    "Italy": "",
    "Japan": "",
    "China": "",
    "South Korea": "",
    "Russia": "",
    "Brazil": "",
    "Mexico": "",
}


def list_to_str(data):
    if not data:
        return "N/A"
    if settings.MAX_LIST_ELM:
        data = data[: int(settings.MAX_LIST_ELM)]
    return ", ".join(map(str, data))


def _genre_emoji(genre: str) -> str:
    return GENRE_EMOJI.get(genre, "")


def _country_flag(country: str) -> str:
    return COUNTRY_FLAGS.get(country, "")


def _format_runtime(runtime_minutes: Optional[int]) -> str:
    if not runtime_minutes:
        return "N/A"

    minutes = int(runtime_minutes)
    hours = minutes // 60
    mins = minutes % 60

    parts = []
    if hours:
        parts.append(f"{hours}h")
    if mins:
        parts.append(f"{mins}min")

    return " ".join(parts) if parts else f"{minutes}min"


def _parse_release_date(date_str: Optional[str]) -> str:
    if not date_str:
        return "N/A"

    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            dt = datetime.strptime(date_str, fmt)
            if fmt == "%Y":
                return dt.strftime("%Y")
            return dt.strftime("%d / %m / %Y")
        except Exception:
            continue

    return date_str


def _normalize_imdb_id(query: str) -> Optional[str]:
    q = query.strip().lower()
    if q.startswith("tt"):
        q = q[2:]
    q = re.sub(r"\D", "", q)
    return q if q else None


def _extract_year_and_title(query: str) -> tuple[str, Optional[str]]:
    query = query.strip()
    year_match = re.findall(r"[1-2]\d{3}", query)
    year = year_match[0] if year_match else None
    title = query.replace(year, "").strip() if year else query
    return title, year


async def _tmdb_request(endpoint: str, params: Optional[dict] = None) -> Optional[dict]:
    if not settings.TMDB_API_KEY:
        return None

    params = params or {}
    params["api_key"] = settings.TMDB_API_KEY

    url = f"https://api.themoviedb.org/3/{endpoint.lstrip('/')}"

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()
    except Exception:
        return None


async def _find_tmdb_item(query: str) -> Optional[dict]:
    title, year = _extract_year_and_title(query)

    data = await _tmdb_request(
        "search/multi",
        {
            "query": title,
            "include_adult": "false",
        },
    )
    if not data:
        return None

    results = data.get("results") or []
    if not results:
        return None

    filtered = []
    for item in results:
        media_type = item.get("media_type")
        if media_type not in ("movie", "tv"):
            continue

        release_date = item.get("release_date") or item.get("first_air_date") or ""
        item_year = release_date[:4] if release_date else None

        if year and item_year == year:
            filtered.append(item)

    if filtered:
        return filtered[0]

    return next(
        (item for item in results if item.get("media_type") in ("movie", "tv")),
        None,
    )


async def _get_tmdb_details(tmdb_id: int, media_type: str) -> Optional[dict]:
    details = await _tmdb_request(
        f"{media_type}/{tmdb_id}",
        {"append_to_response": "credits,external_ids,release_dates,content_ratings"},
    )
    return details


def _poster_url(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    return f"https://image.tmdb.org/t/p/w500{path}"


def _backdrop_url(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    return f"https://image.tmdb.org/t/p/original{path}"


def _pick_release_country(details: dict) -> str:
    origin_country = details.get("origin_country") or []
    production_countries = details.get("production_countries") or []

    if origin_country:
        return origin_country[0]

    if production_countries:
        country = production_countries[0]
        return country.get("name") or country.get("iso_3166_1") or "N/A"

    return "N/A"


def _pick_release_date(details: dict, media_type: str) -> str:
    if media_type == "movie":
        return _parse_release_date(details.get("release_date"))
    return _parse_release_date(details.get("first_air_date"))


def _get_genres(details: dict) -> List[str]:
    return [g.get("name") for g in (details.get("genres") or []) if g.get("name")]


def _get_languages(details: dict) -> List[str]:
    spoken = details.get("spoken_languages") or []
    langs = [x.get("english_name") or x.get("name") for x in spoken if x.get("english_name") or x.get("name")]
    if langs:
        return langs

    original = details.get("original_language")
    return [original.upper()] if original else []


def _get_directors(details: dict, media_type: str) -> List[str]:
    crew = (details.get("credits") or {}).get("crew") or []

    if media_type == "movie":
        names = [p.get("name") for p in crew if p.get("job") == "Director" and p.get("name")]
    else:
        created_by = details.get("created_by") or []
        names = [p.get("name") for p in created_by if p.get("name")]

    return names[:5]


def _get_writers(details: dict, media_type: str) -> List[str]:
    crew = (details.get("credits") or {}).get("crew") or []

    wanted_jobs = {"Writer", "Screenplay", "Story", "Original Story", "Series Composition"}
    names = []

    for person in crew:
        name = person.get("name")
        job = person.get("job")
        if name and job in wanted_jobs and name not in names:
            names.append(name)

    return names[:5]


def _get_cast(details: dict) -> List[str]:
    cast = (details.get("credits") or {}).get("cast") or []
    return [p.get("name") for p in cast if p.get("name")][:7]


def _get_plot(details: dict) -> str:
    plot = details.get("overview") or "N/A"
    if plot and plot != "N/A" and len(plot) > 800:
        return plot[:800] + "..."
    return plot


async def get_poster(
    query: str,
    *,
    bulk: bool = False,
    imdb_id: bool = False,
    id: bool = False,
    file=None,
):
    if id:
        imdb_id = True

    details = None
    media_type = "movie"

    if imdb_id:
        normalized = _normalize_imdb_id(query)
        if not normalized:
            return None

        find_data = await _tmdb_request(f"find/tt{normalized}", {"external_source": "imdb_id"})
        if not find_data:
            return None

        movie_results = find_data.get("movie_results") or []
        tv_results = find_data.get("tv_results") or []

        if movie_results:
            item = movie_results[0]
            media_type = "movie"
        elif tv_results:
            item = tv_results[0]
            media_type = "tv"
        else:
            return None

        details = await _get_tmdb_details(item["id"], media_type)
    else:
        item = await _find_tmdb_item(query)
        if not item:
            return None

        media_type = item.get("media_type", "movie")
        details = await _get_tmdb_details(item["id"], media_type)

    if not details:
        return None

    release_date_raw = details.get("release_date") or details.get("first_air_date") or ""
    year = release_date_raw[:4] if release_date_raw else None
    imdb_id_value = ((details.get("external_ids") or {}).get("imdb_id")) or None

    return {
        "title": details.get("title") or details.get("name"),
        "year": year,
        "rating": details.get("vote_average") or "N/A",
        "genres": list_to_str(_get_genres(details)),
        "poster": _poster_url(details.get("poster_path")) or _backdrop_url(details.get("backdrop_path")),
        "plot": _get_plot(details),
        "url": f"https://www.imdb.com/title/{imdb_id_value}" if imdb_id_value else (
            f"https://www.themoviedb.org/{media_type}/{details.get('id')}"
        ),
    }


async def get_imdb_info(query: str, *, imdb_id: bool = False, id: bool = False) -> Optional[Dict[str, Any]]:
    if not imdb_id and not id:
        normalized = _normalize_imdb_id(query)
        if normalized and len(normalized) >= 6:
            imdb_id = True
            query = normalized

    if id:
        imdb_id = True

    details = None
    media_type = "movie"

    if imdb_id:
        normalized = _normalize_imdb_id(query)
        if not normalized:
            return None

        find_data = await _tmdb_request(f"find/tt{normalized}", {"external_source": "imdb_id"})
        if not find_data:
            return None

        movie_results = find_data.get("movie_results") or []
        tv_results = find_data.get("tv_results") or []

        if movie_results:
            item = movie_results[0]
            media_type = "movie"
        elif tv_results:
            item = tv_results[0]
            media_type = "tv"
        else:
            return None

        details = await _get_tmdb_details(item["id"], media_type)
    else:
        item = await _find_tmdb_item(query)
        if not item:
            return None

        media_type = item.get("media_type", "movie")
        details = await _get_tmdb_details(item["id"], media_type)

    if not details:
        return None

    release_country = _pick_release_country(details)
    genres = _get_genres(details)
    languages = _get_languages(details)
    directors = _get_directors(details, media_type)
    writers = _get_writers(details, media_type)
    stars = _get_cast(details)
    imdb_id_value = ((details.get("external_ids") or {}).get("imdb_id")) or None
    title = details.get("title") or details.get("name")
    year_raw = details.get("release_date") or details.get("first_air_date") or ""

    genre_line = " ".join(f"{_genre_emoji(g)} #{g}" for g in genres) or "N/A"
    languages_line = " ".join(f"#{lang.replace(' ', '_')}" for lang in languages) or "N/A"

    if release_country and release_country != "N/A":
        country_line = f"{_country_flag(release_country)} #{release_country}"
    else:
        country_line = "N/A"

    return {
        "title": title,
        "year": year_raw[:4] if year_raw else "N/A",
        "url": f"https://www.imdb.com/title/{imdb_id_value}" if imdb_id_value else (
            f"https://www.themoviedb.org/{media_type}/{details.get('id')}"
        ),
        "aka": details.get("original_title") or details.get("original_name") or "N/A",
        "rating": details.get("vote_average") or "N/A",
        "votes": details.get("vote_count") or "N/A",
        "runtime": _format_runtime(details.get("runtime") or details.get("episode_run_time", [None])[0]),
        "release_date": _pick_release_date(details, media_type),
        "release_country": release_country,
        "release_link": f"https://www.imdb.com/title/{imdb_id_value}/releaseinfo" if imdb_id_value else (
            f"https://www.themoviedb.org/{media_type}/{details.get('id')}"
        ),
        "genres_line": genre_line,
        "languages_line": languages_line,
        "country_line": country_line,
        "plot": _get_plot(details),
        "directors_line": ", ".join(directors) if directors else "N/A",
        "writers_line": ", ".join(writers) if writers else "N/A",
        "stars_line": ", ".join(stars) if stars else "N/A",
    }