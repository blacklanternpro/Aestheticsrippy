import os
import urllib.request
import urllib.error
import json
import base64
from pathlib import Path

key = os.environ.get("GEMINI_API_KEY", "")
with open('test_shot.png', 'rb') as f:
    b64 = base64.b64encode(f.read()).decode('utf-8')

prompts = [
    'Describe this image in 1 word:',
    'Deconstruct the layout, archetype, typography and colors of this graphic design scan. Output JSON.',
]

models = ['gemini-3.6-flash', 'gemini-flash-latest']

for m in models:
    for p_text in prompts:
        payload = {
            'contents': [{
                'parts': [
                    {'text': p_text},
                    {'inline_data': {'mime_type': 'image/png', 'data': b64}}
                ]
            }]
        }
        url = f'https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={key}'
        req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=20) as res:
                data = json.loads(res.read())
                txt = data['candidates'][0]['content']['parts'][0]['text'].strip()
                print(f"[{m}] '{p_text[:30]}...' -> OK: {txt[:100]}...\n")
        except urllib.error.HTTPError as e:
            err = e.read().decode('utf-8', errors='ignore')
            print(f"[{m}] '{p_text[:30]}...' -> Error {e.code}: {err[:150]}\n")
