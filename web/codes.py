# -*- coding: utf-8 -*-
"""Zugangscodes verwalten. Damit gibst du deinen Testern Zugang - ohne dass
irgendjemand deinen OpenAI-Key zu sehen bekommt.

    python codes.py neu Max 5        -> Code fuer Max, 5 Videos
    python codes.py liste            -> wer hat wie viel verbraucht
    python codes.py sperre CODE      -> Zugang sofort dicht
    python codes.py frei CODE        -> wieder freigeben
    python codes.py limit CODE 20    -> Kontingent aendern
"""
import json
import os
import random
import string
import sys

DATA = os.environ.get('DVE_DATA', os.path.join(os.path.dirname(
    os.path.abspath(__file__)), 'data'))
F = os.path.join(DATA, 'codes.json')


def laden():
    if os.path.exists(F):
        return json.load(open(F, encoding='utf-8'))
    return {}


def sichern(c):
    os.makedirs(DATA, exist_ok=True)
    json.dump(c, open(F, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd = sys.argv[1]
    c = laden()
    if cmd == 'neu':
        name = sys.argv[2] if len(sys.argv) > 2 else 'Tester'
        limit = int(sys.argv[3]) if len(sys.argv) > 3 else 5
        code = (name.upper()[:6].replace(' ', '') + '-'
                + ''.join(random.choices(string.digits, k=4)))
        c[code] = {'name': name, 'limit': limit, 'genutzt': 0, 'aktiv': True}
        sichern(c)
        print(f'Code fuer {name}: {code}   ({limit} Videos)')
    elif cmd == 'liste':
        if not c:
            print('Noch keine Codes.')
        for k, v in c.items():
            zustand = 'aktiv   ' if v.get('aktiv', True) else 'GESPERRT'
            print(f"{k:16} {zustand} {v.get('name',''):12} "
                  f"{v.get('genutzt', 0)}/{v.get('limit', '-')} Videos"
                  + (f"  zuletzt {v['zuletzt']}" if v.get('zuletzt') else ''))
    elif cmd == 'sperre':
        c[sys.argv[2]]['aktiv'] = False
        sichern(c)
        print('Gesperrt:', sys.argv[2])
    elif cmd == 'frei':
        c[sys.argv[2]]['aktiv'] = True
        sichern(c)
        print('Freigegeben:', sys.argv[2])
    elif cmd == 'limit':
        c[sys.argv[2]]['limit'] = int(sys.argv[3])
        sichern(c)
        print('Neues Kontingent:', sys.argv[2], sys.argv[3])
    else:
        print(__doc__)


if __name__ == '__main__':
    main()
