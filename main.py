from flask import Flask, request, jsonify
from flask_cors import CORS
import swisseph as swe
from datetime import date, datetime
import os

app = Flask(__name__)
CORS(app)

swe.set_ephe_path('/usr/share/ephe')

PLANETS = {
    'Sun': swe.SUN, 'Moon': swe.MOON, 'Mercury': swe.MERCURY,
    'Venus': swe.VENUS, 'Mars': swe.MARS, 'Jupiter': swe.JUPITER,
    'Saturn': swe.SATURN, 'Uranus': swe.URANUS, 'Neptune': swe.NEPTUNE,
    'Pluto': swe.PLUTO,
}
SIGN_NAMES = ['Aries','Taurus','Gemini','Cancer','Leo','Virgo',
              'Libra','Scorpio','Sagittarius','Capricorn','Aquarius','Pisces']
PLANET_SYMBOL = {
    'Sun':'☉','Moon':'☽','Mercury':'☿','Venus':'♀','Mars':'♂',
    'Jupiter':'♃','Saturn':'♄','Uranus':'♅','Neptune':'♆','Pluto':'♇',
}
PLANET_COLOR = {
    'Jupiter':{'bg':'rgba(93,184,160,0.15)','color':'#5db8a0'},
    'Saturn':{'bg':'rgba(139,127,212,0.15)','color':'#8b7fd4'},
    'Mars':{'bg':'rgba(212,149,90,0.15)','color':'#d4955a'},
    'Venus':{'bg':'rgba(196,125,142,0.15)','color':'#c47d8e'},
    'Neptune':{'bg':'rgba(93,120,184,0.15)','color':'#5d78b8'},
    'Pluto':{'bg':'rgba(139,127,212,0.1)','color':'#6b5fb0'},
    'Uranus':{'bg':'rgba(93,184,160,0.1)','color':'#3d9e88'},
    'Sun':{'bg':'rgba(201,169,110,0.15)','color':'#c9a96e'},
    'Mercury':{'bg':'rgba(180,178,169,0.15)','color':'#b4b2a9'},
    'Moon':{'bg':'rgba(232,230,240,0.1)','color':'#8b8aaa'},
}
AREA_MAP = {
    ('Jupiter','conjunction'):['career','finances','inner growth'],
    ('Jupiter','trine'):['career','finances','relationships'],
    ('Jupiter','opposition'):['inner growth','relationships'],
    ('Jupiter','square'):['inner growth'],
    ('Jupiter','sextile'):['finances','career'],
    ('Saturn','conjunction'):['career','inner growth'],
    ('Saturn','trine'):['career','inner growth'],
    ('Saturn','opposition'):['inner growth','relationships'],
    ('Saturn','square'):['inner growth','career'],
    ('Saturn','sextile'):['career'],
    ('Mars','conjunction'):['career','inner growth'],
    ('Mars','opposition'):['relationships','inner growth'],
    ('Mars','square'):['inner growth'],
    ('Mars','trine'):['career','finances'],
    ('Venus','conjunction'):['relationships','finances'],
    ('Venus','trine'):['relationships','finances'],
    ('Venus','opposition'):['relationships'],
    ('Venus','square'):['relationships','inner growth'],
    ('Neptune','conjunction'):['inner growth'],
    ('Neptune','square'):['inner growth'],
    ('Neptune','trine'):['inner growth','relationships'],
    ('Pluto','conjunction'):['career','inner growth'],
    ('Pluto','trine'):['career','inner growth','finances'],
    ('Pluto','square'):['inner growth'],
    ('Uranus','conjunction'):['career','inner growth'],
    ('Uranus','opposition'):['relationships','inner growth'],
    ('Uranus','trine'):['career','finances'],
    ('Uranus','square'):['inner growth'],
}
PLANET_WEIGHT = {
    'Pluto':5,'Neptune':4,'Uranus':4,'Saturn':5,'Jupiter':4,
    'Mars':3,'Sun':2,'Venus':2,'Mercury':2,'Moon':1,
}
ASPECTS = [
    {'name':'conjunction','target':0,'orb':8},
    {'name':'opposition','target':180,'orb':8},
    {'name':'trine','target':120,'orb':7},
    {'name':'square','target':90,'orb':7},
    {'name':'sextile','target':60,'orb':5},
]

# For /events — only outer/slow planets hitting natal key points
EVENT_TRANSIT_PLANETS = ['Pluto','Neptune','Uranus','Saturn','Jupiter']
EVENT_NATAL_POINTS = ['Sun','Moon','Venus','Mars','Mercury','Ascendant','Midheaven','Saturn','Jupiter']
# Only the most significant aspect types for life events
EVENT_ASPECTS = [
    {'name':'conjunction','target':0,'orb':5},
    {'name':'opposition','target':180,'orb':5},
    {'name':'square','target':90,'orb':5},
    {'name':'trine','target':120,'orb':4},
]
# Score weight for ranking (transit planet x natal point)
EVENT_SCORE = {
    'Pluto': 10, 'Neptune': 8, 'Uranus': 8, 'Saturn': 7, 'Jupiter': 5,
}
EVENT_NATAL_SCORE = {
    'Sun': 5, 'Moon': 5, 'Ascendant': 5, 'Midheaven': 4,
    'Venus': 3, 'Mars': 3, 'Saturn': 3, 'Jupiter': 2, 'Mercury': 1,
}
EVENT_ASPECT_SCORE = {
    'conjunction': 5, 'opposition': 4, 'square': 4, 'trine': 3,
}

def date_to_jd(y, m, d, h=12.0):
    return swe.julday(y, m, d, h)

def get_pos(jd, pid):
    return swe.calc_ut(jd, pid)[0][0]

def lon_to_sign(lon):
    idx = int(lon / 30) % 12
    deg = lon % 30
    return SIGN_NAMES[idx], round(deg, 1)

def angle_diff(a, b):
    d = abs(a - b) % 360
    return 360 - d if d > 180 else d

def check_aspect(tlon, nlon):
    diff = angle_diff(tlon, nlon)
    for asp in ASPECTS:
        ao = abs(diff - asp['target'])
        if ao <= asp['orb']:
            return asp['name'], ao
    return None, None

def check_event_aspect(tlon, nlon):
    diff = angle_diff(tlon, nlon)
    for asp in EVENT_ASPECTS:
        ao = abs(diff - asp['target'])
        if ao <= asp['orb']:
            return asp['name'], ao
    return None, None

def find_window(t_id, n_lon, asp_target, start_jd, days=180):
    orb = 8
    s = peak_jd = e = None
    peak_orb = 999
    for i in range(days):
        jd = start_jd + i
        diff = angle_diff(get_pos(jd, t_id), n_lon)
        ao = abs(diff - asp_target)
        if ao <= orb:
            if s is None: s = jd
            if ao < peak_orb: peak_orb = ao; peak_jd = jd
            e = jd
    return s, peak_jd, e

def fmt_range(s, e, p=None):
    if not s: return None
    ms = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
    def jd2d(jd):
        y,m,d,_ = swe.revjul(jd)
        return date(y, m, int(d))
    sd, ed = jd2d(s), jd2d(e)
    if sd.month == ed.month and sd.year == ed.year:
        r = f"{ms[sd.month-1]} {sd.day}–{ed.day}, {sd.year}"
    elif sd.year == ed.year:
        r = f"{ms[sd.month-1]} {sd.day} – {ms[ed.month-1]} {ed.day}, {sd.year}"
    else:
        r = f"{ms[sd.month-1]} {sd.day}, {sd.year} – {ms[ed.month-1]} {ed.day}, {ed.year}"
    if p:
        pd = jd2d(p)
        r += f" (peak {ms[pd.month-1]} {pd.day})"
    return r

def jd_to_year_float(jd):
    y, m, d, _ = swe.revjul(jd)
    return y + (m - 1) / 12 + (d - 1) / 365.25

def jd_to_date(jd):
    y, m, d, _ = swe.revjul(jd)
    return date(y, m, int(d))

def calc_natal(birth, overrides=None):
    h = birth.get('hour', 12.0)
    jd = date_to_jd(birth['year'], birth['month'], birth['day'], h)
    natal = {}
    for name, pid in PLANETS.items():
        natal[name] = get_pos(jd, pid)

    houses_data = None
    if birth.get('lat') and birth.get('lon') and h != 12.0:
        cusps, ascmc = swe.houses(jd, birth['lat'], birth['lon'], b'P')
        natal['Ascendant'] = ascmc[0]
        natal['Midheaven'] = ascmc[1]
        houses_data = list(cusps)

    if overrides:
        for point, sign in overrides.items():
            if sign and sign in SIGN_NAMES:
                base = SIGN_NAMES.index(sign) * 30
                if point in natal:
                    natal[point] = base + (natal[point] % 30)
                else:
                    natal[point] = base + 15

    return natal, jd, houses_data

def calc_natal_aspects(natal):
    ASPECT_COLORS = {
        'conjunction': '#c9a96e', 'trine': '#5db8a0',
        'sextile': '#8b7fd4', 'square': '#c47d8e', 'opposition': '#d4955a',
    }
    planets = ['Sun','Moon','Mercury','Venus','Mars','Jupiter','Saturn','Uranus','Neptune','Pluto']
    aspects = []
    for i, p1 in enumerate(planets):
        for p2 in planets[i+1:]:
            if p1 not in natal or p2 not in natal:
                continue
            asp_name, orb = check_aspect(natal[p1], natal[p2])
            if asp_name and asp_name in ['conjunction','trine','sextile','square','opposition']:
                aspects.append({
                    'p1': p1, 'p2': p2, 'aspect': asp_name,
                    'orb': round(orb, 1),
                    'color': ASPECT_COLORS.get(asp_name, '#888'),
                    'lon1': natal[p1], 'lon2': natal[p2],
                })
    return aspects

def get_transits(natal, start_jd):
    skip = {'Moon', 'Sun', 'Mercury'}
    transit_planets = [p for p in PLANETS if p not in skip]
    results = []
    for t_name in transit_planets:
        t_id = PLANETS[t_name]
        for n_name, n_lon in natal.items():
            if n_name in skip: continue
            cur_lon = get_pos(start_jd, t_id)
            asp_name, orb_val = check_aspect(cur_lon, n_lon)
            if not asp_name: continue
            asp_target = next(a['target'] for a in ASPECTS if a['name'] == asp_name)
            sw, pw, ew = find_window(t_id, n_lon, asp_target, start_jd - 30, 180)
            if not sw: continue
            date_str = fmt_range(sw, ew, pw)
            intensity = min(5, PLANET_WEIGHT.get(t_name, 2) + (1 if orb_val < 2 else 0))
            t_sign, _ = lon_to_sign(cur_lon)
            n_sign, _ = lon_to_sign(n_lon)
            colors = PLANET_COLOR.get(t_name, {'bg':'rgba(180,178,169,0.15)','color':'#b4b2a9'})
            results.append({
                'id': f"{t_name.lower()}-{asp_name[:3]}-{n_name.lower().replace(' ','')}",
                'planet': PLANET_SYMBOL.get(t_name, t_name[0]),
                'symbol': t_name,
                'bg': colors['bg'],
                'color': colors['color'],
                'name': f"{t_name} {asp_name} natal {n_name}",
                'aspect': asp_name,
                'natal': n_name,
                'date': date_str,
                'intensity': intensity,
                'areas': AREA_MAP.get((t_name, asp_name), ['inner growth']),
                'transitSign': t_sign,
                'natalSign': n_sign,
                'orbDeg': round(orb_val, 1),
            })
    results.sort(key=lambda x: (-x['intensity'], -PLANET_WEIGHT.get(x['symbol'], 0)))
    return results[:8]


def get_life_events(natal, birth_year):
    """
    Scan 1990–2030 (or birth_year+5 whichever is later) for the top 15
    most significant slow-planet transits to natal key points.
    Uses monthly sampling for speed, then refines peak date.
    """
    today = date.today()
    today_jd = date_to_jd(today.year, today.month, today.day)

    scan_start_year = max(1990, birth_year + 5)
    scan_end_year = 2031
    start_jd = date_to_jd(scan_start_year, 1, 1)
    end_jd = date_to_jd(scan_end_year, 1, 1)

    candidates = []
    seen = set()  # deduplicate by (transit_planet, natal_point, aspect)

    for t_name in EVENT_TRANSIT_PLANETS:
        t_id = PLANETS[t_name]

        for n_name in EVENT_NATAL_POINTS:
            if n_name not in natal:
                continue
            n_lon = natal[n_name]

            # Sample every 14 days for speed
            jd = start_jd
            in_aspect = False
            asp_start_jd = None
            asp_peak_jd = None
            asp_peak_orb = 999
            current_asp = None

            while jd <= end_jd:
                t_lon = get_pos(jd, t_id)
                asp_name, orb_val = check_event_aspect(t_lon, n_lon)

                if asp_name:
                    if not in_aspect or asp_name != current_asp:
                        # New aspect window starting
                        if in_aspect and current_asp:
                            # Save previous
                            key = (t_name, n_name, current_asp, int(asp_peak_jd / 365))
                            if key not in seen:
                                seen.add(key)
                                score = (EVENT_SCORE.get(t_name, 3) +
                                         EVENT_NATAL_SCORE.get(n_name, 1) +
                                         EVENT_ASPECT_SCORE.get(current_asp, 2))
                                t_sign, t_deg = lon_to_sign(get_pos(asp_peak_jd, t_id))
                                n_sign, n_deg = lon_to_sign(n_lon)
                                peak_date = jd_to_date(asp_peak_jd)
                                is_past = asp_peak_jd < today_jd
                                colors = PLANET_COLOR.get(t_name, {'bg':'rgba(180,178,169,0.15)','color':'#b4b2a9'})
                                candidates.append({
                                    'transitPlanet': t_name,
                                    'natalPoint': n_name,
                                    'aspect': current_asp,
                                    'peakDate': peak_date.isoformat(),
                                    'peakYear': peak_date.year,
                                    'score': score,
                                    'isPast': is_past,
                                    'transitSign': t_sign,
                                    'natalSign': n_sign,
                                    'symbol': PLANET_SYMBOL.get(t_name, t_name[0]),
                                    'bg': colors['bg'],
                                    'color': colors['color'],
                                    'name': f"{t_name} {current_asp} natal {n_name}",
                                })
                        in_aspect = True
                        asp_start_jd = jd
                        asp_peak_jd = jd
                        asp_peak_orb = orb_val
                        current_asp = asp_name
                    else:
                        if orb_val < asp_peak_orb:
                            asp_peak_orb = orb_val
                            asp_peak_jd = jd
                else:
                    if in_aspect and current_asp:
                        key = (t_name, n_name, current_asp, int(asp_peak_jd / 365))
                        if key not in seen:
                            seen.add(key)
                            score = (EVENT_SCORE.get(t_name, 3) +
                                     EVENT_NATAL_SCORE.get(n_name, 1) +
                                     EVENT_ASPECT_SCORE.get(current_asp, 2))
                            t_sign, _ = lon_to_sign(get_pos(asp_peak_jd, t_id))
                            n_sign, _ = lon_to_sign(n_lon)
                            peak_date = jd_to_date(asp_peak_jd)
                            is_past = asp_peak_jd < today_jd
                            colors = PLANET_COLOR.get(t_name, {'bg':'rgba(180,178,169,0.15)','color':'#b4b2a9'})
                            candidates.append({
                                'transitPlanet': t_name,
                                'natalPoint': n_name,
                                'aspect': current_asp,
                                'peakDate': peak_date.isoformat(),
                                'peakYear': peak_date.year,
                                'score': score,
                                'isPast': is_past,
                                'transitSign': t_sign,
                                'natalSign': n_sign,
                                'symbol': PLANET_SYMBOL.get(t_name, t_name[0]),
                                'bg': colors['bg'],
                                'color': colors['color'],
                                'name': f"{t_name} {current_asp} natal {n_name}",
                            })
                    in_aspect = False
                    current_asp = None
                    asp_peak_orb = 999

                jd += 14  # step 2 weeks

    # Sort by score desc, then chronologically within ties
    candidates.sort(key=lambda x: (-x['score'], x['peakDate']))

    # Take top 15, but ensure a blend: at least 5 past and 5 future if available
    past = [c for c in candidates if c['isPast']]
    future = [c for c in candidates if not c['isPast']]

    # Deduplicate — only one event per (transit, natal) pair to avoid repetition
    def dedup(lst):
        seen_pairs = set()
        out = []
        for item in lst:
            pair = (item['transitPlanet'], item['natalPoint'])
            if pair not in seen_pairs:
                seen_pairs.add(pair)
                out.append(item)
        return out

    past = dedup(past)
    future = dedup(future)

    # Pick top by score, balanced
    n_past = min(len(past), 8)
    n_future = min(len(future), 8)
    # Guarantee at least 5 each if possible
    if n_past < 5: n_future = min(len(future), 15 - n_past)
    if n_future < 5: n_past = min(len(past), 15 - n_future)
    total = n_past + n_future
    if total < 15:
        extra_past = min(len(past) - n_past, 15 - total)
        extra_future = min(len(future) - n_future, 15 - total - extra_past)
        n_past += extra_past
        n_future += extra_future

    selected = past[:n_past] + future[:n_future]
    # Final sort chronologically
    selected.sort(key=lambda x: x['peakDate'])

    return selected


@app.route('/health')
def health():
    return jsonify({'status': 'ok'})

@app.route('/natal', methods=['POST'])
def natal_chart():
    try:
        body = request.json
        birth = body.get('birth', {})
        overrides = body.get('overrides', {})
        natal, jd, houses = calc_natal(birth, overrides)

        natal_desc = {}
        for k, v in natal.items():
            sign, deg = lon_to_sign(v)
            natal_desc[k] = f"{deg}° {sign}"

        aspects = calc_natal_aspects(natal)

        today = date.today()
        start_jd = date_to_jd(today.year, today.month, today.day)
        transits = get_transits(natal, start_jd)

        return jsonify({
            'natal': natal_desc,
            'natalLongitudes': natal,
            'houses': houses,
            'aspects': aspects,
            'transits': transits,
            'calculated': today.isoformat(),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/events', methods=['POST'])
def life_events():
    """
    Returns the top 15 most significant slow-planet transits to natal points
    spanning 1990–2030, blending past and future events.
    """
    try:
        body = request.json
        birth = body.get('birth', {})
        overrides = body.get('overrides', {})
        natal, jd, houses = calc_natal(birth, overrides)
        birth_year = birth.get('year', 1990)
        events = get_life_events(natal, birth_year)
        return jsonify({
            'events': events,
            'calculated': date.today().isoformat(),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
