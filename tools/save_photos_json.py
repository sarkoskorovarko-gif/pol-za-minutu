"""Компактно пересохранить data/photos.json: каждый контур — в одну строку."""
import json, sys
def dump(d, path):
    out = ['[']
    for k, x in enumerate(d):
        out.append(' {')
        items = list(x.items())
        for j, (key, v) in enumerate(items):
            if key in ('floor', 'quad', 'img', 'size', 'focus'):
                s = json.dumps(v)
            elif key in ('holes', 'windows'):
                s = '[' + (',\n   '.join(json.dumps(h) for h in v)).join(['\n   ', '\n  ']) + ']' if v else '[]'
            else:
                s = json.dumps(v, ensure_ascii=False)
            out.append(f'  "{key}": {s}' + (',' if j < len(items) - 1 else ''))
        out.append(' }' + (',' if k < len(d) - 1 else ''))
    out.append(']')
    open(path, 'w', encoding='utf-8').write('\n'.join(out) + '\n')
if __name__ == '__main__':
    p = sys.argv[1] if len(sys.argv) > 1 else 'data/photos.json'
    dump(json.load(open(p, encoding='utf-8')), p)
