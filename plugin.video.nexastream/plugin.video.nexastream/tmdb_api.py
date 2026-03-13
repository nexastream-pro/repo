# -*- coding: utf-8 -*-
"""
TMDB API modul — NexaStream (VERZE 2.2 - CLEANED & FIXED)
Opraveno vyhledávání podle států a kódování diakritiky.
Vyčištěno od skrytých znaků.
"""

import json
import xbmc
import sys

if sys.version_info[0] >= 3:
    from urllib.request import urlopen, Request
    from urllib.parse import urlencode, quote
else:
    from urllib2 import urlopen, Request
    from urllib import urlencode, quote

TMDB_BASE     = 'https://api.themoviedb.org/3'
TMDB_IMG      = 'https://image.tmdb.org/t/p/'
POSTER_SIZE   = 'w500'
BACKDROP_SIZE = 'w1280'

MOVIE_GENRES = {
    28: 'Akční', 12: 'Dobrodružný', 16: 'Animovaný', 35: 'Komedie',
    80: 'Krimi', 99: 'Dokumentární', 18: 'Drama', 10751: 'Rodinný',
    14: 'Fantasy', 36: 'Historický', 27: 'Horor', 10402: 'Hudební',
    9648: 'Mysteriózní', 10749: 'Romantický', 878: 'Sci-Fi',
    10770: 'TV film', 53: 'Thriller', 10752: 'Válečný', 37: 'Western',
}

TV_GENRES = {
    10759: 'Akční & dobrodružný', 16: 'Animovaný', 35: 'Komedie',
    80: 'Krimi', 99: 'Dokumentární', 18: 'Drama', 10751: 'Rodinný',
    10762: 'Pro děti', 9648: 'Mysteriózní', 10763: 'Zprávy',
    10764: 'Reality', 10765: 'Sci-Fi & Fantasy', 10766: 'Soap opera',
    10767: 'Talk show', 10768: 'Válka & politika', 37: 'Western',
}

def _get(path, params, api_key):
    params['api_key'] = api_key
    params.setdefault('language', 'cs-CZ')
    
    safe_params = {}
    for k, v in params.items():
        # Bezpečné ošetření diakritiky
        if isinstance(v, str):
            safe_params[k] = v.encode('utf-8')
        elif sys.version_info[0] < 3 and isinstance(v, unicode):
            safe_params[k] = v.encode('utf-8')
        else:
            safe_params[k] = str(v)
            
    url = TMDB_BASE + path + '?' + urlencode(safe_params)
    
    try:
        import ssl
        ctx = ssl._create_unverified_context()
        req = Request(url, headers={'User-Agent': 'NexaStream/4.0'})
        resp = urlopen(req, timeout=10, context=ctx)
        return json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        xbmc.log('NexaStream - TMDB API [%s] error: %s' % (path, str(e)), xbmc.LOGERROR)
        return {}

def poster_url(path, size=POSTER_SIZE):
    if not path: return ''
    return TMDB_IMG + size + path

def backdrop_url(path, size=BACKDROP_SIZE):
    if not path: return ''
    return TMDB_IMG + size + path

def _parse_movie(item):
    year = ''
    rd = item.get('release_date', '')
    if rd and len(rd) >= 4: year = rd[:4]
    return {
        'id': str(item.get('id', '')),
        'tmdb_id': str(item.get('id', '')),
        'title': item.get('title', '') or item.get('original_title', ''),
        'orig_title': item.get('original_title', ''),
        'year': year,
        'plot': item.get('overview', ''),
        'poster': poster_url(item.get('poster_path', '')),
        'backdrop': backdrop_url(item.get('backdrop_path', '')),
        'type': 'movie',
        'popularity': item.get('popularity', 0),
        'vote_average': item.get('vote_average', 0)
    }

def _parse_tv(item):
    year = ''
    fa = item.get('first_air_date', '')
    if fa and len(fa) >= 4: year = fa[:4]
    return {
        'id': str(item.get('id', '')),
        'tmdb_id': str(item.get('id', '')),
        'title': item.get('name', '') or item.get('original_name', ''),
        'orig_title': item.get('original_name', ''),
        'year': year,
        'plot': item.get('overview', ''),
        'poster': poster_url(item.get('poster_path', '')),
        'backdrop': backdrop_url(item.get('backdrop_path', '')),
        'type': 'tvshow',
        'popularity': item.get('popularity', 0),
        'vote_average': item.get('vote_average', 0)
    }

# --- STÁVAJÍCÍ FUNKCE (Hledání, detaily) ---

def search_movies(api_key, query, page=1, year=''):
    params = {'query': query, 'page': page}
    if year: params['year'] = str(year)
    data = _get('/search/movie', params, api_key)
    results = [_parse_movie(r) for r in data.get('results', [])]
    return results, data.get('total_pages', 1)

def search_tvshows(api_key, query, page=1):
    data = _get('/search/tv', {'query': query, 'page': page}, api_key)
    results = [_parse_tv(r) for r in data.get('results', [])]
    return results, data.get('total_pages', 1)

def get_movie_details(api_key, tmdb_id):
    data = _get('/movie/%s' % tmdb_id, {'append_to_response': 'credits'}, api_key)
    if not data: return {}
    res = _parse_movie(data)
    res['genres'] = [g.get('name', '') for g in data.get('genres', [])]
    return res

def get_tvshow_details(api_key, tmdb_id):
    data = _get('/tv/%s' % tmdb_id, {'append_to_response': 'credits'}, api_key)
    if not data: return {}
    res = _parse_tv(data)
    res['genres'] = [g.get('name', '') for g in data.get('genres', [])]
    res['seasons'] = data.get('number_of_seasons', 0)
    return res

# --- OPRAVENÉ FUNKCE PRO DISCOVER (STÁTY) ---

def discover_movies(api_key, genre_id='', year='', sort_by='popularity.desc', page=1, country_code=''):
    params = {'sort_by': sort_by, 'page': page}
    if genre_id: params['with_genres'] = str(genre_id)
    if year: params['primary_release_year'] = str(year)
    # ZDE JE TA OPRAVA: Pro discover se používá with_origin_country
    if country_code: params['with_origin_country'] = str(country_code)
    
    data = _get('/discover/movie', params, api_key)
    results = [_parse_movie(r) for r in data.get('results', [])]
    return results, data.get('total_pages', 1)

def discover_tvshows(api_key, genre_id='', sort_by='popularity.desc', page=1, country_code=''):
    params = {'sort_by': sort_by, 'page': page}
    if genre_id: params['with_genres'] = str(genre_id)
    # ZDE JE TA OPRAVA: Pro discover se používá with_origin_country
    if country_code: params['with_origin_country'] = str(country_code)
    
    data = _get('/discover/tv', params, api_key)
    results = [_parse_tv(r) for r in data.get('results', [])]
    return results, data.get('total_pages', 1)

def get_tv_season(api_key, tmdb_id, season_number):
    data = _get('/tv/%s/season/%s' % (tmdb_id, season_number), {}, api_key)
    return data or {}

def get_genres(api_key, media_type='movie'):
    if media_type == 'movie': return list(MOVIE_GENRES.items())
    return list(TV_GENRES.items())