r"""Generate synthetic PDF manuscripts using ERMS-Manuscript.pdf as the layout.

Run from the repository root:
    .\venv\Scripts\python.exe datasets/manuscripts/generate.py --count 25

Requires pdfplumber and reportlab. No application or database imports are needed.
Existing PDFs are never overwritten. The source PDF is read only.
"""

import argparse
from collections import Counter
from io import BytesIO
from pathlib import Path
import random
import re

import pdfplumber
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph


WIDTH, HEIGHT = 515.9, 728.5
LEFT, RIGHT, CENTER = 108, 444, 276
FONTS = {
    'regular': 'Times-Roman', 'bold': 'Times-Bold',
    'italic': 'Times-Italic', 'bolditalic': 'Times-BoldItalic',
}
LOREM = (
    'Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod '
    'tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, '
    'quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo '
    'consequat. Duis aute irure dolor in reprehenderit in voluptate velit esse '
    'cillum dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat '
    'non proident, sunt in culpa qui officia deserunt mollit anim id est laborum.'
)
PROJECTS = [
    'Library Circulation', 'Clinic Appointment', 'Supply Inventory',
    'Scholarship Application', 'Dormitory Reservation', 'Laboratory Equipment',
    'Student Attendance', 'Community Event', 'Internship Placement',
    'Campus Facility Reservation', 'Alumni Engagement', 'Canteen Ordering',
    'Research Archive', 'Student Feedback', 'Transportation Scheduling',
    'Maintenance Request', 'Lost Property', 'Volunteer Coordination',
    'Tuition Payment', 'Document Request', 'Sports Equipment',
    'Peer Tutoring', 'Campus Visitor', 'Career Fair', 'Project Consultation',
]
CAMPUSES = ['Riverside', 'Hillcrest', 'Lakeside', 'Northfield', 'Westbridge',
            'Eastwood', 'Southridge', 'Greenfield', 'Brookside', 'Fairview']
FIRST = ['Alden', 'Bianca', 'Carlo', 'Diana', 'Elias', 'Fiona', 'Gavin', 'Hana',
         'Irene', 'Jasper', 'Kira', 'Lorenzo', 'Mira', 'Nico', 'Olivia', 'Paolo',
         'Quinn', 'Rafael', 'Selena', 'Tristan', 'Una', 'Victor', 'Wendy',
         'Xander', 'Yasmin']
LAST = ['Alonzo', 'Bautista', 'Castillo', 'Domingo', 'Espino', 'Flores', 'Garcia',
        'Herrera', 'Ignacio', 'Jimenez', 'Lazaro', 'Mendoza', 'Navarro', 'Ortega',
        'Pascual', 'Ramos', 'Santos', 'Torres', 'Valdez', 'Villanueva', 'Aquino',
        'Benitez', 'Cabrera', 'Cruz', 'Reyes']
INSTITUTION = ['Republic of the Philippines',
               'Nueva Ecija University of Science and Technology',
               'College of Information and Communications Technology']
HEADINGS = {'JOINT UNDERTAKING', 'CERTIFICATION OF ENGLISH CRITIC',
            'ACKNOWLEDGEMENT', 'DEDICATION', 'ABSTRACT', 'TABLE OF CONTENTS',
            'TABLE OF TABLES', 'TABLE OF FIGURES', 'REFERENCES', 'APPENDICES'}


def register_fonts():
    files = {'regular': 'times.ttf', 'bold': 'timesbd.ttf',
             'italic': 'timesi.ttf', 'bolditalic': 'timesbi.ttf'}
    directory = Path('C:/Windows/Fonts')
    if all((directory / filename).is_file() for filename in files.values()):
        for style, filename in files.items():
            FONTS[style] = 'TNR-' + style
            pdfmetrics.registerFont(TTFont(FONTS[style], str(directory / filename)))
    pdfmetrics.registerFontFamily(FONTS['regular'], normal=FONTS['regular'],
                                  bold=FONTS['bold'], italic=FONTS['italic'],
                                  boldItalic=FONTS['bolditalic'])


def read_layout(source):
    pages = []
    with pdfplumber.open(source) as pdf:
        if len(pdf.pages) != 164 or 'A CAPSTONE' not in (pdf.pages[0].extract_text() or ''):
            raise ValueError('Template must use the 164-page ERMS manuscript format.')
        for page in pdf.pages:
            if abs(page.width - WIDTH) > .05 or abs(page.height - HEIGHT) > .05:
                raise ValueError('Template page dimensions differ from the ERMS format.')
            lines = []
            for item in page.extract_text_lines():
                chars = item.pop('chars')
                font = Counter(c['fontname'] for c in chars).most_common(1)[0][0]
                style = ('bolditalic' if 'Bold' in font and 'Italic' in font else
                         'bold' if 'Bold' in font else 'italic' if 'Italic' in font else 'regular')
                item['font'] = FONTS[style]
                item['size'] = Counter(round(c['size'], 1) for c in chars).most_common(1)[0][0]
                item['baseline'] = chars[0]['matrix'][5]
                item['bold'] = sum('Bold' in c['fontname'] for c in chars) / len(chars)
                lines.append(item)
            edges = [(e['x0'], e['top'], e['x1'], e['bottom']) for e in page.edges
                     if e.get('orientation') in ('h', 'v') and e['top'] > 55]
            pages.append({'lines': lines, 'edges': edges})
    return pages


def draw_line(pdf, value, top, x=CENTER, style='regular', size=11, align='center'):
    pdf.setFont(FONTS[style], size)
    draw = {'center': pdf.drawCentredString, 'right': pdf.drawRightString,
            'left': pdf.drawString}[align]
    draw(x, HEIGHT - top - size * .784, value)


def paragraph(pdf, text, top, max_height):
    style = ParagraphStyle('body', fontName=FONTS['regular'], fontSize=11,
                           leading=18.98, alignment=4, firstLineIndent=36)
    body = Paragraph(text, style)
    _, height = body.wrap(RIGHT - LEFT, max_height)
    if height > max_height:
        raise ValueError('Generated paragraph does not fit the template.')
    body.drawOn(pdf, LEFT, HEIGHT - top - height + 2.5)


def title_lines(text, size):
    words, options = text.split(), []
    for i in range(1, len(words) - 1):
        for j in range(i + 1, len(words)):
            parts = [' '.join(words[:i]), ' '.join(words[i:j]), ' '.join(words[j:])]
            widths = [pdfmetrics.stringWidth(s, FONTS['bold'], size) for s in parts]
            if max(widths) <= 336:
                options.append((max(widths) - min(widths), parts))
    if not options:
        raise ValueError('Generated title does not fit the template.')
    return min(options)[1]


def person(rng):
    return (rng.choice(FIRST), rng.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ') + '.', rng.choice(LAST))


def cover_name(author):
    first, middle, last = author
    return f'{last}, {first} {middle}'.upper()


def first_pages(pdf, record):
    title, authors = record['title'], record['authors']
    teacher, adviser = record['teacher'], record['adviser']
    for text, top in zip(title_lines(title, 12), [73.8, 94.5, 115.2]):
        draw_line(pdf, text, top, style='bold', size=12)
    draw_line(pdf, 'A CAPSTONE AND RESEARCH PROJECT', 344.5, style='bold')
    draw_line(pdf, 'by:', 439.4, style='bold')
    for author, top in zip(authors, [477.4, 496.4, 515.3, 534.2]):
        draw_line(pdf, cover_name(author), top, style='bold')
    draw_line(pdf, record['date'], 629.2, x=267.5, style='bold')
    pdf.showPage()
    draw_line(pdf, 'ii', 36.9, RIGHT, align='right')
    draw_line(pdf, 'TITLE PAGE', 92.7, style='bold')
    for text, top in zip(title_lines(title, 11), [111.6, 130.6, 149.6]):
        draw_line(pdf, text, top, style='bold')
    for text, top in [
        ('A Capstone and Research Project Presented to', 187.5),
        ('the Faculty of the College of Information and Communications Technology', 206.5),
        ('Cabanatuan City, Nueva Ecija', 225.5),
        ('In Partial Fulfillment of the Requirements for the Degree', 282.4),
        ('Bachelor of Science in Information Technology', 301.4),
        ('with Specialization in Database Systems Technology', 320.4),
        ('Submitted by:', 377.3), ('Submitted to:', 510.2),
        (' '.join(teacher) + ', Ph.D', 529),
        ('Capstone and Research Instructor', 541.7), (record['date'], 630.3),
    ]:
        draw_line(pdf, text, top)
    for author, top in zip(authors, [396.2, 415.2, 434.2, 453.2]):
        draw_line(pdf, cover_name(author), top, style='bold')
    pdf.showPage()
    draw_line(pdf, 'iii', 36.9, RIGHT, align='right')
    for text, top in zip(INSTITUTION, [73.6, 86.2, 98.9]):
        draw_line(pdf, text, top)
    draw_line(pdf, 'APPROVAL SHEET', 124.3, style='bold')
    names = ', '.join(' '.join(a) for a in authors[:-1]) + ', and ' + ' '.join(authors[-1])
    paragraph(pdf, f'This capstone and research project is entitled <b>{title.title()}</b>, '
              f'prepared and submitted by <b>{names}</b> in partial fulfillment of the '
              'requirements for the degree, Bachelor of Science in Information Technology '
              'with Specialization in Database Systems Technology is hereby recommended '
              'for approval and acceptance.', 143.3, 165)
    for name, suffix, label, x in [(teacher, 'PhD', 'Course Teacher', 185),
                                   (adviser, 'MSIT', 'Adviser', 359)]:
        draw_line(pdf, ' '.join(name) + ', ' + suffix, 317.8, x, style='bold')
        draw_line(pdf, label, 331.7, x)
    approval = ('Approved in partial fulfillment of the requirements for the degree, '
                'Bachelor of Science in Information Technology with Specialization in '
                'Database Systems Technology')
    paragraph(pdf, approval + ' by the Examining Committee.', 377, 60)
    draw_line(pdf, 'Marina L. Robles, MIT', 452.9, style='bold')
    draw_line(pdf, 'Chairman', 465.4)
    for name, x in [('Tomas E. Mercado, MSIT', 185), ('Leah S. Salazar, MSIT', 359)]:
        draw_line(pdf, name, 482, x, style='bold')
        draw_line(pdf, 'Member', 496, x)
    paragraph(pdf, approval, 527.7, 60)
    for name, label, x in [('Marina L. Robles, MIT', 'Chairman, DST', 185),
                           ('Felix P. Rosales, DIT', 'Dean, CICT', 359)]:
        draw_line(pdf, name, 607.4, x, style='bold')
        draw_line(pdf, label, 621.3, x)
    for top in [345.3, 634.9]:
        for x in [113, 291]:
            draw_line(pdf, 'Date:', top, x, align='left')
            pdf.setLineWidth(.5)
            pdf.line(x + 28, HEIGHT - top - 11, x + 150, HEIGHT - top - 11)
    pdf.showPage()


def lorem_line(width, font, size, offset):
    words, result = LOREM.split(), []
    while True:
        word = words[offset % len(words)]
        if pdfmetrics.stringWidth(' '.join(result + [word]), font, size) > width:
            break
        result.append(word)
        offset += 1
    return ' '.join(result) or 'Ut', offset


def remaining_pages(pdf, layout, record):
    offset = record['index'] * 11
    for page_index, page in enumerate(layout[3:], 3):
        for x0, top, x1, bottom in page['edges']:
            pdf.setLineWidth(.4)
            pdf.line(x0, HEIGHT - top, x1, HEIGHT - bottom)
        for item in page['lines']:
            source = item['text'].replace('\ufffd', '-')
            preserve = (item['top'] < 55 or source in HEADINGS or 9 <= page_index < 15 or
                        (16 <= page_index < 110 and item['bold'] > .90) or
                        source.startswith(('Chapter ', 'APPENDIX ')))
            if page_index in [3, 4] and source in INSTITUTION:
                preserve = True
            if page_index == 3 and (
                source in ['_______________________SS.', 'Province of Nueva Ecija', 'Name ID No. Address']
                or source.startswith(('Doc No.', 'Page No.', 'Book No.', 'Series of'))
            ):
                preserve = True
            width = item['x1'] - item['x0']
            if preserve:
                text = source.replace('Electronic Records Management System', 'Proposed Information System')
                text = text.replace('ELECTRONIC RECORDS', 'PROPOSED DIGITAL RECORDS').replace('ERMS', 'SYSTEM')
            else:
                text, offset = lorem_line(width, item['font'], item['size'], offset)
            if page_index == 4 and 470 < item['top'] < 490:
                text = 'Elena R. Soriano, MBusAn'
            if page_index == 4 and source == 'Research Editor':
                text = source
            if page_index == 15 and item['top'] > 620:
                text = ('Keywords: ' + record['topic'] + '; Lorem Ipsum;' if source.startswith('Keywords:')
                        else 'Database Systems; Capstone Research; Sample Data')
                preserve, width = True, RIGHT - item['x0']
            obj = pdf.beginText(item['x0'], item['baseline'])
            obj.setFont(item['font'], item['size'])
            actual = pdfmetrics.stringWidth(text, item['font'], item['size'])
            if actual > width:
                obj.setHorizScale(100 * width / actual)
            elif not preserve and ' ' in text and width > 100:
                obj.setWordSpace((width - actual) / text.count(' '))
            obj.textOut(text)
            pdf.drawText(obj)
        if page_index >= 116 and len(page['lines']) <= 4:
            paragraph(pdf, LOREM, 150, 400)
        pdf.showPage()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--count', type=int, default=25, help='Number of PDFs to create (default: 25).')
    parser.add_argument('--template', type=Path, default=Path.home() / 'Downloads/ERMS-Manuscript.pdf',
                        help='Original ERMS PDF (default: ~/Downloads/ERMS-Manuscript.pdf).')
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parent,
                        help='Output folder (default: folder containing this script).')
    parser.add_argument('--seed', type=int, help='Optional random seed for reproducible names and titles.')
    args = parser.parse_args()
    if args.count < 1:
        parser.error('--count must be at least 1.')
    if not args.template.is_file():
        parser.error('Template PDF not found; supply its location using --template.')
    register_fonts()
    print('Reading template layout...', flush=True)
    layout = read_layout(args.template)
    args.output.mkdir(parents=True, exist_ok=True)
    indexes = [int(match.group(1)) for file in args.output.glob('sample_*.pdf')
               if (match := re.match(r'sample_(\d+)_', file.name))]
    start = max(indexes, default=0) + 1
    rng = random.Random(args.seed)
    for index in range(start, start + args.count):
        topic = rng.choice(PROJECTS) + ' Management System'
        title = ('Design and Development of a ' + topic + ' for ' + rng.choice(CAMPUSES) + ' Campus').upper()
        people = []
        while len(people) < 6:
            candidate = person(rng)
            if candidate not in people:
                people.append(candidate)
        record = {'index': index, 'topic': topic, 'title': title, 'authors': people[:4],
                  'adviser': people[4], 'teacher': people[5],
                  'date': 'DECEMBER ' + str(rng.randint(2021, 2025))}
        name = f'sample_{index:02d}_' + re.sub(r'[^a-z0-9]+', '_', topic.lower()) + '.pdf'
        path = args.output / name
        buffer = BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=(WIDTH, HEIGHT), pageCompression=1)
        pdf.setTitle(title)
        pdf.setAuthor('; '.join(' '.join(a) for a in record['authors']))
        pdf.setSubject('Synthetic manuscript for upload extraction testing; fictional names and Lorem Ipsum content.')
        first_pages(pdf, record)
        remaining_pages(pdf, layout, record)
        pdf.save()
        with path.open('xb') as target:
            target.write(buffer.getvalue())
        print(f'Created {path.name}', flush=True)
    print(f'Done: {args.count} PDFs, {len(layout)} pages each, in {args.output.resolve()}')


if __name__ == '__main__':
    main()
