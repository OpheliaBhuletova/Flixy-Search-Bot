import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
import asyncio

import pycountry

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

CACHE_TTL_SECONDS = 60 * 60 * 6  # 6 hours
PERSON_CACHE_TTL_SECONDS = 60 * 60 * 24  # 24 hours

_tmdb_cache: Dict[str, tuple[float, dict]] = {}
_person_imdb_cache: Dict[int, tuple[float, Optional[str]]] = {}

_MISSING = object()

def list_to_str(data):
    if not data:
        return "N/A"
    if settings.MAX_LIST_ELM:
        data = data[: int(settings.MAX_LIST_ELM)]
    return ", ".join(map(str, data))

def _cache_get(cache: dict, key):
    item = cache.get(key)
    if item is None:
        return _MISSING

    expires_at, value = item
    if expires_at < time.time():
        cache.pop(key, None)
        return _MISSING

    return value


def _cache_set(cache: dict, key, value, ttl: int):
    cache[key] = (time.time() + ttl, value)


def _make_cache_key(endpoint: str, params: Optional[dict]) -> str:
    params = params or {}
    parts = [endpoint]
    for k in sorted(params):
        parts.append(f"{k}={params[k]}")
    return "|".join(parts)

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

def _cleanup_cache(cache: dict):
    now = time.time()
    expired = [k for k, (expires_at, _) in cache.items() if expires_at < now]
    for k in expired:
        cache.pop(k, None)


async def _tmdb_request(endpoint: str, params: Optional[dict] = None) -> Optional[dict]:
    if not settings.TMDB_API_KEY:
        return None

    params = params or {}
    params["api_key"] = settings.TMDB_API_KEY

    if len(_tmdb_cache) > 1000:
        _cleanup_cache(_tmdb_cache)

    if len(_person_imdb_cache) > 2000:
        _cleanup_cache(_person_imdb_cache)

    cache_key = _make_cache_key(endpoint, params)
    cached = _cache_get(_tmdb_cache, cache_key)
    if cached is not _MISSING:
        return cached

    url = f"https://api.themoviedb.org/3/{endpoint.lstrip('/')}"

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            _cache_set(_tmdb_cache, cache_key, data, CACHE_TTL_SECONDS)
            return data
    except Exception:
        return None


async def _find_tmdb_item(query: str, preferred_type: Optional[str] = None) -> Optional[dict]:
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
    production_countries = details.get("production_countries") or []
    origin_country = details.get("origin_country") or []

    # Best case: TMDb already gives the country name
    if production_countries:
        country = production_countries[0]
        name = country.get("name")
        if name:
            return name

        iso = country.get("iso_3166_1")
        if iso:
            try:
                return pycountry.countries.get(alpha_2=iso).name
            except Exception:
                return iso

    # Fallback: origin_country only gives ISO
    if origin_country:
        iso = origin_country[0]
        try:
            return pycountry.countries.get(alpha_2=iso).name
        except Exception:
            return iso

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


def _get_director_people(details: dict, media_type: str) -> List[dict]:
    crew = (details.get("credits") or {}).get("crew") or []

    if media_type == "movie":
        return [
            {"id": p.get("id"), "name": p.get("name")}
            for p in crew
            if p.get("job") == "Director" and p.get("id") and p.get("name")
        ][:5]

    created_by = details.get("created_by") or []
    return [
        {"id": p.get("id"), "name": p.get("name")}
        for p in created_by
        if p.get("id") and p.get("name")
    ][:5]


def _get_writer_people(details: dict) -> List[dict]:
    crew = (details.get("credits") or {}).get("crew") or []
    wanted_jobs = {"Writer", "Screenplay", "Story", "Original Story", "Series Composition"}

    people = []
    seen = set()

    for p in crew:
        pid = p.get("id")
        name = p.get("name")
        job = p.get("job")

        if pid and name and job in wanted_jobs and pid not in seen:
            seen.add(pid)
            people.append({"id": pid, "name": name})

    return people[:5]


def _get_cast_people(details: dict) -> List[dict]:
    cast = (details.get("credits") or {}).get("cast") or []
    return [
        {"id": p.get("id"), "name": p.get("name")}
        for p in cast
        if p.get("id") and p.get("name")
    ][:7]

async def _person_imdb_url(person_id: int) -> Optional[str]:
    cached = _cache_get(_person_imdb_cache, person_id)
    if cached is not _MISSING:
        return cached

    data = await _tmdb_request(f"person/{person_id}/external_ids")
    if not data:
        _cache_set(_person_imdb_cache, person_id, None, PERSON_CACHE_TTL_SECONDS)
        return None

    imdb_id = data.get("imdb_id")
    url = f"https://www.imdb.com/name/{imdb_id}" if imdb_id else None
    _cache_set(_person_imdb_cache, person_id, url, PERSON_CACHE_TTL_SECONDS)
    return url


async def _people_links(people: List[dict], limit: int = 7) -> str:
    people = people[:limit]
    if not people:
        return "N/A"

    urls = await asyncio.gather(
        *[_person_imdb_url(p["id"]) for p in people if p.get("id") and p.get("name")],
        return_exceptions=True,
    )

    linked = []
    valid_people = [p for p in people if p.get("id") and p.get("name")]

    for person, url in zip(valid_people, urls):
        if isinstance(url, Exception) or not url:
            linked.append(f"<a href='https://www.imdb.com/'>{person['name']}</a>")
        else:
            linked.append(f"<a href='{url}'>{person['name']}</a>")

    return ", ".join(linked)


def _get_plot(details: dict) -> str:
    plot = details.get("overview") or "N/A"
    if plot and plot != "N/A" and len(plot) > 800:
        return plot[:800] + "..."
    return plot

def _title_url(details: dict, media_type: str, imdb_id_value: Optional[str]) -> str:
    if imdb_id_value:
        return f"https://www.imdb.com/title/{imdb_id_value}"
    return f"https://www.themoviedb.org/{media_type}/{details.get('id')}"


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
        "rating": round(details.get("vote_average", 0), 1) if details.get("vote_average") else "N/A",
        "genres": list_to_str(_get_genres(details)),
        "poster": _poster_url(details.get("poster_path")) or _backdrop_url(details.get("backdrop_path")),
        "plot": _get_plot(details),
        "url": _title_url(details, media_type, imdb_id_value),
    }


async def get_imdb_info(query: str, *, imdb_id: bool = False, id: bool = False) -> Optional[Dict[str, Any]]:
    preferred_type = None

    if not imdb_id and not id:
        lowered = query.strip().lower()
        if lowered.startswith("tv "):
            preferred_type = "tv"
            query = query[3:].strip()
        elif lowered.startswith("series "):
            preferred_type = "tv"
            query = query[7:].strip()
        elif lowered.startswith("movie "):
            preferred_type = "movie"
            query = query[6:].strip()

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

        if preferred_type == "tv" and tv_results:
            item = tv_results[0]
            media_type = "tv"
        elif preferred_type == "movie" and movie_results:
            item = movie_results[0]
            media_type = "movie"
        elif movie_results:
            item = movie_results[0]
            media_type = "movie"
        elif tv_results:
            item = tv_results[0]
            media_type = "tv"
        else:
            return None

        details = await _get_tmdb_details(item["id"], media_type)
    else:
        item = await _find_tmdb_item(query, preferred_type=preferred_type)
        if not item:
            return None

        media_type = item.get("media_type", "movie")
        details = await _get_tmdb_details(item["id"], media_type)

    if not details:
        return None

    release_country = _pick_release_country(details)
    genres = _get_genres(details)
    languages = _get_languages(details)
    directors = _get_director_people(details, media_type)
    writers = _get_writer_people(details)
    stars = _get_cast_people(details)
    imdb_id_value = ((details.get("external_ids") or {}).get("imdb_id")) or None
    title = details.get("title") or details.get("name")
    year_raw = details.get("release_date") or details.get("first_air_date") or ""

    genre_line = " ".join(f"{_genre_emoji(g)} #{g}" for g in genres) or "N/A"
    languages_line = " ".join(f"#{lang.replace(' ', '_')}" for lang in languages) or "N/A"

    if release_country and release_country != "N/A":
        country_line = f"{_country_flag(release_country)} {release_country}"
    else:
        country_line = "N/A"

    directors_links = await _people_links(directors, limit=5)
    writers_links = await _people_links(writers, limit=5)
    stars_links = await _people_links(stars, limit=7)

    episode_runtime = details.get("episode_run_time") or []
    runtime_value = details.get("runtime") or (episode_runtime[0] if episode_runtime else None)

    return {
        "type_label": "TV Series" if media_type == "tv" else "Movie",
        "media_type": media_type,
        "title": title,
        "year": year_raw[:4] if year_raw else "N/A",
        "url": _title_url(details, media_type, imdb_id_value),
        "aka": details.get("original_title") or details.get("original_name") or "N/A",
        "rating": round(details.get("vote_average", 0), 1) if details.get("vote_average") else "N/A",
        "votes": details.get("vote_count") or "N/A",
        "runtime": _format_runtime(runtime_value),
        "release_date": _pick_release_date(details, media_type),
        "release_country": release_country,
        "release_link": f"https://www.imdb.com/title/{imdb_id_value}/releaseinfo" if imdb_id_value else "N/A",
        "genres_line": genre_line,
        "languages_line": languages_line,
        "country_line": country_line,
        "plot": _get_plot(details),
        "directors_line": directors_links,
        "writers_line": writers_links,
        "stars_line": stars_links,
    }