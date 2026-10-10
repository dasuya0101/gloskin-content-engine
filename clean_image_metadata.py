"""Export PNG pixels without ancillary metadata; preserve internal provenance records."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from PIL import Image

def chunks(path):
    raw = path.read_bytes()
    assert raw[:8] == b'\x89PNG\r\n\x1a\n'
    result, offset = [], 8
    while offset < len(raw):
        size = struct.unpack('>I', raw[offset:offset+4])[0]
        kind = raw[offset+4:offset+8].decode('ascii')
        result.append(kind)
        offset += size + 12
    return sorted(set(result))

def clean(path):
    before = chunks(path)
    with Image.open(path) as source:
        pixels = source.convert('RGB')
        expected = hashlib.sha256(pixels.tobytes()).hexdigest()
        fresh = Image.frombytes('RGB', pixels.size, pixels.tobytes())
    fresh.save(path, format='PNG')
    with Image.open(path) as check:
        assert hashlib.sha256(check.tobytes()).hexdigest() == expected
        assert not check.info
    after = chunks(path)
    assert set(after) <= {'IHDR', 'IDAT', 'IEND'}
    return {'file': str(path), 'before': before, 'after': after,
            'decoded_rgb_pixels_unchanged': True}

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('folder', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    records = [clean(path) for path in sorted(args.folder.rglob('*.png'))]
    args.report.write_text(json.dumps(records, indent=2), encoding='utf-8')
    print(f'Verified {len(records)} PNGs: pixels unchanged; only IHDR, IDAT and IEND chunks remain.')
