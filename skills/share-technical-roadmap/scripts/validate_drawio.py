"""Validate native uncompressed draw.io structure, not scientific correctness."""
import argparse
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path


def validate(path):
    root = ET.parse(path).getroot()
    errors, counts = [], []
    diagrams = root.findall('diagram')
    if root.tag != 'mxfile' or not diagrams:
        errors.append('Expected mxfile with at least one diagram')
    for diagram in diagrams:
        name = diagram.get('name', 'unnamed')
        model = diagram.find('mxGraphModel')
        if model is None:
            errors.append(f'{name}: compressed or missing mxGraphModel')
            continue
        cells = model.findall('./root/mxCell')
        ids = {c.get('id'): c for c in cells}
        if len(ids) != len(cells) or None in ids:
            errors.append(f'{name}: duplicate or missing cell IDs')
        if not {'0', '1'} <= ids.keys():
            errors.append(f'{name}: missing root cells')
        vertices = [c for c in cells if c.get('vertex') == '1']
        edges = [c for c in cells if c.get('edge') == '1']
        try:
            pw, ph = float(model.get('pageWidth')), float(model.get('pageHeight'))
        except (TypeError, ValueError):
            errors.append(f'{name}: missing page size')
            continue
        if pw <= 0 or ph <= 0 or not vertices:
            errors.append(f'{name}: empty diagram or nonpositive page')
        for c in cells:
            cid, parent = c.get('id'), c.get('parent')
            if parent and parent not in ids:
                errors.append(f'{name}/{cid}: unknown parent')
            style, value = c.get('style', ''), c.get('value', '')
            if re.search(r'<\s*(table|img)\b', value, re.I) or 'shape=table' in style or 'shape=image' in style:
                errors.append(f'{name}/{cid}: table or flattened image node')
            seen, ancestor = {cid}, parent
            while ancestor and ancestor in ids:
                if ancestor in seen:
                    errors.append(f'{name}/{cid}: parent cycle')
                    break
                seen.add(ancestor)
                ancestor = ids[ancestor].get('parent')
        for c in vertices:
            cid, parent = c.get('id'), c.get('parent')
            geom = c.find('mxGeometry')
            try:
                x, y = float(geom.get('x', 0)), float(geom.get('y', 0))
                w, h = float(geom.get('width')), float(geom.get('height'))
                bw, bh = pw, ph
                if parent in ids and ids[parent].get('vertex') == '1':
                    pg = ids[parent].find('mxGeometry')
                    bw, bh = float(pg.get('width')), float(pg.get('height'))
                if min(x, y) < 0 or min(w, h) <= 0 or x+w > bw+.01 or y+h > bh+.01:
                    errors.append(f'{name}/{cid}: outside page or parent')
            except (AttributeError, TypeError, ValueError):
                errors.append(f'{name}/{cid}: invalid geometry')
        for c in edges:
            for attr in ('source', 'target'):
                endpoint = c.get(attr)
                if endpoint:
                    if endpoint not in ids or ids[endpoint].get('vertex') != '1':
                        errors.append(f'{name}/{c.get("id")}: dangling {attr}')
                elif c.find(f'mxGeometry/mxPoint[@as="{attr}Point"]') is None:
                    errors.append(f'{name}/{c.get("id")}: missing {attr}')
        counts.append({'page': name, 'nodes': len(vertices), 'edges': len(edges)})
    return {'path': str(path), 'pages': counts, 'errors': errors, 'ok': not errors}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file', type=Path)
    args = parser.parse_args()
    try:
        result = validate(args.file)
    except (ET.ParseError, OSError) as exc:
        result = {'ok': False, 'errors': [str(exc)]}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result['ok'] else 1)
