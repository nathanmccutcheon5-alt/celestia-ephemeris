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

def calc_natal(birth, overrides=None):
    h = birth.get('hour', 12.0)
    jd = date_to_jd(birth['year'], birth['month'], birth['day'], h)
    natal = {}
    for name, pid in PLANETS.items():
        natal[name] = get_pos(jd, pid)

    # Houses if we have lat/lon and birth time
    houses_data = None
    if birth.get('lat') and birth.get('lon') and h != 12.0:
        cusps, ascmc = swe.houses(jd, birth['lat'], birth['lon'], b'P')
        natal['Ascendant'] = ascmc[0]
        natal['Midheaven'] = ascmc[1]
        houses_data = list(cusps)

    # Apply sign overrides
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
    """Calculate aspects between natal planets for the wheel."""
    ASPECT_COLORS = {
        'conjunction': '#c9a96e',
        'trine': '#5db8a0',
        'sextile': '#8b7fd4',
        'square': '#c47d8e',
        'opposition': '#d4955a',
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
                    'p1': p1, 'p2': p2,
                    'aspect': asp_name,
                    'orb': round(orb, 1),
                    'color': ASPECT_COLORS.get(asp_name, '#888'),
                    'lon1': natal[p1],
                    'lon2': natal[p2],
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

        # Build natal description
        natal_desc = {}
        for k, v in natal.items():
            sign, deg = lon_to_sign(v)
            natal_desc[k] = f"{deg}° {sign}"

        # Natal aspects for wheel
        aspects = calc_natal_aspects(natal)

        # Current transits
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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
