"""Extract signup fields from the University's COR layout."""
import re
import os
from pathlib import Path
import shutil
try:
    import pytesseract
except ImportError:
    pytesseract = None
from io import BytesIO

import pdfplumber

if __package__ and __package__.startswith('app.'):
    from app.utils.pdf_rendering import pdfium_lock
else:
    from threading import RLock
    pdfium_lock = RLock()

PROCESSING_LIMITS = {'render_dimension': 2000, 'text_chars': 200_000, 'ocr_seconds': 10, 'image_pixels': 16_000_000}


def configure_tesseract():
    configured = os.getenv('TESSERACT_CMD')
    if configured:
        pytesseract.pytesseract.tesseract_cmd = configured
    elif not shutil.which('tesseract'):
        for command in (r'C:\Program Files\Tesseract-OCR\tesseract.exe', r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe'):
            if Path(command).is_file():
                pytesseract.pytesseract.tesseract_cmd = command
                break


FIELD_KEYS = (
    "registration_no",
    "student_no",
    "first_name",
    "middle_name",
    "last_name",
)


def _empty_fields():
    return {key: "" for key in FIELD_KEYS}


def _clean(value):
    return re.sub(r"\s+", " ", (value or "")).strip(" :;|-\t")


def _value_after_label(text, label_pattern):
    match = re.search(
        rf"(?im)^\s*(?:{label_pattern})\s*[:#-]?\s*(.+?)\s*$",
        text,
    )
    value = _clean(match.group(1)) if match else ""
    if value:
        value = re.split(
            r"\s+(?=(?:College|Program|Sex|Major|Curriculum|Age|Year\s+Level|Scholarship)\s*:)",
            value,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
    return value


def _parse_name(value):
    template_order = False
    value = re.sub(r"[^A-Za-z .,\-]", " ", value or "")
    value = _clean(value).replace(" .", ".")
    if "," in value:
        last, given = (part.strip() for part in value.split(",", 1))
    else:
        parts = value.split()
        # The COR template prints names as LAST FIRST MIDDLE. OCR can lose
        # the comma, so recognize its all-caps two-part form.
        template_order = (
            len(parts) == 2
            and all(part.replace(".", "").isupper() for part in parts)
        )
        last, given = (
            (parts[0], " ".join(parts[1:])) if template_order
            else (parts[-1], " ".join(parts[:-1]))
        ) if len(parts) > 1 else ("", value)

    given_parts = given.replace(".", "").split()
    if len(given_parts) >= 2:
        first = given_parts[0]
        middle = " ".join(given_parts[1:])
    elif ("," in value or template_order) and given_parts and len(given_parts[0]) > 1 and given_parts[0][-1].isalpha():
        # OCR often turns `AARIES M.` into `AARIESM.` on the sample COR.
        compact = given_parts[0]
        first, middle = compact[:-1], compact[-1]
    else:
        first, middle = (given_parts[0], "") if given_parts else ("", "")

    return {
        "first_name": first.title(),
        "middle_name": middle.upper(),
        "last_name": last.title(),
    }


def parse_cor_text(text):
    """Parse fields from text extracted from a COR or OCR output."""
    fields = _empty_fields()
    text = text or ""
    registration = _value_after_label(text, r"Registration\s*No\.?|RegistrationNo")
    registration_match = re.search(r"\b\d{5,}\b", registration)
    fields["registration_no"] = registration_match.group(0) if registration_match else registration

    student = _value_after_label(text, r"Student\s*No\.?|StudentNo")
    student_match = re.search(r"[A-Za-z]{2,8}\s*\d{4}\s*-\s*\d{3,}", student)
    fields["student_no"] = re.sub(r"\s+", "", student_match.group(0)) if student_match else student

    name = _value_after_label(text, r"Name")
    fields.update(_parse_name(name))
    return fields


def _ocr_page(page):
    if pytesseract is None:
        return "", "Install pytesseract and Tesseract OCR to auto-read image-based COR files."
    configure_tesseract()
    bitmap = name_crop = crop = None
    try:
        # Render the complete page. This works for scanned CORs and avoids
        # depending on the PDF's internal image encoding.
        with pdfium_lock:
            resolution = min(300, PROCESSING_LIMITS['render_dimension'] * 72 / max(page.width, page.height))
            bitmap = page.to_image(resolution=resolution).original
        full_text = pytesseract.image_to_string(bitmap, config="--psm 6", timeout=PROCESSING_LIMITS['ocr_seconds'])
        if len(full_text) > PROCESSING_LIMITS['text_chars']:
            raise ValueError('Extracted text exceeds processing budget.')

        # The template's name row is tightly packed. A focused crop keeps
        # OCR from joining the name with the Program value beside it.
        width, height = bitmap.size
        crop = bitmap.crop((
            int(width * 0.115), int(height * 0.14),
            int(width * 0.30), int(height * 0.18),
        ))
        name_crop = crop.resize((max(1, int(width * 0.74)), max(1, int(height * 0.16))))
        name_text = pytesseract.image_to_string(name_crop, config="--psm 6", timeout=PROCESSING_LIMITS['ocr_seconds']).strip()
        compact_name = re.search(r"(?im)^\s*Name\s*:\s*([A-Za-z.]+)", full_text)
        name_hint = re.search(r"\b([A-Z]{3,})\s+[A-Z]{3,}\.?\b", name_text)
        if compact_name and name_hint:
            compact = re.sub(r"[^A-Za-z]", "", compact_name.group(1))
            surname = name_hint.group(1)
            if compact.upper().startswith(surname.upper()) and len(compact) > len(surname):
                corrected = f"{surname} {compact[len(surname):]}"
                full_text = f"Name: {corrected}\n{full_text}"
        elif name_text:
            full_text = f"Name: {name_text}\n{full_text}"
        return full_text, ""
    except Exception:
        return "", "The COR image could not be read automatically. Enter the fields manually."
    finally:
        for image in (name_crop, crop, bitmap):
            if image is not None:
                image.close()


def extract_cor_fields(content):
    """Return extracted signup fields and a warning when OCR is unavailable."""
    text_chunks = []
    warning = ""
    text_size = 0
    with pdfplumber.open(BytesIO(content)) as pdf:
        for page in pdf.pages:
            start = len(text_chunks)
            text_chunks.append(page.extract_text() or "")
            if not text_chunks[-1].strip():
                ocr_text, ocr_warning = _ocr_page(page)
                text_chunks.append(ocr_text)
                warning = warning or ocr_warning
            text_size += sum(len(chunk) for chunk in text_chunks[start:])
            if text_size > PROCESSING_LIMITS['text_chars']:
                raise ValueError('Extracted text exceeds processing budget.')
            page.close()

    fields = parse_cor_text("\n".join(text_chunks))
    if not any(fields.values()) and not warning:
        warning = "No COR fields were found. Enter the fields manually."
    fields["warning"] = warning
    return fields


def extract_id_fields(content):
    """Read likely faculty ID text and reuse the shared name parser."""
    from PIL import Image, ImageOps

    try:
        configure_tesseract()
        if pytesseract is None:
            return {**_empty_fields(), "warning": "Install pytesseract and Tesseract OCR to read this ID. Enter your details manually."}
        with Image.open(BytesIO(content)) as source:
            if source.width * source.height > PROCESSING_LIMITS['image_pixels']:
                raise ValueError('Image budget exceeded.')
            with ImageOps.exif_transpose(source) as oriented, oriented.convert('RGB') as image:
                image.thumbnail((PROCESSING_LIMITS['render_dimension'],) * 2)
                text = pytesseract.image_to_string(image, config="--psm 6", timeout=PROCESSING_LIMITS['ocr_seconds'])
                if len(text) > PROCESSING_LIMITS['text_chars']:
                    raise ValueError('Extracted text exceeds processing budget.')
        fields = parse_cor_text(text)
        # ID cards commonly print the person's name without a "Name" label.
        if not any((fields["first_name"], fields["middle_name"], fields["last_name"])):
            name = re.search(r"(?im)^\s*name\s*[:#-]\s*([A-Z][A-Z' -]{2,})\s*$", text)
            if name:
                fields.update(_parse_name(name.group(1)))
        fields["warning"] = "" if any(fields[key] for key in ("first_name", "middle_name", "last_name")) else "Name not found. Enter your details manually."
        return fields
    except Exception:
        return {**_empty_fields(), "warning": "Tesseract could not read this ID. Enter your details manually."}
