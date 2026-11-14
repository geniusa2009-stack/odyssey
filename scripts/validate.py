#!/usr/bin/env python3
"""Offline checks for the publicly deployed ODYSSEY judges microsite."""
from pathlib import Path
import json
root = Path(__file__).resolve().parents[1]
site = root / 'judges-site'
for filename in ('index.html', 'styles.css', 'app.js', 'content.json', 'robots.txt'):
    target = site / filename
    assert target.is_file() and target.stat().st_size > 0, f"Missing {filename}"
html = (site / 'index.html').read_text(encoding='utf-8')
for fragment in ('id="mission"', 'id="experience"', 'id="technology"', 'id="resources"', 'id="demo"'):
    assert fragment in html, f"Missing {fragment}"
assert 'not a streamed Unreal game session' in html
assert 'not a claim that live Unreal streaming is available' in html
config = json.loads((site / 'content.json').read_text(encoding='utf-8'))
for key in ('videoUrl', 'liveDemoUrl', 'videoCaption', 'liveDemoLabel'):
    assert isinstance(config.get(key), str), f"Invalid {key}"
for key in ('videoUrl', 'liveDemoUrl'):
    url = config[key].strip()
    if url:
        assert url.startswith('https://') or url.startswith('./') or url.startswith('/'), f"Unsafe {key}"
print('ODYSSEY judges website: validation passed.')
