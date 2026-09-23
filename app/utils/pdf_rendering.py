"""PDFium must not run concurrently, including through pdfplumber's renderer."""
from threading import RLock


pdfium_lock = RLock()
