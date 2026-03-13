# -*- coding: utf-8 -*-
"""
NexaStream v3.7.0 — VIP GOLD & HISTORY REPAIR
ZÁKLAD: Kompletní oprava ukládání historie, odstranění čtverečků a "TREZOR"
OPRAVY: Názvy filmů u VIP streamů jsou pevně vázány, velikosti souborů zachovány
"""

import sys, os, re, json, time as _time_mod
import urllib.request
import ssl

import xbmc
import xbmcgui
import xbmcplugin
import xbmcaddon

try:
    import xbmcvfs
    _translate_path = xbmcvfs.translatePath
except (ImportError, AttributeError):
    _translate_path = xbmc.translatePath

try:
    from urllib.parse import parse_qsl, urlencode
except ImportError:
    from urlparse import parse_qsl
    from urllib import urlencode

import tmdb_api
import webshare

# ══════════════════════════════════════════════════════════════════════════════
#  INICIALIZACE
# ══════════════════════════════════════════════════════════════════════════════

addon        = xbmcaddon.Addon()
addon_handle = int(sys.argv[1])
addon_url    = sys.argv[0]

profile_path = _translate_path(addon.getAddonInfo('profile'))
if not os.path.exists(profile_path):
    try: os.makedirs(profile_path)
    except: pass

WATCHED_FILE = os.path.join(profile_path, 'watched.json')
TOKEN_FILE   = os.path.join(profile_path, 'ws_token.json')
SEARCH_FILE  = os.path.join(profile_path, 'search.json')
TMDB_KEY     = addon.getSetting('tmdb_api_key') or 'a9d851cb36fd8287fed226766d7f01ab'

STRM_PATH = os.path.join(profile_path, 'library')
STRM_MOVIES = os.path.join(STRM_PATH, 'movies')
STRM_TVSHOWS = os.path.join(STRM_PATH, 'tvshows')

for p in [STRM_MOVIES, STRM_TVSHOWS]:
    if not os.path.exists(p):
        try: os.makedirs(p)
        except: pass

# ══════════════════════════════════════════════════════════════════════════════
#  NEXASTREAM API ENGINE
# ══════════════════════════════════════════════════════════════════════════════

def _check_trezor(tmdb_id):
    if not tmdb_id: return []
    try:
        import ssl, urllib.request, json
        ctx = ssl._create_unverified_context()
        # PŘIDÁN KLÍČ DO URL
        api_call = "https://nexa.rybaribezhranic.cz/api.php?key=NexaPro2026&tmdb_id=" + str(tmdb_id)
        with urllib.request.urlopen(api_call, timeout=4, context=ctx) as response:
            data = json.loads(response.read().decode('utf-8'))
            if data.get('status') == 'ok': 
                return data.get('results', [])
    except: pass
    return []
_VIP_IDS_CACHE = None

def _get_vip_ids():
    global _VIP_IDS_CACHE
    if _VIP_IDS_CACHE is not None: return _VIP_IDS_CACHE
    try:
        import ssl, urllib.request, json
        ctx = ssl._create_unverified_context()
        # PŘIDÁN KLÍČ DO URL
        api_url = "https://nexa.rybaribezhranic.cz/api.php?key=NexaPro2026&mode=all_ids"
        with urllib.request.urlopen(api_url, timeout=3, context=ctx) as response:
            data = json.loads(response.read().decode('utf-8'))
            if data.get('status') == 'ok': 
                _VIP_IDS_CACHE = set(str(x) for x in data.get('ids', []))
                return _VIP_IDS_CACHE
    except: pass
    _VIP_IDS_CACHE = set()
    return _VIP_IDS_CACHE
# ══════════════════════════════════════════════════════════════════════════════
#  CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════

COUNTRY_NAMES = {
    'US':'USA','GB':'Velká Británie','CZ':'Česká republika','SK':'Slovensko',
    'DE':'Německo','FR':'Francie','IT':'Itálie','ES':'Španělsko','PL':'Polsko',
    'RU':'Rusko','AU':'Austrálie','CA':'Kanada','JP':'Japonsko','KR':'Jižní Korea',
    'CN':'Čína','IN':'Indie','SE':'Švédsko','NO':'Norsko','DK':'Dánsko',
    'FI':'Finsko','NL':'Nizozemsko','BE':'Belgie','AT':'Rakousko','CH':'Švýcarsko',
    'HU':'Maďarsko','BR':'Brazílie','MX':'Mexiko','AR':'Argentina','ZA':'Jižní Afrika',
    'IE':'Irsko','PT':'Portugalsko','TR':'Turecko','IL':'Izrael','TH':'Thajsko',
}
FEATURED_COUNTRIES_MOVIE  = ['US','GB','CZ','SK','DE','FR','IT','ES','AU','CA','JP','KR','RU','PL','SE','DK','NO']
FEATURED_COUNTRIES_TVSHOW = ['US','GB','CZ','SK','DE','FR','KR','JP','SE','DK','NO','AU','CA','RU','PL']

QUALITY_PATTERN = (
    r'\b(720p|1080p|2160p|4K|UHD|BluRay|BRRip|WEBRip|HDTV|WEB-DL|DVDRip|'
    r'x264|x265|HEVC|H\.264|H\.265|AAC|AC3|DTS|'
    r'CZ|SK|EN|MULTI|DUAL|SUB|DUBBED|'
    r'KINORIP|CAMRIP|TELESYNC|TS|CAM|SCREENER|'
    r'REMUX|PROPER|REPACK|UNRATED|EXTENDED|'
    r'DD5\.1|TrueHD|ATMOS)\b'
)

# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _norm(s):
    import unicodedata
    try:
        if isinstance(s, bytes): s = s.decode('utf-8')
        n = unicodedata.normalize('NFD', s)
        return u''.join(c for c in n if unicodedata.category(c) != 'Mn').lower().strip()
    except:
        return (s or '').lower().strip()

def _url(**kw):
    safe = {}
    for k, v in kw.items():
        if v is None: v = ''
        if isinstance(v, (list, dict)): v = json.dumps(v, ensure_ascii=False)
        safe[str(k)] = str(v)
        
    # MAGICKÝ TRIK: Automatické předávání dětského štítku do všech dalších složek a přehrávače
    try:
        import sys
        from urllib.parse import parse_qsl
        current_params = dict(parse_qsl(sys.argv[2][1:]))
        if current_params.get('is_kids') == 'true' and 'is_kids' not in safe:
            safe['is_kids'] = 'true'
    except: pass
    
    return addon_url + '?' + urlencode(safe)

def _set_info(li, info, is_folder=False):
    try:
        tag = li.getVideoInfoTag()
        if info.get('title'):    tag.setTitle(info['title'])
        if info.get('originaltitle'): tag.setOriginalTitle(info['originaltitle']) 
        if info.get('plot'):     tag.setPlot(info['plot'])
        if info.get('year'):
            try: tag.setYear(int(info['year']))
            except: pass
        if info.get('genre'):    tag.setGenres([info['genre']])
        if info.get('director'): tag.setDirectors([info['director']])
        if info.get('duration'):
            try: tag.setDuration(int(info['duration']))
            except: pass
        if info.get('season'):
            try: tag.setSeason(int(info['season']))
            except: pass
        if info.get('episode'):
            try: tag.setEpisode(int(info['episode']))
            except: pass
        if info.get('cast'):
            try: tag.setCast([xbmc.Actor(n,'',0,'') for n in info['cast'][:10]])
            except: pass
        if info.get('playcount') is not None:
            tag.setPlaycount(int(info['playcount']))
        tag.setMediaType(info.get('mediatype','movie'))
    except AttributeError:
        kodi_info = {k: v for k, v in info.items()
                     if k in ('title','plot','year','genre','director','duration',
                               'cast','season','episode','mediatype','playcount','originaltitle')}
        li.setInfo('video', kodi_info)

def _notify(msg, icon=xbmcgui.NOTIFICATION_INFO, ms=3000):
    xbmcgui.Dialog().notification('NexaStream', msg, icon, ms)

def _add_dir(name, url, img='DefaultFolder.png', fanart='', plot=''):
    li = xbmcgui.ListItem(name)
    art = {'icon': img, 'thumb': img}
    if fanart:
        art['fanart'] = fanart
        li.setProperty('fanart_image', fanart)
        li.setProperty('landscape', fanart)
    li.setArt(art)
    
    # NOVÉ: Přidání popisku (vysvětlení složky)
    if plot:
        try:
            tag = li.getVideoInfoTag()
            tag.setPlot(plot)
        except AttributeError:
            li.setInfo('video', {'plot': plot})
            
    xbmcplugin.addDirectoryItem(addon_handle, url, li, True)

def _end(update_listing=False):
    xbmcplugin.endOfDirectory(addon_handle, updateListing=update_listing)

def _fail(msg=''):
    if msg: _notify(msg, xbmcgui.NOTIFICATION_WARNING)
    xbmcplugin.endOfDirectory(addon_handle, succeeded=False)

# ══════════════════════════════════════════════════════════════════════════════
#  VIP KOD 
# ══════════════════════════════════════════════════════════════════════════════
def check_vip_access():
    # --- HLAVNÍ VYPÍNAČ ZÁMKU ---
    # Okamžitě povolí přístup všem bez ověřování
    return True 
    # ----------------------------

    import urllib.request
    import urllib.parse
    import json
    import xbmcgui
    import xbmcaddon
    
    addon = xbmcaddon.Addon()
    vip_code = addon.getSetting('vip_code')
    ws_user = addon.getSetting('username') 
    
    if not vip_code:
        xbmcgui.Dialog().ok('NexaStream', 'Tato prémiová sekce je uzamčena.\nPro přístup si prosím vyžádejte a zadejte VIP kód\nv nastavení tohoto doplňku.')
        return False
        
    if not ws_user:
        xbmcgui.Dialog().ok('NexaStream', 'Chybí Webshare účet.\nPro ověření VIP kódu musíte mít v nastavení\nvyplněné své přihlašovací jméno na Webshare.')
        return False

    # Volání tvého vrátného na webu
    api_url = "http://nexa.rybaribezhranic.cz/api_vip.php?code=" + urllib.parse.quote(vip_code) + "&user=" + urllib.parse.quote(ws_user)
    
    try:
        req = urllib.request.Request(api_url)
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode('utf-8'))
            
        if data.get('status') == 'ok':
            return True
        else:
            error_msg = data.get('msg', 'Neznámá chyba při ověřování kódu.')
            xbmcgui.Dialog().ok('NexaStream', f'Přístup odepřen!\n{error_msg}')
            return False
            
    except Exception as e:
        xbmcgui.Dialog().ok('NexaStream', f'Chyba serveru.\nNepodařilo se spojit s ověřovacím serverem NexaStream.\nDetail: {str(e)}')
        return False

def show_support_info():
    import xbmcgui
    import xbmc
    import xbmcaddon
    import os
    
    addon = xbmcaddon.Addon()
    addon_path = addon.getAddonInfo('path')
    qr_revolut_path = os.path.join(addon_path, 'fanart/qr_revolut.png') 
    qr_web_path = os.path.join(addon_path, 'fanart/qr_web.png') 
    
    title = "* Podpora projektu NexaStream"
    
    # Tady se můžeme rozepsat a provzdušnit to! Textviewer má místa dost.
    body = "[B][COLOR gold]PODPOŘTE VÝVOJ A NAŠE UPLOADERY[/COLOR][/B]\n"
    body += "--------------------------------------------------------\n\n"
    body += "NexaStream je nyní 100% otevřený a zdarma pro všechny.\n"
    body += "Provoz serverů a odměny pro naše skvělé uploadery ale něco stojí.\n\n"
    body += "Líbí se vám naše práce? Budeme rádi za vaši podporu!\n\n"
    body += "[COLOR gray]Web:[/COLOR] https://nexastream-pro.github.io/nexastream-pro/\n"
    body += "[COLOR gray]Revolut:[/COLOR] @nexaxtream\n\n"
    body += "Děkujeme, že tvoříte komunitu s námi!"

    dialog = xbmcgui.Dialog()
    
    # KROK 1: Zobrazíme obrovské, vzdušné a statické okno pro čtení textu
    dialog.textviewer(title, body)
    
# KROK 2: Po zavření čtecího okna se zeptáme na zobrazení QR kódu
    if dialog.yesno("Zobrazit QR kód?", "Díky za podporu, tady je QR kód\npro rychlé naskenování mobilem a další informace o projektu.", nolabel='ZAVŘÍT', yeslabel='ZOBRAZIT QR KÓD'):
        
        # Pokud klikne ANO, dáme mu vybrat
        možnosti = [
            "Zobrazit QR kód - Podpora Revolut",
            "Zobrazit QR kód - Náš Web (GitHub)"
        ]
        volba = dialog.select("Který kód chcete zobrazit?", možnosti)
        
        if volba == 0:
            xbmc.executebuiltin(f'ShowPicture("{qr_revolut_path}")')
        elif volba == 1:
            xbmc.executebuiltin(f'ShowPicture("{qr_web_path}")')
# ══════════════════════════════════════════════════════════════════════════════
#  TOKEN / LOGIN 
# ══════════════════════════════════════════════════════════════════════════════

def _load_token():
    try:
        if os.path.exists(TOKEN_FILE):
            data = json.load(open(TOKEN_FILE, 'r'))
            if 'username' not in data:
                return data.get('token')
            current_user = addon.getSetting('username')
            current_pass = addon.getSetting('password')
            if data.get('username') != current_user or data.get('password') != current_pass:
                os.remove(TOKEN_FILE)
                return None
            return data.get('token')
    except: pass
    return None

def _save_token(token):
    try:
        current_user = addon.getSetting('username')
        current_pass = addon.getSetting('password')
        json.dump({'token': token, 'username': current_user, 'password': current_pass}, open(TOKEN_FILE, 'w'))
    except: pass

def _get_token(force=False):
    if not force:
        t = _load_token()
        if t: return t
    username = addon.getSetting('username')
    password = addon.getSetting('password')
    if not username or not password: return None
    token = webshare.login(username, password)
    if token: _save_token(token)
    return token

def do_login():
    username = addon.getSetting('username')
    password = addon.getSetting('password')
    try:
        if os.path.exists(TOKEN_FILE): os.remove(TOKEN_FILE)
    except: pass
    if not username or not password:
        xbmcgui.Dialog().ok('NexaStream', '❌ V systému nejsou uloženy žádné údaje.\nVyplňte je v nastavení.')
        addon.openSettings()
        return _fail()
    token = webshare.login(username, password)
    if token:
        _save_token(token)
        xbmcgui.Dialog().ok('NexaStream', '✅ Přihlášení úspěšné!')
    else:
        xbmcgui.Dialog().ok('NexaStream', '❌ Přihlášení SELHALO!')
    _fail()

# ══════════════════════════════════════════════════════════════════════════════
#  HISTORIE HLEDÁNÍ
# ══════════════════════════════════════════════════════════════════════════════

def _load_searches():
    try:
        if os.path.exists(SEARCH_FILE): return json.load(open(SEARCH_FILE, 'r'))
    except: pass
    return []

def _save_search(query):
    searches = _load_searches()
    if query in searches: searches.remove(query)
    searches.insert(0, query)
    searches = searches[:20]
    try: json.dump(searches, open(SEARCH_FILE, 'w'))
    except: pass

def clear_search_history():
    try: os.remove(SEARCH_FILE)
    except: pass
    _notify('Historie hledání byla vymazána')
    xbmc.executebuiltin('Container.Refresh')

def search_menu(search_id='', is_kids='false'):
    xbmcplugin.setContent(addon_handle, 'videos')
    _add_dir('[COLOR lime]>> Nové hledání[/COLOR]', _url(mode='do_search', search_id=search_id, is_kids=is_kids))
    
    searches = _load_searches()
    if searches:
        _add_dir('[COLOR red]Vymazat historii hledání[/COLOR]', _url(mode='clear_search_history'))
        for s in searches:
            _add_dir(s, _url(mode='do_search', search_id=search_id, query=s, is_kids=is_kids), img='DefaultAddonsSearch.png')
    _end()

# ══════════════════════════════════════════════════════════════════════════════
#  WATCHED, PŘEHRÁVAČ A STRM EXPORT
# ══════════════════════════════════════════════════════════════════════════════

def _load_watched():
    try:
        if os.path.exists(WATCHED_FILE): return json.load(open(WATCHED_FILE, 'r'))
    except: pass
    return {}

def _save_watched(data):
    try: json.dump(data, open(WATCHED_FILE, 'w'), indent=2)
    except: pass

def _trim_watched(watched):
    max_w = int(addon.getSetting('max_watched') or '100')
    if len(watched) > max_w:
        for k, _ in sorted(watched.items(), key=lambda i: i[1]['time'], reverse=True)[max_w:]:
            del watched[k]
    return watched

class SCCPlayer(xbmc.Player):
    def __init__(self, ident, title, media_type='movie', size='', is_kids='false'):
        xbmc.Player.__init__(self)
        self.ident = ident
        self.title = title
        self.media_type = media_type
        self.size = size
        self.is_kids = is_kids # NOVÉ: Převzetí dětského štítku
        self.last_time = 0
        self.last_total = 0

    def onPlayBackStopped(self):
        try:
            time = self.last_time
            total = self.last_total
            if total > 0 and (time / total) > 0.90:
                _auto_watched(self.ident, self.title, size=self.size, playcount=1, resume_time=0, total_time=total, media_type=self.media_type, is_kids=self.is_kids)
            elif time > 15:
                _auto_watched(self.ident, self.title, size=self.size, playcount=0, resume_time=time, total_time=total, media_type=self.media_type, is_kids=self.is_kids)
        except: pass

    def onPlayBackEnded(self):
        _auto_watched(self.ident, self.title, size=self.size, playcount=1, resume_time=0, media_type=self.media_type, is_kids=self.is_kids)

def _auto_watched(ident, title, size='', img='', media_type='movie', playcount=0, resume_time=0, total_time=0, is_kids='false'):
    watched = _load_watched()
    ex = watched.get(ident, {})
    watched[ident] = {
        'title': title, 'size': size or ex.get('size', ''), 'img': img or ex.get('img', ''),
        'time': int(_time_mod.time()), 'media_type': media_type,
        'playcount': playcount if playcount else ex.get('playcount', 0),
        'resume_time': resume_time, 'total_time': total_time or ex.get('total_time', 0),
        'is_kids': is_kids or ex.get('is_kids', 'false') # NOVÉ: Uložení do databáze historie
    }
    _save_watched(_trim_watched(watched))

def watched_add(ident, title, size='', img='', media_type='movie', is_kids='false'):
    _auto_watched(ident, title, size, img, media_type, playcount=1, is_kids=is_kids)
    _notify('Přidáno do zhlédnutých')
    xbmc.executebuiltin('Container.Refresh')

def watched_remove(ident):
    watched = _load_watched()
    if ident in watched:
        del watched[ident]
        _save_watched(watched)
    _notify('Odebráno z historie')
    xbmc.executebuiltin('Container.Refresh')

def export_to_strm(ident, title, media_type='movie', season='', episode=''):
    safe_title = re.sub(r'[\\/*?:"<>|]', "", title)
    if media_type == 'episode':
        folder_path = os.path.join(STRM_TVSHOWS, safe_title)
        if not os.path.exists(folder_path): os.makedirs(folder_path)
        file_path = os.path.join(folder_path, f"{safe_title} S{int(season):02d}E{int(episode):02d}.strm")
    else:
        folder_path = os.path.join(STRM_MOVIES, safe_title)
        if not os.path.exists(folder_path): os.makedirs(folder_path)
        file_path = os.path.join(folder_path, f"{safe_title}.strm")

    url = _url(mode='play', ident=ident, title=title, media_type=media_type)
    try:
        with open(file_path, 'w', encoding='utf-8') as f: f.write(url)
        _notify('Exportováno do knihovny Kodi!')
        xbmc.executebuiltin('UpdateLibrary(video)')
    except Exception as e:
        _notify(f'Chyba exportu: {e}', xbmcgui.NOTIFICATION_ERROR)

# ══════════════════════════════════════════════════════════════════════════════
#  ROOT MENU
# ══════════════════════════════════════════════════════════════════════════════

def main_menu():
    xbmcplugin.setContent(addon_handle, 'videos')
    
    # 5. Účet Webshare
    _show_account_status()
    # 6. Podpora
    _add_dir('[COLOR gold][B]Podpora projektu NexaStream[/B][/COLOR]', _url(mode='vip_info'), img='DefaultAddonInfo.png')
    # 4. Hledání
    _add_dir('[B]Hledání[/B]', _url(mode='search_menu'), img='DefaultAddonsSearch.png')
    # 1. Filmy
    _add_dir('[B]Filmy[/B]', _url(mode='movies_menu'), img='DefaultMovies.png')
    # 2. Seriály
    _add_dir('[B]Seriály[/B]', _url(mode='shows_menu'), img='DefaultTVShows.png')
    # 3. Dětský svět
    _add_dir('[COLOR FF10B981][B]Dětský svět[/B][/COLOR]', _url(mode='kids_world_menu'), img='DefaultVideo.png')
    # 7. Nastavení
    _add_dir('[COLOR gray][B]Nastavení doplňku[/B][/COLOR]', _url(mode='settings'), img='DefaultAddonSettings.png')
    
    _end()

def movies_menu():
    xbmcplugin.setContent(addon_handle, 'videos')
    _add_dir('[B]Hledat film[/B]', _url(mode='do_search', search_id='movie'), img='DefaultAddonsSearch.png')
    _add_dir('[COLOR orange]>> Pokračovat ve sledování[/COLOR]', _url(mode='in_progress_list'), img='DefaultVideo.png')
    _add_dir('Historie zhlédnutých filmů', _url(mode='watched_list', media_type='movie'), img='DefaultRecentlyAddedMovies.png')
    _add_dir('[COLOR pink]Moje Oblíbené filmy[/COLOR]', _url(mode='placeholder_msg', msg='Oblíbené'), img='DefaultVideo.png')
    _add_dir('[COLOR lime]Stažené filmy[/COLOR]', _url(mode='placeholder_msg', msg='Stažené'), img='DefaultFolder.png')
    _add_dir('[COLOR FF8B5CF6]Nové Filmy v Trezoru[/COLOR]', _url(mode='trezor_list', api_mode='movies', title='Filmy'), img='DefaultRecentlyAddedMovies.png')
    _add_dir('[COLOR FF0EA5E9]Nové filmy s CZ dabingem[/COLOR]', _url(mode='trezor_list', api_mode='cz_only', title='CZ Dabing'), img='DefaultVideo.png')
    _add_dir('[COLOR FF38BDF8]VOD Služby (Netflix, HBO...)[/COLOR]', _url(mode='show_vod_menu'), img='DefaultTVShows.png')
    _add_dir('Trendy a Populární filmy', _url(mode='trending_movies'), img='DefaultRecentlyAddedMovies.png')
    _add_dir('Filmové Kolekce', _url(mode='collections_root'), img='DefaultMovies.png')
    _add_dir('Podle abecedy', _url(mode='alphabet_root', media_type='movie', prefix=''), img='DefaultMusicAlbums.png')
    _add_dir('Podle žánru', _url(mode='genre_list', media_type='movie'), img='DefaultGenre.png')
    _add_dir('Podle státu', _url(mode='country_list', media_type='movie'), img='DefaultCountry.png')
    _end()

def shows_menu():
    xbmcplugin.setContent(addon_handle, 'videos')
    _add_dir('[B]Hledat seriál[/B]', _url(mode='do_search', search_id='tvshow'), img='DefaultAddonsSearch.png')
    _add_dir('[COLOR orange]>> Moje rozkoukané seriály[/COLOR]', _url(mode='active_series', is_kids='false'), img='DefaultTVShows.png')
    _add_dir('Historie zhlédnutých seriálů', _url(mode='watched_list', media_type='tvshow'), img='DefaultRecentlyAddedEpisodes.png')
    _add_dir('[COLOR pink]Moje Oblíbené seriály[/COLOR]', _url(mode='placeholder_msg', msg='Oblíbené'), img='DefaultVideo.png')
    _add_dir('[COLOR lime]Stažené seriály[/COLOR]', _url(mode='placeholder_msg', msg='Stažené'), img='DefaultFolder.png')
    _add_dir('[COLOR FF8B5CF6]Nové Seriály v Trezoru[/COLOR]', _url(mode='trezor_list', api_mode='shows', title='Seriály'), img='DefaultRecentlyAddedEpisodes.png')
    _add_dir('[COLOR FF38BDF8]VOD Služby (Netflix, HBO...)[/COLOR]', _url(mode='show_vod_menu'), img='DefaultTVShows.png')
    _add_dir('Podle abecedy', _url(mode='alphabet_root', media_type='tvshow', prefix=''), img='DefaultMusicAlbums.png')
    _add_dir('Podle žánru', _url(mode='genre_list', media_type='tvshow'), img='DefaultGenre.png')
    _add_dir('Podle státu', _url(mode='country_list', media_type='tvshow'), img='DefaultCountry.png')
    _end()

def kids_world_menu():
    xbmcplugin.setContent(addon_handle, 'videos')
    _add_dir('[B]Hledat pohádku[/B]', _url(mode='search_menu', search_id='kids', is_kids='true'), img='DefaultAddonsSearch.png')
    _add_dir('[COLOR orange]>> Pokračovat v pohádce[/COLOR]', _url(mode='kids_in_progress'), img='DefaultVideo.png')
    _add_dir('[COLOR cyan]Naše rozkoukané seriály[/COLOR]', _url(mode='active_series', is_kids='true'), img='DefaultTVShows.png')
    _add_dir('[COLOR FF8B5CF6]Nové pohádky v Trezoru[/COLOR]', _url(mode='kids_trezor_latest', api_mode='movies'), img='DefaultRecentlyAddedMovies.png')
    _add_dir('[COLOR FF8B5CF6]Nové dětské seriály (Trezor)[/COLOR]', _url(mode='kids_trezor_latest', api_mode='shows'), img='DefaultRecentlyAddedEpisodes.png')
    _add_dir('[COLOR FF10B981]Populární Dětské Filmy[/COLOR]', _url(mode='kids_discover', m_type='movie', is_kids='true'), img='DefaultMovies.png')
    _add_dir('[COLOR FF10B981]Dětské Seriály a Večerníčky[/COLOR]', _url(mode='kids_discover', m_type='tv', is_kids='true'), img='DefaultTVShows.png')
    _add_dir('[COLOR FF10B981]České Večerníčky a seriály[/COLOR]', _url(mode='kids_vecernicky'), img='DefaultTVShows.png')
    _add_dir('[COLOR FF10B981]České filmové pohádky[/COLOR]', _url(mode='kids_cz_movies'), img='DefaultMovies.png')
    _end()

def show_trezor_list(api_mode, title):
    content_type = 'movies' if api_mode == 'movies' else 'tvshows' if api_mode == 'shows' else 'videos'
    xbmcplugin.setContent(addon_handle, content_type)
    
    prog = xbmcgui.DialogProgress()
    prog.create('NexaStream', 'Načítám z Trezoru: %s...' % title)
    try:
        ctx = ssl._create_unverified_context()
        api_call = "https://nexa.rybaribezhranic.cz/api.php?key=NexaPro2026&mode=" + api_mode
        with urllib.request.urlopen(api_call, timeout=4, context=ctx) as response:
            data = json.loads(response.read().decode('utf-8'))
            if data.get('status') == 'ok':
                for item in data.get('results', []):
                    t_id = item.get('tmdb_id')
                    m_type = item.get('type', 'movie')
                    
                    if m_type == 'movie':
                        det = tmdb_api.get_movie_details(TMDB_KEY, t_id)
                        if det:
                            _add_dir('[B]%s[/B]' % det['title'], _url(mode='select_quality', tmdb_id=t_id, title=det['title'], year=det.get('year',''), orig_title=det.get('original_title','')), img=det.get('poster',''), fanart=det.get('backdrop',''))
                    else:
                        det = tmdb_api.get_tvshow_details(TMDB_KEY, t_id)
                        if det:
                            _add_dir('[B]%s[/B]' % det['title'], _url(mode='series_list', tmdb_id=t_id, serial_title=det['title'], serial_year=det.get('year',''), serial_original_name=det.get('original_name', det.get('original_title',''))), img=det.get('poster',''), fanart=det.get('backdrop',''))
    except: pass
    finally: prog.close()
    _end()

def show_in_progress_list():
    xbmcplugin.setContent(addon_handle, 'videos')
    watched = _load_watched()
    in_progress = {k: v for k, v in watched.items() if v.get('resume_time', 0) > 0 and v.get('playcount', 0) == 0}

    if not in_progress:
        return _fail('Zatím nemáte nic rozkoukáno.')

    for ident, data in sorted(in_progress.items(), key=lambda i: i[1]['time'], reverse=True):
        raw_title = data.get('title', '')
        
        # --- ZPĚTNÁ OPRAVA HISTORIE ---
        clean_title = re.sub(r'\[/?(?:COLOR|B|I)[^\]]*\]', '', raw_title, flags=re.I)
        clean_title = clean_title.replace('[]', '').replace('>>', '').strip()
        clean_title = re.sub(r'^(?:TREZOR:\s*)+', '', clean_title).strip()

        is_vip = "★ VIP" in clean_title or "TREZOR" in raw_title

        if "★ VIP:" in clean_title: clean_title = clean_title.replace("★ VIP:", "").strip()
        if not clean_title: clean_title = "Neznámý VIP titul"

        size_str = data.get('size', '')
        size_label = '  [I][%s][/I]' % size_str if size_str else ''

        # Čisté vykreslení s elegantní šipkou a vrácením zlaté barvy pro VIP
        if is_vip:
            label = '[COLOR orange]►[/COLOR] [COLOR gold]★ VIP: %s[/COLOR]%s' % (clean_title, size_label)
        else:
            label = '[COLOR orange]►[/COLOR] %s%s' % (clean_title, size_label)

        li = xbmcgui.ListItem(label)
        li.setProperty('IsPlayable', 'true')
        if data.get('img'): li.setArt({'thumb': data['img']})
        
        li.setProperty('ResumeTime', str(data['resume_time']))
        if data.get('total_time'): li.setProperty('TotalTime', str(data['total_time']))

        info = {'title': clean_title, 'mediatype': data.get('media_type', 'movie')}
        _set_info(li, info)
        li.addContextMenuItems([('Odebrat z historie', 'RunPlugin(%s)' % _url(mode='remove_watched', ident=ident))])
        xbmcplugin.addDirectoryItem(addon_handle, _url(mode='play', ident=ident, title=clean_title, media_type=data.get('media_type', 'movie'), size=size_str), li, False)
    _end()

def _show_account_status():
    token = _load_token()
    if not token and addon.getSetting('username') and addon.getSetting('password'):
        token = _get_token()

    if token:
        try:
            xml = webshare._post('user_data', {}, token=token)
            if xml and webshare._x(xml, 'status') == 'OK':
                username = webshare._x(xml, 'username') or addon.getSetting('username') or '?'
                vip      = webshare._x(xml, 'vip') == '1'
                vip_days = webshare._x(xml, 'vip_days')

                if vip and vip_days and str(vip_days).isdigit(): badge = ' [COLOR lime][VIP | %s dni][/COLOR]' % vip_days
                elif vip: badge = ' [COLOR lime][VIP][/COLOR]'
                else: badge = ' [COLOR gray][Free][/COLOR]'

                import os
                addon_path = addon.getAddonInfo('path')
                if hasattr(addon_path, 'decode'): addon_path = addon_path.decode('utf-8')
                bg_ucet = os.path.join(addon_path, 'fanart', 'bg_ucet.jpg')

                _add_dir('[B]Účet: %s%s[/B]' % (username, badge), _url(mode='account_info'), img='DefaultAddonService.png', fanart=bg_ucet)
                return
        except: pass
        
    _add_dir('Prihlasit se na Webshare.cz', _url(mode='do_login'), img='DefaultAddonService.png')

def show_account_info():
    token = _load_token()
    if not token: return _fail('Nejste prihlaseni.')
    try:
        xml = webshare._post('user_data', {}, token=token)
        if xml and webshare._x(xml, 'status') == 'OK':
            username = webshare._x(xml, 'username')
            email    = webshare._x(xml, 'email')
            vip      = webshare._x(xml, 'vip') == '1'
            vip_days = webshare._x(xml, 'vip_days')
            vip_text = ('ANO (%s dni)' % vip_days) if (vip and vip_days) else ('ANO' if vip else 'NE (viz webshare.cz)')
            xbmcgui.Dialog().ok('Webshare ucet', 'Uzivatel: %s\nE-mail: %s\nVIP: %s' % (username, email, vip_text))
    except Exception as e:
        xbmcgui.Dialog().ok('NexaStream', 'Nelze nacist data uctu:\n%s' % str(e))
    _fail()

def media_root(media_type):
    xbmcplugin.setContent(addon_handle, 'videos')
    use_tmdb = addon.getSetting('use_tmdb') != 'false'
    watched = _load_watched()
    valid_types = ['tvshow', 'episode'] if media_type == 'tvshow' else ['movie']
    
    if any(v.get('media_type') in valid_types for v in watched.values()):
        _add_dir('[COLOR cyan]>> Naposledy sledované[/COLOR]', _url(mode='watched_list', media_type=media_type), img='DefaultRecentlyAddedMovies.png', plot="Rychlý návrat k tomu, co jste sledovali nedávno.")

    _add_dir('Hledat', _url(mode='search_menu', search_id=media_type), img='DefaultAddonsSearch.png', plot="Přímé vyhledávání podle názvu.")
    _add_dir('Hledat podle abecedy', _url(mode='alphabet_root', media_type=media_type, prefix=''), img='DefaultMusicAlbums.png', plot="Abecední rejstřík veškerého obsahu.")

    if use_tmdb:
        _add_dir('Hledat podle žánru', _url(mode='genre_list', media_type=media_type), img='DefaultGenre.png', plot="Komedie, Drama, Sci-Fi... vyberte si podle nálady.")
        _add_dir('Hledat podle státu (CZ, SK, US...)', _url(mode='country_list', media_type=media_type), img='DefaultCountry.png', plot="Filtrování produkce podle konkrétních zemí světa.")
    _end()

def show_genre_list(media_type='movie'):
    xbmcplugin.setContent(addon_handle, 'videos')
    genres = tmdb_api.get_genres(TMDB_KEY, media_type=media_type)
    for gid, gname in sorted(genres, key=lambda g: g[1]):
        _add_dir('[B]%s[/B]' % gname, _url(mode='genre_movies', genre_id=gid, genre_name=gname, media_type=media_type))
    _end()

def show_genre_movies(genre_id, genre_name, media_type='movie', page=1):
    xbmcplugin.setContent(addon_handle, 'movies' if media_type == 'movie' else 'tvshows')
    page = int(page)
    try:
        if media_type == 'movie': results, total_pages = tmdb_api.discover_movies(TMDB_KEY, genre_id=genre_id, page=page)
        else: results, total_pages = tmdb_api.discover_tvshows(TMDB_KEY, genre_id=genre_id, page=page)
    except: results, total_pages = [], 1

    for item in results: _add_tmdb_item(item, media_type)

    if page < total_pages:
        _add_dir('[B]>> Dalsi strana (%d/%d)[/B]' % (page + 1, total_pages), _url(mode='genre_movies', genre_id=genre_id, genre_name=genre_name, media_type=media_type, page=page + 1))
    _end()

def show_country_list(media_type='movie'):
    xbmcplugin.setContent(addon_handle, 'videos')
    countries = FEATURED_COUNTRIES_MOVIE if media_type == 'movie' else FEATURED_COUNTRIES_TVSHOW
    
    # Vlastní klíč pro řazení: CZ první (0), SK druhé (1), ostatní abecedně (2)
    def sort_key(code):
        name = COUNTRY_NAMES.get(code, code)
        if code == 'CZ': return (0, name)
        if code == 'SK': return (1, name)
        return (2, name)
        
    for code in sorted(countries, key=sort_key):
        name = COUNTRY_NAMES.get(code, code)
        _add_dir('[B]%s[/B]' % name, _url(mode='country_movies', country_code=code, country_name=name, media_type=media_type))
    _end()

def show_country_movies(country_code, country_name, media_type='movie', page=1):
    xbmcplugin.setContent(addon_handle, 'movies' if media_type == 'movie' else 'tvshows')
    page = int(page)
    
    # OPRAVA 2: Voláme TMDB napřímo, abychom se vyhnuli starému souboru tmdb_api.py, který státy ignoroval
    try:
        import urllib.request, json, ssl
        ctx = ssl._create_unverified_context()
        tmdb_key_safe = 'a9d851cb36fd8287fed226766d7f01ab'
        m_type = 'movie' if media_type == 'movie' else 'tv'
        
        url = f"https://api.themoviedb.org/3/discover/{m_type}?api_key={tmdb_key_safe}&language=cs-CZ&sort_by=popularity.desc&with_origin_country={country_code}&page={page}"
        
        with urllib.request.urlopen(url, context=ctx) as r:
            data = json.loads(r.read().decode('utf-8'))
            results = data.get('results', [])
            total_pages = data.get('total_pages', 1)
    except Exception as e:
        import xbmc
        xbmc.log(f"NEXASTREAM COUNTRY ERROR: {str(e)}", xbmc.LOGERROR)
        results, total_pages = [], 1

    if not results:
        return _fail(f'Zatím nemáme nic pro stát: {country_name}')

    # VIP Radar pro obarvení tvých Trezor kousků
    try: vip_ids = _get_vip_ids()
    except: vip_ids = set()
    
    def get_pop(item):
        try: return float(item.get('popularity') or 0.0)
        except: return 0.0
        
    results.sort(key=lambda x: (0 if str(x.get('id', '')) in vip_ids else 1, -get_pop(x)))

    for item in results:
        item['tmdb_id'] = str(item.get('id', ''))
        item['year'] = (item.get('release_date') or item.get('first_air_date') or '').split('-')[0]
        item['orig_title'] = item.get('original_title') or item.get('original_name') or ''
        
        if item.get('poster_path'): item['poster'] = 'https://image.tmdb.org/t/p/w500' + item['poster_path']
        if item.get('backdrop_path'): item['backdrop'] = 'https://image.tmdb.org/t/p/w1280' + item['backdrop_path']
        
        if media_type == 'tvshow':
            item['title'] = item.get('name', '')
        else:
            item['title'] = item.get('title', '')
            
        _add_tmdb_item(item, media_type)

    if page < total_pages:
        _add_dir(f'[B]>> Další strana ({page + 1}/{total_pages})[/B]', _url(mode='country_movies', country_code=country_code, country_name=country_name, media_type=media_type, page=page + 1))
    
    _end()

def show_trending_movies():
    xbmcplugin.setContent(addon_handle, 'movies')
    try: results = tmdb_api.get_trending(TMDB_KEY, media_type='movie')
    except: results = []
    for item in results: _add_tmdb_item(item, 'movie')
    _end()

def show_popular_movies(page=1):
    xbmcplugin.setContent(addon_handle, 'movies')
    page = int(page)
    try:
        result = tmdb_api.get_popular_movies(TMDB_KEY, page=page)
        results, total = (result if isinstance(result, tuple) else (result, 1))
    except: results, total = [], 1
    for item in results: _add_tmdb_item(item, 'movie')
    if page < total:
        _add_dir('[B]>> Dalsi strana[/B]', _url(mode='popular_movies', page=page + 1))
    _end()

def _add_tmdb_item(item, media_type):
    title    = item.get('title', '')
    year     = item.get('year', '')
    plot     = item.get('plot', '')
    poster   = item.get('poster', '')
    backdrop = item.get('backdrop', '')
    tmdb_id  = str(item.get('tmdb_id', item.get('id', '')))
    orig     = item.get('orig_title', title)
    genres   = item.get('genres', [])

    year_str = ' (%s)' % year if year else ''
    
    # --- NOVÉ: Automatické obarvení našich věcí dozlatova ---
    if tmdb_id and tmdb_id in _get_vip_ids():
        label = '[COLOR gold]★ %s[/COLOR]%s' % (title, year_str)
    else:
        label = '%s%s' % (title, year_str)

    li = xbmcgui.ListItem(label)
    li.setArt({'thumb': poster, 'poster': poster, 'fanart': backdrop or poster, 'icon': poster})
    info = {
        'title': title, 'plot': plot, 'year': int(year) if year and str(year).isdigit() else 0,
        'genre': ', '.join(genres) if genres else '', 'mediatype': 'movie' if media_type == 'movie' else 'tvshow',
        'originaltitle': orig,
    }
    _set_info(li, info)

    if media_type == 'movie': url = _url(mode='select_quality', title=title, year=year, orig_title=orig, tmdb_id=tmdb_id)
    else: url = _url(mode='series_list', serial_title=title, serial_year=year, serial_original_name=orig, tmdb_id=tmdb_id)

    xbmcplugin.addDirectoryItem(addon_handle, url, li, True)

# ══════════════════════════════════════════════════════════════════════════════
#  HLEDÁNÍ A FILTERY
# ══════════════════════════════════════════════════════════════════════════════

def do_search(search_id='', query=''):
    if not query:
        # Dynamický text klávesnice
        popisek = 'dětský pořad' if search_id == 'kids' else 'seriál' if search_id == 'tvshow' else 'film' if search_id == 'movie' else 'vše (Filmy i Seriály)'
        kb = xbmc.Keyboard('', 'Hledat ' + popisek)
        kb.doModal()
        if not kb.isConfirmed() or not kb.getText().strip(): return _fail()
        query = kb.getText().strip()
    
    _save_search(query)
    use_tmdb = addon.getSetting('use_tmdb') != 'false'

    if search_id == 'tvshow':
        if use_tmdb: _search_series_with_tmdb(query)
        else: show_series_list(serial_title=query)
    elif search_id == 'movie':
        if use_tmdb: _search_movies_with_tmdb(query, page=1)
        else: _do_search_files(query, media_type='movie')
    elif search_id == 'kids':
        # NOVÉ: Hledání pouze v dětském obsahu
        if use_tmdb: _search_kids_with_tmdb(query)
        else: _do_search_files(query, media_type='movie')
    else:
        if use_tmdb: _search_multi_with_tmdb(query)
        else: _do_search_files(query, media_type='movie')

def _search_kids_with_tmdb(keyword):
    xbmcplugin.setContent(addon_handle, 'videos')
    try:
        import urllib.request, urllib.parse, json, ssl
        ctx = ssl._create_unverified_context()
        url = f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_KEY}&language=cs-CZ&query={urllib.parse.quote(keyword)}"
        with urllib.request.urlopen(url, context=ctx) as r:
            data = json.loads(r.read().decode('utf-8'))
            results = data.get('results', [])
    except Exception as e:
        results = []

    if not results:
        return _fail('V databázi TMDB nebylo nic nalezeno pro: ' + keyword)

    try: vip_ids = _get_vip_ids()
    except: vip_ids = set()

    # Filtrovat pouze na dětské žánry (16=Animovaný, 10751=Rodinný, 10762=Kids)
    kids_genres = {16, 10751, 10762}
    filtered_results = []
    
    for item in results:
        m_type = item.get('media_type', '')
        if m_type not in ['movie', 'tv']: continue
        
        item_genres = set(item.get('genre_ids', []))
        if not item_genres.intersection(kids_genres): 
            # Pokud to nemá dětský žánr, neukážeme to!
            continue
            
        filtered_results.append(item)

    if not filtered_results:
        return _fail('Nenalezena žádná pohádka pro: ' + keyword)

    # DOKONALÉ ŘAZENÍ: 1. Náš VIP Trezor, 2. Popularita
    filtered_results.sort(key=lambda x: (0 if str(x.get('id', '')) in vip_ids else 1, -x.get('popularity', 0)))

    for item in filtered_results:
        m_type = item.get('media_type', '')
        item['tmdb_id'] = str(item.get('id', ''))
        item['year'] = (item.get('release_date') or item.get('first_air_date') or '').split('-')[0]
        item['orig_title'] = item.get('original_title') or item.get('original_name') or ''
        
        if item.get('poster_path'): item['poster'] = 'https://image.tmdb.org/t/p/w500' + item['poster_path']
        if item.get('backdrop_path'): item['backdrop'] = 'https://image.tmdb.org/t/p/w1280' + item['backdrop_path']
        
        if m_type == 'tv':
            item['title'] = item.get('name', '')
            item['title'] = f"[COLOR gray][TV][/COLOR] {item['title']}"
            _add_tmdb_item(item, 'tvshow')
        else:
            item['title'] = item.get('title', '')
            _add_tmdb_item(item, 'movie')
            
    _end()

def _search_multi_with_tmdb(keyword):
    xbmcplugin.setContent(addon_handle, 'videos')
    try:
        import urllib.request, urllib.parse, json, ssl
        ctx = ssl._create_unverified_context()
        # TMDB Multi-Search Endpoint
        url = f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_KEY}&language=cs-CZ&query={urllib.parse.quote(keyword)}"
        with urllib.request.urlopen(url, context=ctx) as r:
            data = json.loads(r.read().decode('utf-8'))
            results = data.get('results', [])
    except Exception as e:
        import xbmc
        xbmc.log(f"NEXASTREAM MULTI-SEARCH ERROR: {str(e)}", xbmc.LOGERROR)
        results = []

    if not results:
        return _fail('V databázi TMDB nebylo nic nalezeno pro: ' + keyword)

    # VIP Radar i pro globální hledání
    try: vip_ids = _get_vip_ids()
    except: vip_ids = set()
    
    results.sort(key=lambda x: 0 if str(x.get('id', '')) in vip_ids else 1)

    for item in results:
        m_type = item.get('media_type', '')
        # Multi-search vrací i herce (person), ty přeskočíme
        if m_type not in ['movie', 'tv']: continue 
        
        # Sjednocení dat pro naši stávající funkci _add_tmdb_item
        item['tmdb_id'] = str(item.get('id', ''))
        item['year'] = (item.get('release_date') or item.get('first_air_date') or '').split('-')[0]
        item['orig_title'] = item.get('original_title') or item.get('original_name') or ''
        
        if item.get('poster_path'): item['poster'] = 'https://image.tmdb.org/t/p/w500' + item['poster_path']
        if item.get('backdrop_path'): item['backdrop'] = 'https://image.tmdb.org/t/p/w1280' + item['backdrop_path']
        
        if m_type == 'tv':
            item['title'] = item.get('name', '')
            # Odlišení seriálu v mixovaném seznamu
            item['title'] = f"[COLOR gray][TV][/COLOR] {item['title']}"
            _add_tmdb_item(item, 'tvshow')
        else:
            item['title'] = item.get('title', '')
            _add_tmdb_item(item, 'movie')
            
    _end()

def _search_series_with_tmdb(keyword):
    xbmcplugin.setContent(addon_handle, 'tvshows')
    try:
        raw = tmdb_api.search_tvshows(TMDB_KEY, keyword)
        results = (raw[0] if isinstance(raw, tuple) else raw)
    except: results = []

    if not results: return show_series_list(serial_title=keyword)
    
    # --- NOVÉ: Seřazení - Naše seriály jdou jako první! ---
    vip_ids = _get_vip_ids()
    results.sort(key=lambda x: 0 if str(x.get('id', x.get('tmdb_id', ''))) in vip_ids else 1)

    for item in results: _add_tmdb_item(item, 'tvshow')
    _end()

def _search_movies_with_tmdb(keyword, page=1):
    xbmcplugin.setContent(addon_handle, 'movies')
    page = int(page)
    try:
        raw = tmdb_api.search_movies(TMDB_KEY, keyword, page=page)
        results, total_pages = (raw if isinstance(raw, tuple) else (raw, 1))
    except: 
        results, total_pages = [], 1

    if not results: 
        return _fail('V TMDB nebyl nalezen film: ' + keyword)
    
    # Seřazení: Náš VIP Trezor má přednost
    try: vip_ids = _get_vip_ids()
    except: vip_ids = set()
    results.sort(key=lambda x: 0 if str(x.get('id', x.get('tmdb_id', ''))) in vip_ids else 1)

    for item in results: 
        _add_tmdb_item(item, 'movie')
        
    if page < total_pages:
        _add_dir(f'[B]>> Další strana ({page + 1}/{total_pages})[/B]', _url(mode='search_more', keyword=keyword, search_id='movie', page=page + 1))
    _end()

def search_more(keyword, search_id='movie', page=1):
    if search_id == 'movie': _search_movies_with_tmdb(keyword, page=int(page))
    else: do_search(search_id=search_id, query=keyword)

def _do_search_files(query, media_type='movie'):
    token = _get_token()
    if not token: return _fail()
    
    poster, backdrop = '', ''
    if addon.getSetting('use_tmdb') != 'false':
        try:
            tmdb_results = tmdb_api.search_movies(TMDB_KEY, query)
            if tmdb_results and isinstance(tmdb_results, tuple): tmdb_results = tmdb_results[0]
            if tmdb_results and len(tmdb_results) > 0:
                best = tmdb_results[0]
                poster, backdrop = best.get('poster', ''), best.get('backdrop', '')
        except: pass

    prog = xbmcgui.DialogProgress()
    prog.create('NexaStream', 'Hledani: %s' % query)
    try: files = webshare.search_for_title(token, query)
    except: files = []
    finally: prog.close()

    if not files: return _fail('Zadne vysledky pro: %s' % query)
    xbmcplugin.setContent(addon_handle, 'movies' if media_type == 'movie' else 'tvshows')
    _show_file_items(files, media_type=media_type, poster=poster, backdrop=backdrop)
    _end()

def _show_file_items(files, media_type='movie', poster='', backdrop='', orig_title='', year=''):
    grouped = {}
    for f in files:
        base = re.sub(QUALITY_PATTERN, '', f['name'], flags=re.I)
        base = re.sub(r'[._]', ' ', base)
        base = re.sub(r'\s+', ' ', base).strip()
        grouped.setdefault(base, []).append(f)

    for base_title, variants in sorted(grouped.items()):
        if len(variants) == 1:
            _add_video_item(variants[0], media_type, show_quality=False, poster=poster, backdrop=backdrop, orig_title=orig_title, year=year)
        else:
            li = xbmcgui.ListItem('[B]%s[/B]  [I](%d verzi)[/I]' % (base_title, len(variants)))
            if poster: li.setArt({'thumb': poster, 'poster': poster, 'fanart': backdrop or poster})
            xbmcplugin.addDirectoryItem(addon_handle,
                _url(mode='quality_select',
                     variants=json.dumps([{
                         'name': v['name'], 'ident': v['ident'],
                         'size': v.get('size_str', ''), 'size_b': str(v.get('size', 0)),
                         'positive': str(v.get('positive', 0)), 'negative': str(v.get('negative', 0)),
                         'desc': v.get('desc', ''),
                     } for v in variants]),
                     media_type=media_type, poster=poster, backdrop=backdrop, orig_title=orig_title, year=year),
                li, True)

def show_quality_select(variants_json, media_type='movie', poster='', backdrop='', orig_title='', year=''):
    xbmcplugin.setContent(addon_handle, 'videos')
    try: variants = json.loads(variants_json)
    except: variants = []
    def _mb(v):
        try: return int(v.get('size_b', 0))
        except: return 0
    for v in sorted(variants, key=_mb, reverse=True):
        _add_video_item(v, media_type, show_quality=True, poster=poster, backdrop=backdrop, orig_title=orig_title, year=year)
    _end()

def _add_video_item(f, media_type, show_quality=False, poster='', backdrop='', orig_title='', year=''):
    name  = f.get('name', f.get('title', ''))
    ident = f.get('ident', '')
    size  = f.get('size_str', f.get('size', ''))
    plus  = f.get('positive', 0)
    minus = f.get('negative', 0)
    
    real_title = f.get('real_title', '')
    info_str = f.get('info_str', '')
    
    # --- OČISTA NÁZVU PRO ULOŽENÍ DO HISTORIE A PŘEHRÁVAČE ---
    if real_title:
        # Pevně spojený název filmu s informací o kvalitě, bez textu VIP
        clean_title = "★ " + real_title + " " + info_str
    else:
        clean_title = re.sub(r'\[/?(?:COLOR|B|I)[^\]]*\]', '', name, flags=re.I)
        clean_title = clean_title.replace('[]', '').replace('>>', '').strip()
        clean_title = re.sub(r'^(?:TREZOR:\s*)+', '', clean_title).strip()
        if not clean_title: clean_title = orig_title or "Neznámý titul"
    # ---------------------------------------------

    if "★" in name or ">>" in name or show_quality: label = name
    else: label = re.sub(r'\s+', ' ', re.sub(QUALITY_PATTERN, '', name, flags=re.I)).strip()
    
    # K našim luxusním odkazům už velikost nepřipisujeme na konec (máme ji uprostřed v závorce)
    if "★" not in name:
        label += '  [I][%s][/I]' % size

    li = xbmcgui.ListItem(label)
    li.setProperty('IsPlayable', 'true')
    if poster: li.setArt({'thumb': poster, 'poster': poster, 'fanart': backdrop or poster})
    
    info = {
        'title': clean_title, 'originaltitle': orig_title if orig_title else clean_title, 'year': year,
        'plot': 'Velikost: %s  |  +%s -%s' % (size, plus, minus), 'mediatype': 'movie' if media_type == 'movie' else 'episode'
    }

    watched = _load_watched()
    w_data = watched.get(ident, {})
    if w_data:
        if w_data.get('playcount', 0) >= 1: info['playcount'] = 1
        elif w_data.get('resume_time', 0) > 0:
            li.setProperty('ResumeTime', str(w_data['resume_time']))
            if w_data.get('total_time'): li.setProperty('TotalTime', str(w_data['total_time']))

    _set_info(li, info)
    li.addContextMenuItems([
        ('Označit jako Zhlédnuté', 'RunPlugin(%s)' % _url(mode='add_watched', ident=ident, title=clean_title, size=size, media_type=media_type)),
        ('Přidat do knihovny Kodi (STRM)', 'RunPlugin(%s)' % _url(mode='export_strm', ident=ident, title=clean_title, media_type=media_type))
    ])
    
    xbmcplugin.addDirectoryItem(addon_handle, _url(mode='play', ident=ident, title=clean_title, media_type=media_type, size=size), li, False)

# ══════════════════════════════════════════════════════════════════════════════
#  VÝBĚR KVALITY FILMY A SERIÁLY
# ══════════════════════════════════════════════════════════════════════════════

def select_quality(title, year='', orig_title='', tmdb_id=''):
    token = _get_token()
    if not token: return _fail()
    xbmcplugin.setContent(addon_handle, 'movies')

    poster, backdrop = '', ''
    if tmdb_id and TMDB_KEY:
        try:
            det = tmdb_api.get_movie_details(TMDB_KEY, tmdb_id)
            poster, backdrop = det.get('poster', ''), det.get('backdrop', '')
        except: pass

    nase_ciste_linky = False

    # --- CHYTRÁ VÝHYBKA A (Máme vlastní film z DB) ---
    if tmdb_id:
        try:
            trezor_res = _check_trezor(tmdb_id)
            for t_item in trezor_res:
                if int(t_item.get('season', 0)) == 0:
                    ident = t_item['link'].strip('/').split('/')[-1]
                    info_str = str(t_item.get('info', ''))
                    velikost = str(t_item.get('size', '---'))
                    
                    # Čistý název bez slova VIP, s barevně odlišenou velikostí a metadaty
                    lbl = f"[COLOR gold]★ {title}[/COLOR] [COLOR gray][{velikost}][/COLOR] {info_str}"
                    
                    _add_video_item({'name': lbl, 'ident': ident, 'size_str': velikost, 'real_title': title, 'info_str': info_str}, 'movie', show_quality=True, poster=poster, backdrop=backdrop, orig_title=orig_title, year=year)
                    nase_ciste_linky = True
        except: pass

    # ZÁSADNÍ KROK: Pokud jsme vypsali prémiové linky, UKONČÍME hledání!
    if nase_ciste_linky:
        _end()
        return

    # --- CHYTRÁ VÝHYBKA B (Nemáme vlastní link, spustí se veřejný Webshare) ---
    prog = xbmcgui.DialogProgress()
    prog.create('NexaStream', 'Hledani: %s' % title)
    try: files = webshare.search_for_title(token, title, year=year, original_title=orig_title)
    except: files = []
    finally: prog.close()

    if not files:
        try: files = webshare.search_for_title(token, title, year=year, original_title=orig_title)
        except: files = []

    if files: 
        _show_file_items(files, media_type='movie', poster=poster, backdrop=backdrop, orig_title=orig_title, year=year)
    elif not nase_ciste_linky:
        li = xbmcgui.ListItem('[COLOR red]Neni k dispozici: %s[/COLOR]' % title)
        xbmcplugin.addDirectoryItem(addon_handle, '', li, False)
    _end()

def show_series_list(serial_title, serial_year='', serial_original_name='', tmdb_id='', num_seasons=0):
    xbmcplugin.setContent(addon_handle, 'tvshows')
    use_tmdb = addon.getSetting('use_tmdb') != 'false'
    num_seasons = int(num_seasons) if num_seasons else 0

    if use_tmdb and not (tmdb_id and num_seasons):
        orig, cz = serial_original_name or serial_title, serial_title
        for query in [orig, cz]:
            try:
                results = tmdb_api.search_tvshows(TMDB_KEY, query)
                if isinstance(results, tuple): results = results[0]
                if results:
                    best = results[0]
                    tmdb_id = best.get('tmdb_id', best.get('id', ''))
                    if tmdb_id:
                        det = tmdb_api.get_tvshow_details(TMDB_KEY, tmdb_id)
                        if det:
                            num_seasons = det.get('seasons', det.get('number_of_seasons', 0))
                            if det.get('orig_title'): serial_original_name = det['orig_title']
                if tmdb_id and num_seasons: break
            except: pass

    if use_tmdb and tmdb_id and num_seasons: found_seasons = list(range(1, int(num_seasons) + 1))
    else:
        token = _get_token()
        if not token: return _fail()
        found_set = set()
        search_queries = []
        if serial_original_name: search_queries.append('%s S01' % serial_original_name)
        if serial_title and _norm(serial_title) != _norm(serial_original_name or ''): search_queries.append('%s S01' % serial_title)
        prog = xbmcgui.DialogProgress()
        prog.create('NexaStream', 'Detekuji serie: %s' % serial_title)
        try:
            for q in search_queries:
                try:
                    for f in webshare._raw_search(token, q, limit=50):
                        if f.get('season'): found_set.add(f['season'])
                except: pass
            max_s = max(found_set) if found_set else 0
            search_base = serial_original_name or serial_title
            for s in range(1, max_s + 3):
                if s in found_set: continue
                try:
                    for f in webshare._raw_search(token, '%s S%02d' % (search_base, s), limit=20):
                        if f.get('season'): found_set.add(f['season'])
                except: pass
        finally: prog.close()
        found_seasons = sorted(found_set)

    if not found_seasons: return _fail('Serial nenalezen: %s' % serial_title)

    poster = ''
    if tmdb_id and TMDB_KEY:
        try:
            det = tmdb_api.get_tvshow_details(TMDB_KEY, tmdb_id)
            poster = det.get('poster', '') if det else ''
        except: pass

    for s in found_seasons:
        li = xbmcgui.ListItem('[B]Serie %d[/B]' % s)
        if poster: li.setArt({'thumb': poster, 'poster': poster, 'fanart': poster})
        xbmcplugin.addDirectoryItem(addon_handle, _url(mode='episodes', serial_title=serial_title, serial_original_name=serial_original_name, serial_year=serial_year, tmdb_id=tmdb_id, season=s), li, True)
    _end()

def show_episodes(serial_title, season, serial_year='', serial_original_name='', tmdb_id=''):
    xbmcplugin.setContent(addon_handle, 'episodes')
    season = int(season)
    token = _get_token()
    if not token: return _fail()

    orig_name, cz_name = serial_original_name or serial_title, serial_title
    items, existing = [], set()

    vip_episodes = {}
    if tmdb_id:
        trezor_results = _check_trezor(tmdb_id)
        for t_item in trezor_results:
            if int(t_item.get('season', 0)) == season:
                vip_episodes[int(t_item.get('episode', 0))] = t_item

    def _merge(new_items):
        for ni in new_items:
            if ni['ident'] not in existing:
                items.append(ni); existing.add(ni['ident'])

    prog = xbmcgui.DialogProgress()
    prog.create('NexaStream', 'Nacitam serie %d: %s' % (season, cz_name or orig_name))
    try:
        q1 = '%s S%02d' % (orig_name, season)
        _merge(webshare._raw_search(token, q1, limit=50))
        if cz_name and _norm(cz_name) != _norm(orig_name): _merge(webshare._raw_search(token, '%s S%02d' % (cz_name, season), limit=50))
        kw_en = _extract_keyword(orig_name)
        if kw_en and len(kw_en) > 4: _merge(webshare._raw_search(token, '%s S%02d' % (kw_en, season), limit=30))
        kw_cz = _extract_keyword(cz_name) if cz_name else ''
        if kw_cz and len(kw_cz) > 4 and _norm(kw_cz) != _norm(kw_en): _merge(webshare._raw_search(token, '%s S%02d' % (kw_cz, season), limit=30))
    except: pass
    finally: prog.close()

    filtered = _filter_season(items, season, serial_title=cz_name, serial_original_name=orig_name)
    groups = _group_by_episode(filtered)

    for vip_ep_num in vip_episodes.keys():
        if vip_ep_num not in groups: groups[vip_ep_num] = []

    if not groups: return _fail('Zadne epizody pro: %s S%02d' % (cz_name, season))

    ep_names, ep_plots = {}, {}
    if addon.getSetting('use_tmdb') != 'false' and tmdb_id and TMDB_KEY:
        try:
            season_data = tmdb_api.get_tv_season(TMDB_KEY, tmdb_id, season)
            for ep in (season_data.get('episodes') or []):
                n = ep.get('episode_number')
                if n is not None:
                    ep_names[n] = ep.get('name', '')
                    ep_plots[n] = ep.get('overview', '')
        except: pass

    for ep_num in sorted(groups.keys()):
        variants = groups[ep_num]
        ep_label = 'S%02dE%02d' % (season, ep_num)
        ep_name  = ep_names.get(ep_num, '')
        ep_plot  = ep_plots.get(ep_num, '')

        folder_title = ('[B]%s  %s[/B]' % (ep_label, ep_name) if ep_name else '[B]%s[/B]' % ep_label)
        if ep_num in vip_episodes: folder_title = "[COLOR gold]★ " + folder_title + "[/COLOR]"

        li = xbmcgui.ListItem(folder_title)
        _set_info(li, {'title': '%s - %s' % (ep_label, ep_name) if ep_name else ep_label, 'season': season, 'episode': ep_num, 'plot': ep_plot or '', 'mediatype': 'episode', 'originaltitle': orig_name})
        xbmcplugin.addDirectoryItem(addon_handle, _url(mode='episode_variants', variants=json.dumps([{'name': v['name'], 'ident': v['ident'], 'size': v.get('size_str', ''), 'size_b': str(v.get('size', 0)), 'positive': str(v.get('positive', 0)), 'negative': str(v.get('negative', 0)), 'desc': v.get('desc', ''),} for v in variants]), tmdb_id=tmdb_id, season=season, ep_num=ep_num, ep_name=ep_name, ep_plot=ep_plot, orig_title=orig_name), li, True)
    _end()

def show_episode_variants(variants_json, season, ep_num, ep_name='', ep_plot='', orig_title='', tmdb_id=''):
    xbmcplugin.setContent(addon_handle, 'episodes')
    season, ep_num = int(season), int(ep_num)

    nase_ciste_linky = []

    # 1. KROK: Dotaz do tvé databáze
    if tmdb_id:
        try:
            trezor_results = _check_trezor(tmdb_id)
            for t_item in trezor_results:
                if int(t_item.get('season', 0)) == season and int(t_item.get('episode', 0)) == ep_num:
                    nase_ciste_linky.append(t_item)
        except: pass

    # --- CHYTRÁ VÝHYBKA A (Máme vlastní linky z DB) ---
    if nase_ciste_linky:
        for t_item in nase_ciste_linky:
            ident = t_item['link'].strip('/').split('/')[-1]
            info_str = str(t_item.get('info', ''))
            velikost = str(t_item.get('size', ''))
            
            # Čistý název bez slova VIP, zato s barevně odlišenou velikostí a metadaty
            ep_disp = (orig_title or "Epizoda") + " S%02dE%02d" % (season, ep_num)
            lbl = f"[COLOR gold]★ {ep_disp}[/COLOR] [COLOR gray][{velikost}][/COLOR] {info_str}"
            
            li = xbmcgui.ListItem(lbl)
            li.setProperty('IsPlayable', 'true')
            
            # Propojení s historií zhlédnutí
            watched = _load_watched()
            w_data = watched.get(ident, {})
            if w_data:
                if w_data.get('playcount', 0) >= 1: li.setInfo('video', {'playcount': 1})
                elif w_data.get('resume_time', 0) > 0: li.setProperty('ResumeTime', str(w_data['resume_time']))

            _set_info(li, {'title': ep_disp, 'season': season, 'episode': ep_num, 'plot': ep_plot, 'mediatype': 'episode'})
            li.addContextMenuItems([('Označit jako Zhlédnuté', 'RunPlugin(%s)' % _url(mode='add_watched', ident=ident, title=ep_disp, size=velikost, media_type='episode'))])
            
            xbmcplugin.addDirectoryItem(addon_handle, _url(mode='play', ident=ident, title=ep_disp, media_type='episode', size=velikost), li, False)
        
        # ZÁSADNÍ KROK: Ukončíme vykreslování! Veřejný Webshare se vůbec nespustí.
        _end()
        return 

    # --- CHYTRÁ VÝHYBKA B (Nemáme vlastní linky, použijeme veřejný Webshare) ---
    try: variants = json.loads(variants_json)
    except: variants = []

    for v in variants:
        name, ident, size = v.get('name', ''), v.get('ident', ''), v.get('size', '')
        li = xbmcgui.ListItem(name)
        li.setProperty('IsPlayable', 'true')
        info = {'title': name, 'originaltitle': orig_title, 'season': season, 'episode': ep_num, 'plot': ep_plot, 'mediatype': 'episode'}

        watched = _load_watched()
        w_data = watched.get(ident, {})
        if w_data:
            if w_data.get('playcount', 0) >= 1: info['playcount'] = 1
            elif w_data.get('resume_time', 0) > 0: li.setProperty('ResumeTime', str(w_data['resume_time']))

        _set_info(li, info)
        li.addContextMenuItems([('Označit jako Zhlédnuté', 'RunPlugin(%s)' % _url(mode='add_watched', ident=ident, title=name, size=size, media_type='episode')), ('Exportovat do knihovny (STRM)', 'RunPlugin(%s)' % _url(mode='export_strm', ident=ident, title=orig_title or name, media_type='episode', season=season, episode=ep_num))])
        xbmcplugin.addDirectoryItem(addon_handle, _url(mode='play', ident=ident, title=name, media_type='episode', size=size), li, False)
    
    _end()

def _filter_season(files, season, serial_title='', serial_original_name=''):
    import unicodedata
    def _norm_title(s):
        try:
            n = unicodedata.normalize('NFD', s or '')
            return re.sub(r'\s+', ' ', re.sub(r'[._\-]', ' ', ''.join(c for c in n if unicodedata.category(c) != 'Mn'))).lower().strip()
        except: return (s or '').lower().strip()

    def _title_ok(filename):
        fn = _norm_title(filename)
        for t in [serial_original_name, serial_title]:
            if not t: continue
            nt = _norm_title(t)
            if nt and nt in fn: return True
            words = [w for w in nt.split() if len(w) > 2]
            if words:
                hits = sum(1 for w in words if re.search(r'\b' + re.escape(w) + r'\b', fn))
                if len(words) == 1 and hits == 1: return True
                if len(words) == 2 and hits == 2: return True
                if len(words) > 2 and hits / float(len(words)) >= 0.85: return True
        return not (serial_title or serial_original_name)

    result = []
    for f in files:
        fs = f.get('season')
        fe = f.get('episode')
        name = f.get('name', '')
        season_ok = False
        if fs is not None:
            if fs == season and fe is not None: season_ok = True
        else:
            m = re.search(r'(?i)[Ss](\d{1,2})[Ee]\d{1,2}', name)
            if m and int(m.group(1)) == season: season_ok = True
            else:
                m = re.search(r'\b(\d{1,2})[xX](\d{2})\b', name)
                if m and int(m.group(1)) == season: season_ok = True
        if not season_ok: continue
        if not _title_ok(name): continue
        result.append(f)
    return result

def _group_by_episode(files):
    groups = {}
    for f in files:
        ep = f.get('episode')
        if ep is None:
            name = f.get('name', '')
            m = re.search(r'(?i)[Ss]\d{1,2}[Ee](\d{1,2})', name)
            if m: ep = int(m.group(1))
            else:
                m = re.search(r'\b\d{1,2}[xX](\d{2})\b', name)
                ep = int(m.group(1)) if m else 0
        groups.setdefault(int(ep), []).append(f)
    for ep in groups: groups[ep].sort(key=lambda x: (x.get('quality_rank', 99), -x.get('size', 0)))
    return groups

def _extract_keyword(title):
    words = [w for w in re.split(r'\W+', title) if len(w) > 3]
    return max(words, key=len) if words else ''

def alphabet_root(prefix='', media_type='movie'):
    xbmcplugin.setContent(addon_handle, 'videos')
    if prefix:
        _add_dir('[COLOR orange]🔎 Vyhledat vše co začíná na "%s"[/COLOR]' % prefix, _url(mode='alphabet_search', prefix=prefix, media_type=media_type))
        letters = list('ABCDEFGHIJKLMNOPQRSTUVWXYZ')
    else: letters = (list('ABCDEFGHIJKLMNOPQRSTUVWXYZ') + [u'\xc1',u'\u010c',u'\u010e',u'\xc9',u'\u011a',u'\xcd',u'\u0147',u'\xd3',u'\u0158',u'\u0160',u'\u0164',u'\xda',u'\u016e',u'\xdd',u'\u017d'] + list('0123456789'))
        
    for letter in letters:
        new_prefix = prefix + letter
        _add_dir('[B]%s[/B]' % new_prefix, _url(mode='alphabet_root', prefix=new_prefix, media_type=media_type))
    _end()

def alphabet_search(prefix, media_type='movie'):
    if addon.getSetting('use_tmdb') != 'false':
        if media_type == 'tvshow': _search_series_with_tmdb(prefix)
        else: _search_movies_with_tmdb(prefix, page=1)
    else: _do_search_files(prefix, media_type=media_type)

def show_watched_list(media_type='movie'):
    xbmcplugin.setContent(addon_handle, 'videos')
    watched = _load_watched()
    valid_types = ['tvshow', 'episode'] if media_type == 'tvshow' else ['movie']
    items = {k: v for k, v in watched.items() if v.get('media_type') in valid_types}

    if not items: return _fail('Zadne sledovane polozky')

    for ident, data in sorted(items.items(), key=lambda i: i[1]['time'], reverse=True):
        raw_title = data.get('title', '')
        
        # --- ZPĚTNÁ OPRAVA HISTORIE A FORMÁTOVÁNÍ ---
        clean_title = re.sub(r'\[/?(?:COLOR|B|I)[^\]]*\]', '', raw_title, flags=re.I)
        clean_title = clean_title.replace('[]', '').replace('>>', '').strip()
        clean_title = re.sub(r'^(?:TREZOR:\s*)+', '', clean_title).strip()

        is_vip = "★ VIP" in clean_title or "TREZOR" in raw_title

        if "★ VIP:" in clean_title:
            clean_title = clean_title.replace("★ VIP:", "").strip()

        if not clean_title: clean_title = "Neznámý titul"

        size_str = data.get('size', '')
        size_label = '  [I][%s][/I]' % size_str if size_str else ''

        if is_vip:
            label = '[COLOR gold]★ VIP: %s[/COLOR]%s' % (clean_title, size_label)
        else:
            label = '%s%s' % (clean_title, size_label)

        li = xbmcgui.ListItem(label)
        li.setProperty('IsPlayable', 'true')
        if data.get('img'): li.setArt({'thumb': data['img']})
        
        if data.get('playcount', 0) >= 1: li.setInfo('video', {'playcount': 1})
        elif data.get('resume_time', 0) > 0:
            li.setProperty('ResumeTime', str(data['resume_time']))
            if data.get('total_time'): li.setProperty('TotalTime', str(data['total_time']))

        li.addContextMenuItems([('Odebrat ze Zhlednutych', 'RunPlugin(%s)' % _url(mode='remove_watched', ident=ident))])
        xbmcplugin.addDirectoryItem(addon_handle, _url(mode='play', ident=ident, title=clean_title, media_type=data.get('media_type', 'movie'), size=size_str), li, False)
    _end()



def show_kids_in_progress():
    xbmcplugin.setContent(addon_handle, 'videos')
    watched = _load_watched()
    
    # NOVÉ: Vyfiltruje POUZE tituly s dětským štítkem!
    in_progress = {k: v for k, v in watched.items() if v.get('resume_time', 0) > 0 and v.get('playcount', 0) == 0 and v.get('is_kids') == 'true'}

    if not in_progress:
        return _fail('Zatím nemáte v Dětském světě nic rozkoukáno.')

    for ident, data in sorted(in_progress.items(), key=lambda i: i[1]['time'], reverse=True):
        raw_title = data.get('title', '')
        clean_title = re.sub(r'\[/?(?:COLOR|B|I)[^\]]*\]', '', raw_title, flags=re.I).replace('[]', '').replace('>>', '').strip()
        clean_title = re.sub(r'^(?:TREZOR:\s*)+', '', clean_title).strip()
        is_vip = "★ VIP" in clean_title or "TREZOR" in raw_title
        if "★ VIP:" in clean_title: clean_title = clean_title.replace("★ VIP:", "").strip()
        if not clean_title: clean_title = "Neznámý titul"

        size_str = data.get('size', '')
        size_label = '  [I][%s][/I]' % size_str if size_str else ''

        if is_vip: label = '[COLOR orange]►[/COLOR] [COLOR gold]★ VIP: %s[/COLOR]%s' % (clean_title, size_label)
        else: label = '[COLOR orange]►[/COLOR] %s%s' % (clean_title, size_label)

        li = xbmcgui.ListItem(label)
        li.setProperty('IsPlayable', 'true')
        if data.get('img'): li.setArt({'thumb': data['img']})
        li.setProperty('ResumeTime', str(data['resume_time']))
        if data.get('total_time'): li.setProperty('TotalTime', str(data['total_time']))

        _set_info(li, {'title': clean_title, 'mediatype': data.get('media_type', 'movie')})
        li.addContextMenuItems([('Odebrat z historie', 'RunPlugin(%s)' % _url(mode='remove_watched', ident=ident))])
        xbmcplugin.addDirectoryItem(addon_handle, _url(mode='play', ident=ident, title=clean_title, media_type=data.get('media_type', 'movie'), size=size_str), li, False)
    
    _end()

def play_file(ident, title='', media_type='movie', size='', is_kids='false'):
    token = _load_token()
    if not token: token = addon.getSetting('token') 
    if not token: return
    link = webshare.get_file_link(token, ident)

    if not link:
        _notify('Nelze ziskat odkaz na stream.', xbmcgui.NOTIFICATION_ERROR)
        xbmcplugin.setResolvedUrl(addon_handle, False, xbmcgui.ListItem())
        return

    li = xbmcgui.ListItem(title, path=link)
    li.setProperty('IsPlayable', 'true')
    ext = (title or '').lower().rsplit('.', 1)[-1]
    mime_map = {'mkv': 'video/x-matroska', 'mp4': 'video/mp4', 'avi': 'video/avi'}
    li.setMimeType(mime_map.get(ext, 'video/x-matroska'))
    
    xbmcplugin.setResolvedUrl(addon_handle, True, li)
    
    player = SCCPlayer(ident, title, media_type=media_type, size=size, is_kids=is_kids)    
    monitor = xbmc.Monitor()
    
    for _ in range(20):
        if player.isPlaying(): break
        xbmc.sleep(500)
        
    while not monitor.abortRequested() and player.isPlaying():
        try:
            player.last_time = player.getTime()
            player.last_total = player.getTotalTime()
        except: pass
        xbmc.sleep(1000)

# ══════════════════════════════════════════════════════════════════════════════
#  KOLEKCE & NETFLIX
# ══════════════════════════════════════════════════════════════════════════════

def collections_root():
    xbmcplugin.setContent(addon_handle, 'videos')
    
    # Seznam nejpopulárnějších kolekcí (Název, TMDB ID Kolekce)
    kolekce = [
        ('Harry Potter', 1241),
        ('Pán prstenů', 119),
        ('Star Wars', 10),
        ('Marvel: Avengers', 86311),
        ('Piráti z Karibiku', 295),
        ('Rychle a zběsile', 9485),
        ('James Bond', 645),
        ('Matrix', 2344),
        ('Jurský park', 328),
        ('Vetřelec', 8091),
        ('Doba ledová', 8353),
        ('Shrek', 2150)
    ]
    
    import os
    addon_path = addon.getAddonInfo('path')
    if hasattr(addon_path, 'decode'): addon_path = addon_path.decode('utf-8')
    bg_vychozi = os.path.join(addon_path, 'fanart', 'bg_vychozi.jpg')

    for name, coll_id in kolekce:
        _add_dir('[B]%s[/B]' % name, _url(mode='show_collection', coll_id=coll_id), img='DefaultMovies.png', fanart=bg_vychozi)
    _end()
# ==========================================
# DEFINICE VOD SLUŽEB (ID a LOGA)
# ==========================================
# ID providerů pro region CZ z TMDB
VOD_PROVIDERS = {
    'netflix': {
        'name': 'Netflix',
        'id': '8',
        # Vysoce kvalitní PNG logo na tmavém pozadí pro Kodi
        'logo': 'https://upload.wikimedia.org/wikipedia/commons/thumb/0/08/Netflix_2015_logo.svg/512px-Netflix_2015_logo.svg.png'
    },
    'hbo': {
        'name': 'HBO Max',
        'id': '1899', # ID pro Max
        'logo': 'https://upload.wikimedia.org/wikipedia/commons/thumb/1/17/HBO_Max_Logo.svg/512px-HBO_Max_Logo.svg.png'
    },
    'disney': {
        'name': 'Disney+',
        'id': '337',
        'logo': 'https://upload.wikimedia.org/wikipedia/commons/thumb/3/3e/Disney%2B_logo.svg/512px-Disney%2B_logo.svg.png'
    },
    'voyo': {
        'name': 'Voyo',
        'id': '376', # ID Voyo CZ
        'logo': 'https://upload.wikimedia.org/wikipedia/commons/thumb/a/a2/Voyo_logo.svg/512px-Voyo_logo.svg.png'
    },
    'apple': {
        'name': 'Apple TV+',
        'id': '350',
        'logo': 'https://upload.wikimedia.org/wikipedia/commons/thumb/2/28/Apple_TV_Plus_Logo.svg/512px-Apple_TV_Plus_Logo.svg.png'
    },
    'prime': {
        'name': 'Prime Video',
        'id': '119',
        'logo': 'https://upload.wikimedia.org/wikipedia/commons/thumb/1/11/Amazon_Prime_Video_logo.svg/512px-Amazon_Prime_Video_logo.svg.png'
    },
     'skyshowtime': {
        'name': 'SkyShowtime',
        'id': '1796',
        'logo': 'https://upload.wikimedia.org/wikipedia/commons/thumb/3/30/SkyShowtime_logo.svg/512px-SkyShowtime_logo.svg.png'
    }
}
def show_collection(coll_id):
    xbmcplugin.setContent(addon_handle, 'movies')
    prog = xbmcgui.DialogProgress()
    prog.create('NexaStream', 'Načítám kolekci...')
    try:
        import urllib.request, json, ssl
        url = "https://api.themoviedb.org/3/collection/%s?api_key=%s&language=cs-CZ" % (coll_id, TMDB_KEY)
        ctx = ssl._create_unverified_context()
        with urllib.request.urlopen(url, context=ctx) as r:
            data = json.loads(r.read().decode('utf-8'))
            parts = data.get('parts', [])
            # Automaticky seřadíme filmy od nejstaršího po nejnovější díl
            parts.sort(key=lambda x: x.get('release_date', '9999'))
            for part in parts:
                # Očista a překlad surových dat z TMDB
                norm_item = {
                    'title': part.get('title', ''),
                    'orig_title': part.get('original_title', ''),
                    'year': part.get('release_date', '')[:4] if part.get('release_date') else '',
                    'plot': part.get('overview', ''),
                    'poster': 'https://image.tmdb.org/t/p/w500' + part['poster_path'] if part.get('poster_path') else '',
                    'backdrop': 'https://image.tmdb.org/t/p/w1280' + part['backdrop_path'] if part.get('backdrop_path') else '',
                    'tmdb_id': part.get('id', '')
                }
                _add_tmdb_item(norm_item, 'movie')
    except: pass
    finally: prog.close()
    _end()

def show_netflix():
    xbmcplugin.setContent(addon_handle, 'tvshows')
    prog = xbmcgui.DialogProgress()
    prog.create('NexaStream', 'Načítám Netflix...')
    try:
        import urllib.request, json, ssl
        # 213 je oficiální ID sítě Netflix na TMDB
        url = "https://api.themoviedb.org/3/discover/tv?api_key=%s&language=cs-CZ&with_networks=213&sort_by=popularity.desc" % TMDB_KEY
        ctx = ssl._create_unverified_context()
        with urllib.request.urlopen(url, context=ctx) as r:
            data = json.loads(r.read().decode('utf-8'))
            for item in data.get('results', []):
                # Seriály mají místo "title" v databázi "name"
                norm_item = {
                    'title': item.get('name', ''),
                    'orig_title': item.get('original_name', ''),
                    'year': item.get('first_air_date', '')[:4] if item.get('first_air_date') else '',
                    'plot': item.get('overview', ''),
                    'poster': 'https://image.tmdb.org/t/p/w500' + item['poster_path'] if item.get('poster_path') else '',
                    'backdrop': 'https://image.tmdb.org/t/p/w1280' + item['backdrop_path'] if item.get('backdrop_path') else '',
                    'tmdb_id': item.get('id', '')
                }
                _add_tmdb_item(norm_item, 'tvshow')
    except: pass
    finally: prog.close()
    _end()

def show_active_series(is_kids='false'):
    xbmcplugin.setContent(addon_handle, 'tvshows')
    watched = _load_watched()
    active_shows = {}
    
    for ident, data in watched.items():
        item_is_kids = data.get('is_kids', 'false')
        if is_kids == 'true' and item_is_kids != 'true': continue
        if is_kids == 'false' and item_is_kids == 'true': continue
        
        raw_title = data.get('title', '')
        clean_title = re.sub(r'\[/?(?:COLOR|B|I)[^\]]*\]', '', raw_title, flags=re.I).replace('[]', '').replace('>>', '').strip()
        clean_title = re.sub(r'^(?:TREZOR:\s*)+', '', clean_title).strip()
        clean_title = clean_title.replace("★ VIP:", "").replace("★", "").strip()
        
        m = re.search(r'(?i)(.*?)\s+S\d{1,2}E\d{1,2}', clean_title)
        if m or data.get('media_type') == 'episode':
            show_name = m.group(1).strip() if m else clean_title
            if not show_name: continue
            
            t = data.get('time', 0)
            if show_name not in active_shows or t > active_shows[show_name]['time']:
                active_shows[show_name] = {'time': t, 'img': data.get('img', 'DefaultTVShows.png')}
                
    if not active_shows:
        return _fail('Zatím nemáte rozezkoukaný žádný seriál v této kategorii.')
        
    for show_name, s_data in sorted(active_shows.items(), key=lambda x: x[1]['time'], reverse=True):
        li = xbmcgui.ListItem(f"[B]{show_name}[/B]")
        if s_data['img']: li.setArt({'thumb': s_data['img'], 'icon': s_data['img']})
        url = _url(mode='do_search', search_id='tvshow', query=show_name)
        xbmcplugin.addDirectoryItem(addon_handle, url, li, True)
        
    _end()

# =========================================================================
# HLAVNÍ ROUTER (Spouštěč)
# ========================================================================

def router(params):
    mode = params.get('mode')
    
    if   mode is None:                 main_menu()
    elif mode == 'movies_menu':        movies_menu()
    elif mode == 'shows_menu':         shows_menu()
    elif mode == 'kids_world_menu':    kids_world_menu()
    elif mode == 'placeholder_msg':
        import xbmcgui
        xbmcgui.Dialog().ok("NexaStream", f"Pracujeme na tom!\n\nSložka '{params.get('msg', '')}' bude přidána v další aktualizaci.")
    elif mode == 'export_strm':        export_to_strm(params.get('ident', ''), params.get('title', ''), params.get('media_type', 'movie'), params.get('season', ''), params.get('episode', ''))
    elif mode == 'in_progress_list':   show_in_progress_list()
    elif mode == 'play':               play_file(params.get('ident', ''), params.get('title', ''), params.get('media_type', 'movie'), params.get('size', ''), is_kids=params.get('is_kids', 'false'))    
    elif mode == 'add_watched':        watched_add(params.get('ident', ''), params.get('title', ''), params.get('size', ''), media_type=params.get('media_type', 'movie'))
    elif mode == 'remove_watched':     watched_remove(params.get('ident', ''))
    elif mode == 'media_root':         media_root(params.get('media_type', 'movie'))
    elif mode == 'search_menu':        search_menu(params.get('search_id', ''), params.get('is_kids', 'false'))    
    elif mode == 'do_search':          do_search(params.get('search_id', ''), params.get('query', ''))
    elif mode == 'clear_search_history': clear_search_history()
    elif mode == 'search_more':        search_more(params.get('keyword', ''), params.get('search_id', 'movie'), int(params.get('page', 1)))
    elif mode == 'genre_list':         show_genre_list(params.get('media_type', 'movie'))
    elif mode == 'genre_movies':       show_genre_movies(params.get('genre_id', ''), params.get('genre_name', ''), params.get('media_type', 'movie'), int(params.get('page', 1)))
    elif mode == 'country_list':       show_country_list(params.get('media_type', 'movie'))
    elif mode == 'country_movies':     show_country_movies(params.get('country_code', ''), params.get('country_name', ''), params.get('media_type', 'movie'), int(params.get('page', 1)))
    elif mode == 'trending_movies':    show_trending_movies()
    elif mode == 'popular_movies':     show_popular_movies(int(params.get('page', 1)))
    elif mode == 'select_quality':     select_quality(params.get('title', ''), params.get('year', ''), params.get('orig_title', ''), params.get('tmdb_id', ''))
    elif mode == 'quality_select':     show_quality_select(params.get('variants', '[]'), params.get('media_type', 'movie'), params.get('poster', ''), params.get('backdrop', ''), params.get('orig_title', ''), params.get('year', ''))
    elif mode == 'series_list':        show_series_list(params.get('serial_title', ''), params.get('serial_year', ''), params.get('serial_original_name', ''), params.get('tmdb_id', ''), params.get('num_seasons', 0))
    elif mode == 'episodes':           show_episodes(params.get('serial_title', ''), params.get('season', 1), params.get('serial_year', ''), params.get('serial_original_name', ''), params.get('tmdb_id', ''))
    elif mode == 'episode_variants':   show_episode_variants(params.get('variants', '[]'), params.get('season', 1), params.get('ep_num', 1), params.get('ep_name', ''), params.get('ep_plot', ''), params.get('orig_title', ''), params.get('tmdb_id', ''))
    elif mode == 'alphabet_root':      alphabet_root(params.get('prefix', ''), params.get('media_type', 'movie'))
    elif mode == 'alphabet_search':    alphabet_search(params.get('prefix', 'A'), params.get('media_type', 'movie'))
    elif mode == 'watched_list':       show_watched_list(params.get('media_type', 'movie'))
    elif mode == 'account_info':       show_account_info()
    elif mode == 'do_login':           do_login()
    elif mode == 'active_series':      show_active_series(params.get('is_kids', 'false'))
    elif mode == 'settings':           addon.openSettings(); _fail()
    
    # --- VIP UZAMČENÉ SEKCE ---
    elif mode == 'trezor_list':
        if not check_vip_access(): return
        show_trezor_list(params.get('api_mode', 'latest'), params.get('title', 'Trezor'))
        
    elif mode == 'collections_root':
        if not check_vip_access(): return
        collections_root()
        
    elif mode == 'show_collection':
        if not check_vip_access(): return
        show_collection(params.get('coll_id', ''))
        
    elif mode == 'show_netflix':
        if not check_vip_access(): return
        show_netflix()

    elif mode == 'vip_info':
        show_support_info()

    # -------------------------------------------------------------------------
    # HANDLER: Rozcestník pro novinky v Trezoru
    # -------------------------------------------------------------------------
    elif mode == 'trezor_latest_menu':
        import sys, xbmcplugin
        _add_dir('[COLOR FFD946EF][B]Nově nahrané Filmy[/B][/COLOR]', _url(mode='trezor_list', api_mode='movies', title='Filmy'), img='DefaultMovies.png')
        _add_dir('[COLOR FFD946EF][B]Nově nahrané Seriály[/B][/COLOR]', _url(mode='trezor_list', api_mode='shows', title='Seriály'), img='DefaultTVShows.png')
        _add_dir('[COLOR FF0EA5E9][B]Pouze CZ Dabing (Trezor)[/B][/COLOR]', _url(mode='trezor_list', api_mode='cz_only', title='CZ Dabing'), img='DefaultVideo.png')
        xbmcplugin.endOfDirectory(int(sys.argv[1]))

   # -------------------------------------------------------------------------
    # HANDLER: Dětský svět (Rozcestník)
    # -------------------------------------------------------------------------
    elif mode == 'kids_world':
        import sys, xbmcplugin
        current_handle = int(sys.argv[1])
        
        # MÍŘÍ NA NOVOU DĚTSKOU HISTORII
        _add_dir('[COLOR orange]>>Pokračovat ve sledování (V půlce)[/COLOR]', _url(mode='kids_in_progress'), img='DefaultVideo.png', plot="Návrat k vašim rozezkoukaným pohádkám. Žádné filmy pro dospělé zde nenajdete.")
        _add_dir('[COLOR cyan][B]Naše rozkoukané seriály (Další díl)[/B][/COLOR]', _url(mode='active_series', is_kids='true'), img='DefaultTVShows.png', plot="Složka se seriály (Tlapková patrola atd.), na které teď koukáte. Ušetří zdlouhavé hledání dalšího dílu.")        
        # PŘIDÁN TAJNÝ ŠTÍTEK is_kids='true'
        _add_dir('[B]Hledat pohádku[/B]', _url(mode='search_menu', search_id='kids', is_kids='true'), img='DefaultAddonsSearch.png', plot="Vyhledávač s filtrem výhradně na dětské seriály a rodinné filmy.")        
        _add_dir('[COLOR FF10B981][B]Populární Dětské Filmy[/B][/COLOR]', _url(mode='kids_discover', m_type='movie', is_kids='true'), img='DefaultMovies.png', plot="Ledové království, Shrek, Mimoni a další hity. Tituly z VIP Trezoru jsou umístěny na prvních místech.")
        _add_dir('[COLOR FF10B981][B]Populární Dětské Seriály[/B][/COLOR]', _url(mode='kids_discover', m_type='tv', is_kids='true'), img='DefaultTVShows.png', plot="Tlapková patrola, Prasátko Peppa, Kačeří příběhy... Seřazeno přesně podle světové popularity.")
        
# --- NOVÉ: ČESKÉ VEČERNÍČKY ---
        _add_dir('[COLOR FF10B981][B]České Večerníčky a seriály[/B][/COLOR]', _url(mode='kids_vecernicky'), img='DefaultTVShows.png', plot="Zlatý fond českých a slovenských večerníčků a animovaných seriálů.")
        
        # --- NOVÉ: ČESKÉ FILMOVÉ POHÁDKY ---
        _add_dir('[COLOR FF10B981][B]České filmové pohádky[/B][/COLOR]', _url(mode='kids_cz_movies'), img='DefaultMovies.png', plot="S čerty nejsou žerty, Tři oříšky pro Popelku, Obušku z pytle ven a další filmové klasiky.")        
        xbmcplugin.endOfDirectory(current_handle)
        
    elif mode == 'kids_in_progress':
        show_kids_in_progress()

    # -------------------------------------------------------------------------
    # HANDLER: České Večerníčky (Funkce pro načtení z TMDB)
    # -------------------------------------------------------------------------
    elif mode == 'kids_vecernicky':
        try:
            import sys, urllib.parse, urllib.request, json, ssl, xbmcplugin
            current_handle = int(sys.argv[1])
            params = dict(urllib.parse.parse_qsl(sys.argv[2][1:]))
            page = int(params.get('page', 1))
            tmdb_key = 'a9d851cb36fd8287fed226766d7f01ab'
            ctx = ssl._create_unverified_context()
            
            # API dotaz: Pouze CZ/SK, řazeno od nejlépe hodnocených, minimálně 5 hlasů (odstraní amatérský balast)
            url = f"https://api.themoviedb.org/3/discover/tv?api_key={tmdb_key}&language=cs-CZ&sort_by=vote_average.desc&vote_count.gte=5&with_genres=16,10762&with_origin_country=CZ|SK&page={page}"
            
            with urllib.request.urlopen(url, context=ctx) as r:
                data = json.loads(r.read().decode('utf-8'))
                results = data.get('results', [])
                total_pages = data.get('total_pages', 1)
                
            try: vip_ids = _get_vip_ids()
            except: vip_ids = set()
            
            def get_vote(item):
                try: return float(item.get('vote_average') or 0.0)
                except: return 0.0
                
            # Seřazení: VIP hity nahoru, zbytek podle hodnocení (nejlepší první)
            results.sort(key=lambda x: (0 if str(x.get('id', '')) in vip_ids else 1, -get_vote(x)))
            
            for item in results:
                title = item.get('name', '')
                orig_title = item.get('original_name') or title
                year = (item.get('first_air_date') or '').split('-')[0]
                tmdb_id = str(item.get('id', ''))
                
                try: rating = f"{float(item.get('vote_average', 0)):.1f}"
                except: rating = "0.0"
                
                poster = "https://image.tmdb.org/t/p/w500" + item['poster_path'] if item.get('poster_path') else 'DefaultVideo.png'
                
                if tmdb_id in vip_ids:
                    base_label = f"[COLOR gold]★[/COLOR] [{rating}] [COLOR gold][B]{title}[/B][/COLOR]"
                else:
                    base_label = f"[{rating}] {title}"
                
                label = f"[COLOR gray][TV][/COLOR] {base_label}"
                _add_dir(label, _url(mode='series_list', tmdb_id=tmdb_id, serial_title=title, serial_original_name=orig_title, serial_year=year), img=poster)
                
            if page < total_pages:
                _add_dir(f'[B]>> Další strana ({page + 1}/{total_pages})[/B]', _url(mode='kids_vecernicky', page=page + 1))
                
            xbmcplugin.endOfDirectory(current_handle)
        except Exception as e:
            import xbmc
            xbmc.log(f"NEXASTREAM VECERNICKY ERROR: {str(e)}", xbmc.LOGERROR)

    # -------------------------------------------------------------------------
    # HANDLER: Dětský svět - Discover (Oprava Asie + České Večerníčky)
    # -------------------------------------------------------------------------
    elif mode == 'kids_discover':
        try:
            import sys, urllib.parse, urllib.request, json, ssl, xbmcplugin
            current_handle = int(sys.argv[1])
            params = dict(urllib.parse.parse_qsl(sys.argv[2][1:]))
            m_type = params.get('m_type', 'movie')
            
            tmdb_key = 'a9d851cb36fd8287fed226766d7f01ab'
            ctx = ssl._create_unverified_context()
            
            # Žánry: 16 (Animovaný), 10751 (Rodinný) a pro seriály 10762 (Kids)
            genres = '16,10751' if m_type == 'movie' else '16,10762'
            
            # Stáhneme dvě dávky, abychom měli jistotu, že tam budou české věci
            # 1. Globální hity (Disney, Pixar, Nickelodeon)
            url_global = f"https://api.themoviedb.org/3/discover/{m_type}?api_key={tmdb_key}&language=cs-CZ&sort_by=popularity.desc&with_genres={genres}&page=1"
            # 2. České a Slovenské hity (Večerníčky, Krteček, Pat a Mat...)
            url_cz = f"https://api.themoviedb.org/3/discover/{m_type}?api_key={tmdb_key}&language=cs-CZ&sort_by=popularity.desc&with_genres={genres}&with_origin_country=CZ|SK&page=1"
            
            results = []
            seen_ids = set()
            
            # Sloučíme obě stahování dohromady
            for url in [url_cz, url_global]:
                try:
                    with urllib.request.urlopen(url, context=ctx) as r:
                        data = json.loads(r.read().decode('utf-8'))
                        for item in data.get('results', []):
                            
                            # 🚫 FILTR: Vyřadíme japonské (Anime), čínské a korejské nesmysly
                            lang = item.get('original_language', '')
                            if lang in ['ja', 'zh', 'ko', 'cn']: 
                                continue
                            
                            t_id = str(item.get('id', ''))
                            if t_id and t_id not in seen_ids:
                                results.append(item)
                                seen_ids.add(t_id)
                except: pass
                
            try: vip_ids = _get_vip_ids()
            except: vip_ids = set()
            
            # ALGORITMUS ŘAZENÍ: Prvně VIP Trezor, poté podle klesající TMDB popularity
            results.sort(key=lambda x: (0 if str(x.get('id', '')) in vip_ids else 1, -x.get('popularity', 0)))
            
            for item in results:
                title = item.get('title') or item.get('name', '')
                orig_title = item.get('original_title') or item.get('original_name') or title
                year = (item.get('release_date') or item.get('first_air_date') or '').split('-')[0]
                tmdb_id = str(item.get('id', ''))
                
                # Bezpečné zaokrouhlení na 1 desetinné místo (např. 8.0 místo 7.963)
                try: rating = f"{float(item.get('vote_average', 0)):.1f}"
                except: rating = "0.0"
                
                poster = "https://image.tmdb.org/t/p/w500" + item['poster_path'] if item.get('poster_path') else 'DefaultVideo.png'
                
                if tmdb_id in vip_ids:
                    base_label = f"[COLOR gold]★[/COLOR] [{rating}] [COLOR gold][B]{title}[/B][/COLOR]"
                else:
                    base_label = f"[{rating}] {title}"
                
                if m_type == 'movie':
                    _add_dir(base_label, _url(mode='select_quality', tmdb_id=tmdb_id, title=title, orig_title=orig_title, year=year), img=poster)
                else:
                    label = f"[COLOR gray][TV][/COLOR] {base_label}"
                    _add_dir(label, _url(mode='series_list', tmdb_id=tmdb_id, serial_title=title, serial_original_name=orig_title, serial_year=year), img=poster)
                    
            xbmcplugin.endOfDirectory(current_handle)
        except Exception as e:
            import xbmc
            xbmc.log(f"NEXASTREAM KIDS ERROR: {str(e)}", xbmc.LOGERROR)
# -------------------------------------------------------------------------
    # HANDLER: České filmové pohádky (Nová sekce pro CZ/SK filmy)
    # -------------------------------------------------------------------------
    elif mode == 'kids_cz_movies':
        try:
            import sys, urllib.parse, urllib.request, json, ssl, xbmcplugin
            current_handle = int(sys.argv[1])
            params = dict(urllib.parse.parse_qsl(sys.argv[2][1:]))
            page = int(params.get('page', 1))
            tmdb_key = 'a9d851cb36fd8287fed226766d7f01ab'
            ctx = ssl._create_unverified_context()
            
            # API dotaz: Filmy, žánr 10751 (Rodinný), orig. jazyk CS nebo SK, řazeno podle hodnocení, min 15 hlasů
            url = f"https://api.themoviedb.org/3/discover/movie?api_key={tmdb_key}&language=cs-CZ&sort_by=vote_average.desc&vote_count.gte=15&with_genres=10751&with_original_language=cs|sk&page={page}"
            
            with urllib.request.urlopen(url, context=ctx) as r:
                data = json.loads(r.read().decode('utf-8'))
                results = data.get('results', [])
                total_pages = data.get('total_pages', 1)
                
            try: vip_ids = _get_vip_ids()
            except: vip_ids = set()
            
            def get_vote(item):
                try: return float(item.get('vote_average') or 0.0)
                except: return 0.0
                
            # Seřazení: VIP hity nahoru, zbytek podle hodnocení
            results.sort(key=lambda x: (0 if str(x.get('id', '')) in vip_ids else 1, -get_vote(x)))
            
            for item in results:
                title = item.get('title', '')
                orig_title = item.get('original_title') or title
                year = (item.get('release_date') or '').split('-')[0]
                tmdb_id = str(item.get('id', ''))
                
                try: rating = f"{float(item.get('vote_average', 0)):.1f}"
                except: rating = "0.0"
                
                poster = "https://image.tmdb.org/t/p/w500" + item['poster_path'] if item.get('poster_path') else 'DefaultMovies.png'
                
                if tmdb_id in vip_ids:
                    base_label = f"[COLOR gold]★[/COLOR] [{rating}] [COLOR gold][B]{title}[/B][/COLOR]"
                else:
                    base_label = f"[{rating}] {title}"
                
                _add_dir(base_label, _url(mode='select_quality', tmdb_id=tmdb_id, title=title, orig_title=orig_title, year=year), img=poster)
                
            if page < total_pages:
                _add_dir(f'[B]>> Další strana ({page + 1}/{total_pages})[/B]', _url(mode='kids_cz_movies', page=page + 1))
                
            xbmcplugin.endOfDirectory(current_handle)
        except Exception as e:
            import xbmc
            xbmc.log(f"NEXASTREAM CZ POHADKY ERROR: {str(e)}", xbmc.LOGERROR)

# -------------------------------------------------------------------------
    # HANDLER 1: DYNAMICKÁ SLOŽKA VOD SLUŽEB (Čistá prémiová šestice)
    # -------------------------------------------------------------------------
    elif mode == 'show_vod_menu':
        try:
            import sys, urllib.request, json, ssl, xbmcplugin
            current_handle = int(sys.argv[1])
            tmdb_key = 'a9d851cb36fd8287fed226766d7f01ab'
            ctx = ssl._create_unverified_context()
            
            all_providers = []
            
            # Stáhneme aktuální data služeb pro CZ region
            for m_type in ['movie', 'tv']:
                url = f"https://api.themoviedb.org/3/watch/providers/{m_type}?api_key={tmdb_key}&language=cs-CZ&watch_region=CZ"
                try:
                    with urllib.request.urlopen(url, context=ctx) as r:
                        all_providers.extend(json.loads(r.read().decode('utf-8')).get('results', []))
                except: pass
                
            wanted = ['netflix', 'max', 'disney', 'apple', 'prime', 'skyshowtime', 'hbo']
            final_list = {}
            
            for prov in all_providers:
                p_name = prov.get('provider_name', '')
                p_id = str(prov.get('provider_id', ''))
                logo = prov.get('logo_path', '')
                p_lower = p_name.lower()
                
                # Ignorujeme placené půjčovny
                if 'store' in p_lower: continue
                
                # Sjednocení a pročištění názvů
                if 'hbo' in p_lower or p_lower == 'max': p_name = 'HBO Max'
                if 'apple' in p_lower: p_name = 'Apple TV+'
                
                for w in wanted:
                    if w in p_lower and p_name not in final_list:
                        full_logo = f"https://image.tmdb.org/t/p/w500{logo}" if logo else 'DefaultTVShows.png'
                        final_list[p_name] = {'id': p_id, 'name': p_name, 'logo': full_logo}
                        break

            # Vykreslení menu (automaticky seřazené abecedně)
            for p_name in sorted(final_list.keys()):
                data = final_list[p_name]
                _add_dir(f"[B]{data['name']}[/B]", _url(mode='discover_vod', provider_id=data['id']), img=data['logo'])
                
            xbmcplugin.endOfDirectory(current_handle)
            
        except Exception as e:
            import xbmc, xbmcgui
            xbmc.log(f"NEXASTREAM VOD MENU ERROR: {str(e)}", xbmc.LOGERROR)

    # -------------------------------------------------------------------------
    # HANDLER 2: DISCOVER OBSAHU (Mix Filmy + Seriály)
    # -------------------------------------------------------------------------
    elif mode == 'discover_vod':
        try:
            import sys, urllib.parse, urllib.request, json, ssl, xbmcplugin, xbmcgui
            
            current_handle = int(sys.argv[1])
            params = dict(urllib.parse.parse_qsl(sys.argv[2][1:]))
            provider_id = params.get('provider_id', '')
            
            if not provider_id:
                sys.exit()

            tmdb_key = 'a9d851cb36fd8287fed226766d7f01ab'
            ctx = ssl._create_unverified_context()
            all_results = []
            
            # Poptáme filmy i seriály na dané službě
            for m_type in ['movie', 'tv']:
                url = f"https://api.themoviedb.org/3/discover/{m_type}?api_key={tmdb_key}&language=cs-CZ&sort_by=popularity.desc&watch_region=CZ&with_watch_providers={provider_id}"
                try:
                    with urllib.request.urlopen(url, context=ctx) as r:
                        data = json.loads(r.read().decode('utf-8'))
                        for item in data.get('results', []):
                            item['media_type'] = m_type
                            all_results.append(item)
                except: pass
                
            # Sloučíme a seřadíme od nejpopulárnějšího z obou kategorií
            all_results.sort(key=lambda x: x.get('popularity', 0), reverse=True)
            
            if not all_results:
                xbmcgui.Dialog().notification('NexaStream', 'Obsah nenalezen.', xbmcgui.NOTIFICATION_INFO)
            
            try: vip_ids = _get_vip_ids()
            except: vip_ids = set()
            
            for item in all_results:
                title = item.get('title') or item.get('name', '')
                orig_title = item.get('original_title') or item.get('original_name') or title
                year = (item.get('release_date') or item.get('first_air_date') or '').split('-')[0]
                tmdb_id = str(item.get('id', ''))
                m_type = item.get('media_type', 'movie')
                
                try: rating = round(float(item.get('vote_average', 0)), 1) if item.get('vote_average') else 0.0
                except: rating = 0.0
                
                poster = "https://image.tmdb.org/t/p/w500" + item['poster_path'] if item.get('poster_path') else 'DefaultVideo.png'
                
                # Zlatá úprava pro VIP obsah
                if tmdb_id in vip_ids:
                    base_label = f"[COLOR gold]★[/COLOR] [{rating}] [COLOR gold][B]{title}[/B][/COLOR]"
                else:
                    base_label = f"[{rating}] {title}"
                
                # Výhybka pro spuštění (Seriály dostanou šedý štítek [TV])
                if m_type == 'movie':
                    _add_dir(base_label, _url(mode='select_quality', tmdb_id=tmdb_id, title=title, orig_title=orig_title, year=year), img=poster)
                else:
                    label = f"[COLOR gray][TV][/COLOR] {base_label}"
                    _add_dir(label, _url(mode='series_list', tmdb_id=tmdb_id, serial_title=title, serial_original_name=orig_title, serial_year=year), img=poster)
                    
            xbmcplugin.endOfDirectory(current_handle)
            
        except Exception as e:
            import xbmc, xbmcgui
            xbmc.log(f"NEXASTREAM VOD ERROR: {str(e)}", xbmc.LOGERROR)
    else:                              main_menu()

if __name__ == '__main__':
    router(dict(parse_qsl(sys.argv[2][1:])))