"""Qt-free theme catalog shared by persistence and desktop controls."""

THEMES = {
    "light": {"title": "Klar · Hell", "dark": False, "pair": "dark", "colors": {}},
    "dark": {"title": "Nacht · Dunkel", "dark": True, "pair": "light", "colors": {}},
    "ivory": {"title": "Elfenbein · Hell", "dark": False, "pair": "graphite", "colors": {
        "background": "#f5f1e8", "surface": "#fffcf5", "text": "#332c25", "muted": "#746451", "border": "#dbd0be"}},
    "graphite": {"title": "Graphit · Dunkel", "dark": True, "pair": "ivory", "colors": {
        "background": "#191919", "surface": "#272727", "text": "#f3eee6", "muted": "#bdb5ab", "border": "#4b4741"}},
    "mint": {"title": "Minze · Hell", "dark": False, "pair": "forest", "colors": {
        "background": "#edf6f1", "surface": "#fbfffc", "text": "#153c2d", "muted": "#537363", "border": "#c9dfd3"}},
    "forest": {"title": "Wald · Dunkel", "dark": True, "pair": "mint", "colors": {
        "background": "#0f211d", "surface": "#18332b", "text": "#e1f4e9", "muted": "#a7c9b9", "border": "#365b4b"}},
    "rose": {"title": "Rosé · Hell", "dark": False, "pair": "plum", "colors": {
        "background": "#f8f0f5", "surface": "#fffcff", "text": "#3d2640", "muted": "#7a607c", "border": "#e3cee3"}},
    "plum": {"title": "Pflaume · Dunkel", "dark": True, "pair": "rose", "colors": {
        "background": "#221828", "surface": "#33223b", "text": "#f4e8fa", "muted": "#c9accf", "border": "#5c4265"}},
}
THEMES.update({
    'ocean': {'title': 'Ozean · Fließend', 'dark': False, 'pair': 'aurora', 'transition': 'slide', 'radius': 14,
              'colors': {'background': '#eaf3fa', 'surface': '#fafdff', 'text': '#173248', 'muted': '#486578', 'border': '#b7cfde'}},
    'aurora': {'title': 'Aurora · Leuchtend', 'dark': True, 'pair': 'ocean', 'transition': 'zoom', 'radius': 14,
               'colors': {'background': '#101e2b', 'surface': '#1b3044', 'text': '#e4faff', 'muted': '#b1d6e2', 'border': '#476577'}},
    'sunrise': {'title': 'Sonnenaufgang · Sanft', 'dark': False, 'pair': 'ember', 'transition': 'fade', 'radius': 18,
                'colors': {'background': '#fff3e7', 'surface': '#fffdf9', 'text': '#493027', 'muted': '#7d6150', 'border': '#dfc7b3'}},
    'ember': {'title': 'Glut · Warm', 'dark': True, 'pair': 'sunrise', 'transition': 'slide', 'radius': 18,
              'colors': {'background': '#251b1c', 'surface': '#3c2929', 'text': '#fff0df', 'muted': '#d6b6a4', 'border': '#71514d'}},
    'paper': {'title': 'Papier · Geradlinig', 'dark': False, 'pair': 'terminal', 'transition': 'none', 'radius': 2,
              'colors': {'background': '#f2f2ef', 'surface': '#ffffff', 'text': '#202421', 'muted': '#5b625c', 'border': '#b7c1b9'}},
    'terminal': {'title': 'Terminal · Präzise', 'dark': True, 'pair': 'paper', 'transition': 'fade', 'radius': 2,
                 'colors': {'background': '#101713', 'surface': '#1b2820', 'text': '#e0f7e6', 'muted': '#a5c2ae', 'border': '#45614e'}},
})


def is_dark_theme(theme):
    return THEMES[theme]["dark"]


def paired_theme(theme):
    return THEMES[theme]["pair"]
