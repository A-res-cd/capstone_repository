"""Standalone parser process. Never import Flask, configuration, or the database."""
import importlib.util
import json
import math
import os
from pathlib import Path
import sys


def validate(content, extension, limits, abstract=False):
    from io import BytesIO
    if extension == '.pdf':
        import pdfplumber
        from pdfminer.pdftypes import resolve1
        total_pixels = 0
        with pdfplumber.open(BytesIO(content)) as pdf:
            if pdf.doc.encryption or not 1 <= len(pdf.pages) <= (200 if abstract else 20):
                raise ValueError('Invalid PDF.')
            for page in pdf.pages:
                for key in ('MediaBox', 'CropBox'):
                    box = resolve1(page.page_obj.attrs.get(key, page.mediabox))
                    if (len(box) != 4 or any(not math.isfinite(float(d)) or abs(float(d)) > limits['page_points'] for d in box)
                            or float(box[2]) <= float(box[0]) or float(box[3]) <= float(box[1])):
                        raise ValueError('Invalid PDF bounds.')
                if resolve1(page.page_obj.attrs.get('UserUnit', 1)) != 1:
                    raise ValueError('Unsupported PDF scale.')
                dimensions = (page.width, page.height)
                if any(not math.isfinite(d) or not 0 < d <= limits['page_points'] for d in dimensions):
                    raise ValueError('Invalid PDF dimensions.')
                scale = min(300 / 72, limits['render_dimension'] / max(dimensions))
                pixels = math.ceil(page.width * scale) * math.ceil(page.height * scale)
                total_pixels += pixels
                if not abstract and (pixels > limits['page_pixels'] or total_pixels > limits['total_pixels']):
                    raise ValueError('Raster budget exceeded.')
    else:
        from PIL import Image
        with Image.open(BytesIO(content)) as image:
            if (image.format not in ('JPEG', 'PNG') or getattr(image, 'n_frames', 1) != 1
                    or min(image.size) < 1 or max(image.size) > 10000
                    or image.width * image.height > limits['image_pixels']):
                raise ValueError('Image budget exceeded.')
            image.verify()


def main():
    limits = json.loads(sys.argv[1])
    # Applied before loading native libraries or parsing attacker-controlled bytes.
    if os.name == 'posix':
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (limits['memory_mb'] * 1024**2,) * 2)
        resource.setrlimit(resource.RLIMIT_CPU, (limits['job_seconds'], limits['job_seconds'] + 1))
        resource.setrlimit(resource.RLIMIT_FSIZE, (16 * 1024**2,) * 2)
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    extension, operation = sys.argv[2:4]
    byte_limit = (20 if operation == 'abstract' else 5) * 1024**2
    content = sys.stdin.buffer.read(byte_limit + 1)
    if not content or len(content) > byte_limit:
        raise ValueError('Invalid file size.')
    validate(content, extension, limits, abstract=(operation == 'abstract'))
    result = {}
    if operation == 'abstract':
        import pdfplumber
        import re
        from io import BytesIO
        text_size = 0
        with pdfplumber.open(BytesIO(content)) as pdf:
            for page in pdf.pages[:20]:
                text = page.extract_text() or ''
                text_size += len(text)
                if text_size > limits['text_chars']:
                    raise ValueError('Text budget exceeded.')
                page.close()
                if re.search(r'TABLE\s*OF\s*CONTENTS', text, re.IGNORECASE):
                    continue
                match = re.search(r'(?im)^\s*ABSTRACT\s*$\n?(.*)', text, re.DOTALL)
                if match:
                    result['abstract'] = match.group(1).strip()
                    break
    elif operation == 'extract':
        path = Path(__file__).with_name('cor_extractor.py')
        spec = importlib.util.spec_from_file_location('isolated_cor_extractor', path)
        extractor = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(extractor)
        extractor.PROCESSING_LIMITS = limits
        result = (extractor.extract_cor_fields(content) if extension == '.pdf'
                  else extractor.extract_id_fields(content))
    sys.stdout.write(json.dumps(result))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        # No parser internals, document contents, or credentials in responses.
        sys.exit(2)
