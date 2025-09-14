from PIL import Image
import pytesseract
from pdf2image import convert_from_path
import pymupdf as fitz
import numpy
import json
import logging
from helperfuncs import *
import os
import re
import string
from types import SimpleNamespace
try:
    import cv2
except Exception:
    cv2 = None


def write_PDFpreview(filename, prevfile, password=None):
    # Import pdf file + write to preview
    # Pass password to pdf2image if provided
    pages = convert_from_path(filename, dpi=100, fmt="jpeg", last_page=1, userpw=password)  
    pages[0].save(prevfile, 'JPEG')  
    return


def getPDFOCR(filename, workdir, pagenr, password=None):
    # Pt.1: Import pdf file  
#    pages = convert_from_path(filename, dpi=150, output_folder=workdir, fmt="jpeg", 
#        jpegopt={'quality':90,'progressive':False,'optimize':False})  
#    pages = convert_from_path(filename, dpi=200, fmt="jpeg", grayscale=True, output_folder=workdir, 
#        jpegopt={'quality':90,'progressive':False,'optimize':False})  
#    print(pytesseract.get_tesseract_version()) 
#    page = convert_from_path(filename, dpi=200, fmt="jpeg", grayscale=True, first_page=pagenr, last_page=pagenr, 
#        jpegopt={'quality':90,'progressive':False,'optimize':True})[0]  

    # Pass password through to pdf2image (userpw)
    page = convert_from_path(filename, dpi=200, output_folder=workdir, fmt="ppm", grayscale=True, first_page=pagenr, last_page=pagenr, userpw=password)[0]  

    # Old: Iterate through all the pages to store them as JPEG files  
    # for page in pages:  
    exportfile = workdir + "Page_no_" + str(pagenr) + ".ppm"  
    page.save(exportfile, 'ppm')  

    # this is probably the place to control output
    page.convert('L')

    # if page.format == 'PPM':
    #     print('PPM image: ' + exportfile)
    # else:
    #    print('Invalid image type: ' + exportfile)

    # image.load()

    text1 = "Could not determine PDF contents."
    result = 0
    maxtries = 200

    pilimge = Image.open(exportfile)
    print(pilimge.format)

    while result < maxtries:
        try:
            result += 1
            tess = pytesseract.image_to_string (pilimge, lang="deu" )
            text1 = str(tess)
            result = maxtries + 1 # this would be success
        except Exception as error:
            print("An OCR error occurred:", error)

    return "" + text1.replace('-\n', '')


# Find fingerprint of best matching document ******************
def getPDFContents(filename, workdir, password=None):
    """
    Use PyMuPDF to open the PDF (supports passwords), extract text and
    fall back to rendering pages + OCR when text extraction yields too little.

    Raises ValueError('encrypted') when a password is required but not given,
    and ValueError('bad_password') when a supplied password is incorrect.
    """
    try:
        doc = fitz.open(filename)
    except RuntimeError as e:
        msg = str(e).lower()
        # If the error message indicates encryption, try a password-aware open or raise encrypted
        if 'password' in msg or 'encrypted' in msg or 'password required' in msg:
            if not password:
                raise ValueError('encrypted')
            # Try opening via stream with password (some PyMuPDF builds require this)
            try:
                with open(filename, 'rb') as fh:
                    data = fh.read()
                doc = fitz.open(stream=data, filetype='pdf', password=password)
            except RuntimeError:
                # password didn't work
                raise ValueError('bad_password')
            except Exception:
                raise
        else:
            raise

    # If document requires a password
    try:
        needs_pass = getattr(doc, 'needs_pass', False)
    except Exception:
        needs_pass = False

    if needs_pass:
        if not password:
            try:
                doc.close()
            except Exception:
                pass
            raise ValueError('encrypted')
        # authenticate returns True on success
        ok = False
        try:
            ok = doc.authenticate(password)
        except Exception:
            ok = False
        if not ok:
            try:
                doc.close()
            except Exception:
                pass
            raise ValueError('bad_password')

    # Extract text from all pages
    retstr = ""
    npages = doc.page_count
    for pno in range(npages):
        try:
            page = doc.load_page(pno)
            txt = page.get_text("text")
            if txt:
                retstr += txt + "\n\n"
        except Exception:
            # skip page on error
            continue

    # If extracted text too small, render pages and run OCR
    if len(retstr) < max(1, npages * 3):
        retstr = ""
        for pno in range(npages):
            try:
                page = doc.load_page(pno)
                # render at ~200 dpi
                mat = fitz.Matrix(200.0 / 72.0, 200.0 / 72.0)
                pix = page.get_pixmap(matrix=mat)
                exportfile = os.path.join(workdir, f"Page_no_{pno+1}.ppm")
                pix.save(exportfile)

                pilimge = Image.open(exportfile)
                tess = pytesseract.image_to_string(pilimge, lang="deu")
                retstr += str(tess).replace('-\n', '') + "\n\n"
            except Exception:
                # If rendering or OCR fails, continue to next page
                continue

    try:
        doc.close()
    except Exception:
        pass

    return retstr


def cos_sim(np_ay1, np_ay2):
    if np_ay1 and np_ay2:
        dot_product = numpy.dot(np_ay1, np_ay2)
        norm_a = numpy.linalg.norm(np_ay1)
        norm_b = numpy.linalg.norm(np_ay2)
        return dot_product / (norm_a * norm_b)
    return 0

# Find fingerprint of best matching document ******************
def vsmSimilarity(array1, array2):
    if not (array1 and array2):
        return 0.0
        
    # Get all unique tag IDs from both arrays
    all_ids = {tag['id'] for tag in array1 + array2}
    
    # Create vectors for each array
    def create_vector(tags):
        return [next((t['occ'] for t in tags if t['id'] == tag_id), 0) 
                for tag_id in all_ids]
    
    vec1 = create_vector(array1)
    vec2 = create_vector(array2)
    
    return cos_sim(vec1, vec2)

# Find fingerprint of best matching document ******************
def getBestTagMatch(foundtags, app):
    if not hasattr(app, 'filestotags') or not app.filestotags:
        return {}
        
    best_match = {}
    best_similarity = 0
    
    # Group tags by file with their occurrences
    files_tags = {}
    
    # Process filestotags to group tags by file and count occurrences
    for entry in app.filestotags:
        # Handle both dictionary and SQLite Row objects
        if hasattr(entry, 'keys'):  # SQLite Row object
            file_id = entry['file_id']
            tag_id = entry['tag_id']
            occ = entry['occ'] if 'occ' in entry else 1
        else:  # Dictionary
            file_id = entry.get('file_id')
            tag_id = entry.get('tag_id')
            occ = entry.get('occ', 1)
            
        if file_id is None or tag_id is None:
            continue
        
        if file_id not in files_tags:
            files_tags[file_id] = {}
        
        # Store the maximum occurrence count for each tag
        if tag_id not in files_tags[file_id] or files_tags[file_id][tag_id] < occ:
            files_tags[file_id][tag_id] = occ
    
    # Find the best matching file
    for file_id, tag_occurrences in files_tags.items():
        # Convert tag_occurrences dict to the format expected by vsmSimilarity
        file_tags = [{'id': tid, 'occ': occ} for tid, occ in tag_occurrences.items()]
        
        # Calculate similarity between found tags and file's tags
        similarity = vsmSimilarity(foundtags, file_tags)
        
        if similarity > best_similarity:
            best_similarity = similarity
            best_match = {
                'id': file_id,
                'tags': json.dumps(file_tags),
                'similarity': similarity
            }
            sPrint(f"New best match found for file {file_id} with similarity {similarity}")
    
    return best_match


def filter_ner_entities(ents, text=None, min_len=3, max_len=80, allow_labels=None):
    """
    Filter spaCy NER entities to reduce noisy / non-usable candidates.

    Parameters:
      ents: iterable of spaCy Span objects (must have .label_ and .text)
      text: the full document text (optional) used for simple frequency checks
      min_len, max_len: length limits on entity text
      allow_labels: optional set/list of labels to keep (e.g., {'PER','ORG','LOC','MISC'})

    Returns: list of SimpleNamespace objects with attributes .label_ and .text

    Heuristics applied:
      - length and character checks
      - reject entities containing pipes or excessive punctuation
      - reject entities that are mostly digits or look like dates/urls/emails
      - remove unmatched brackets
      - normalize whitespace and strip surrounding punctuation
      - deduplicate case-insensitively
    """
    if allow_labels is not None:
        allow_labels = set([l.upper() for l in allow_labels])

    seen = set()
    out = []

    puncre = re.compile(r'[{}]'.format(re.escape(string.punctuation)))
    date_re = re.compile(r'\b\d{1,2}[\.\-/]\d{1,2}[\.\-/]\d{2,4}\b')
    url_re = re.compile(r'https?://|www\.|@')
    # currency / amount tokens (EUR A 2,00/20 etc.)
    currency_re = re.compile(r'\b(EUR|USD|GBP|CHF|JPY|AUD|CAD)\b', re.I)
    amt_re = re.compile(r'\d+[\.,]\d{1,3}')
    # identifier-like tokens: long uppercase+digits without spaces (e.g. SWIFT/BIC)
    id_like_re = re.compile(r'^[A-Z0-9_\-]{8,}$')
    # long digit sequences (bank ids, account numbers)
    digit_seq_re = re.compile(r'\d{10,}')
    # repeated character runs (e.g. ÜÜÜÜ)
    repeat_re = re.compile(r'(.)\1{3,}')

    for ent in ents:
        try:
            label = getattr(ent, 'label_', None) or (ent[0] if isinstance(ent, (list,tuple)) else None)
            etxt = getattr(ent, 'text', None) or (ent[1] if isinstance(ent, (list,tuple)) else None)
            if label is None or etxt is None:
                continue
            label = str(label).strip()
            s = str(etxt).strip()
        except Exception:
            continue

        # normalize whitespace
        s = re.sub(r'\s+', ' ', s).strip()
        # strip surrounding punctuation
        s = s.strip(string.punctuation + "\u201c\u201d\u2018\u2019")

        if not s:
            continue
        if len(s) < min_len or len(s) > max_len:
            continue

        # optional label filter
        if allow_labels and label.upper() not in allow_labels:
            continue

        low = s.lower()
        key = (label.upper(), low)
        if key in seen:
            continue

        # reject if contains pipe or control chars
        if '|' in s or '\x00' in s or '\x1f' in s:
            continue

        # reject urls, emails, or strings with @
        if url_re.search(s):
            continue

        # reject mostly digits or obvious dates
        digits = sum(ch.isdigit() for ch in s)
        if digits / max(1, len(s)) > 0.6:
            continue
        if date_re.search(s):
            continue

        # reject currency-like tokens (EUR followed by amounts or similar)
        if currency_re.search(s) and (amt_re.search(s) or any(ch.isdigit() for ch in s)):
            continue

        # reject identifier-like tokens (long uppercase/digit sequences)
        # remove common separators first (including underscore)
        compact = s.replace(' ', '').replace('.', '').replace('-', '').replace('_', '')
        if id_like_re.match(compact):
            continue

        # reject if contains a long contiguous digit sequence (likely an ID/account)
        if digit_seq_re.search(s):
            continue

        # reject tokens with excessive repeated characters (e.g. LLÜÜÜUÜI)
        if repeat_re.search(s):
            continue

        # reject tokens with low letter density (mostly symbols/digits)
        letters = sum(1 for ch in s if ch.isalpha())
        if len(s) > 0 and (letters / len(s)) < 0.35:
            # allow short exceptions, but remove long non-word tokens
            if len(s) > 4:
                continue

        # punctuation density
        pcount = len(puncre.findall(s))
        if pcount / max(1, len(s)) > 0.25:
            continue

        # unmatched brackets
        for a, b in [('(',')'), ('[',']'), ('{','}')]:
            if (s.count(a) > 0) != (s.count(b) > 0):
                # unmatched - strip brackets and re-evaluate
                s = s.replace(a, '').replace(b, '')
                s = s.strip()
                if not s:
                    # if nothing left after removing unmatched brackets, skip
                    continue

        # Simple frequency check: if text provided, require the entity appears in text
        if text is not None:
            if low not in text.lower():
                # allow short exceptions (single word proper nouns), but otherwise skip
                if len(s.split()) > 1:
                    continue

        # Passed all filters
        seen.add(key)
        out.append(SimpleNamespace(label_=label, text=s))

    return out


def findDatesInText(text):
    """
    Extract dates from text (German/English). Returns list of ["DATE", "DD.MM.YYYY"]
    Month-only matches (e.g. "September 2024" or "im September 2024") are normalized
    to the first day of that month (01.MM.YYYY).
    """
    retarray = []
    if not text:
        return retarray

    months = {
        'jan': 1, 'january': 1, 'januar': 1,
        'feb': 2, 'february': 2, 'februar': 2,
        'mar': 3, 'marc': 3, 'march': 3, 'mär': 3, 'märz': 3, 'maerz': 3, 'marz': 3,
        'apr': 4, 'april': 4,
        'may': 5, 'mai': 5,
        'jun': 6, 'june': 6, 'juni': 6,
        'jul': 7, 'july': 7, 'juli': 7,
        'aug': 8, 'august': 8,
        'sep': 9, 'sept': 9, 'september': 9,
        'oct': 10, 'okt': 10, 'october': 10, 'oktober': 10,
        'nov': 11, 'november': 11,
        'dec': 12, 'dez': 12, 'december': 12, 'dezember': 12
    }

    found = set()

    def _year_to_4(y: str) -> str:
        y = y.strip()
        if len(y) == 2:
            return '20' + y
        return y

    for m in re.finditer(r"\b(\d{1,2})[\.\-/](\d{1,2})[\.\-/](\d{2,4})\b", text):
        d, mon, y = m.groups()
        y = _year_to_4(y)
        try:
            di = int(d); mo = int(mon); yi = int(y)
            if 1 <= di <= 31 and 1 <= mo <= 12:
                found.add(f"{di:02d}.{mo:02d}.{yi:04d}")
        except Exception:
            pass

    for m in re.finditer(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", text):
        y, mon, d = m.groups()
        try:
            di = int(d); mo = int(mon); yi = int(y)
            if 1 <= di <= 31 and 1 <= mo <= 12:
                found.add(f"{di:02d}.{mo:02d}.{yi:04d}")
        except Exception:
            pass

    month_alt = r"(" + r"|".join(sorted({re.escape(k) for k in months.keys()}, key=len, reverse=True)) + r")"

    dm_regex = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?" + month_alt + r"\,?\s+(\d{4})\b", re.I)
    for m in dm_regex.finditer(text):
        d, monname, y = m.groups()
        y = _year_to_4(y)
        monnum = months.get(monname.lower().rstrip('.'), None)
        if monnum:
            try:
                di = int(d); yi = int(y)
                if 1 <= di <= 31:
                    found.add(f"{di:02d}.{monnum:02d}.{yi:04d}")
            except Exception:
                pass

    mdy_regex = re.compile(r"\b" + month_alt + r"\.?\s+(\d{1,2})(?:st|nd|rd|th)?\,?\s+(\d{4})\b", re.I)
    for m in mdy_regex.finditer(text):
        monname, d, y = m.groups()
        y = _year_to_4(y)
        monnum = months.get(monname.lower().rstrip('.'), None)
        if monnum:
            try:
                di = int(d); yi = int(y)
                if 1 <= di <= 31:
                    found.add(f"{di:02d}.{monnum:02d}.{yi:04d}")
            except Exception:
                pass

    my_regex = re.compile(r"\b(?:im\s+|in\s+)?" + month_alt + r"\.?\s+(\d{4})\b", re.I)
    for m in my_regex.finditer(text):
        monname, y = m.groups()
        y = _year_to_4(y)
        monnum = months.get(monname.lower().rstrip('.'), None)
        if monnum:
            try:
                yi = int(y)
                found.add(f"01.{monnum:02d}.{yi:04d}")
            except Exception:
                pass

    for date in sorted(found):
        retarray.append(["DATE", date])

    return retarray


def _parse_amount_value(s: str):
    """
    Try to parse a human-written amount string into a float (in EUR-like or US-like formats).
    Returns float or None.
    """
    if not s:
        return None
    try:
        t = s.strip()
        # remove currency symbols and text
        t = re.sub(r'[A-Za-z\s€$£¥₹¤]', '', t)
        t = t.strip()
        if not t:
            return None

        # if both dot and comma exist, assume last one is decimal separator
        if '.' in t and ',' in t:
            if t.rfind(',') > t.rfind('.'):
                # treat comma as decimal, remove dots as thousand separators
                t = t.replace('.', '')
                t = t.replace(',', '.')
            else:
                # treat dot as decimal, remove commas
                t = t.replace(',', '')

        # if only comma present, assume it's the decimal separator
        elif ',' in t and '.' not in t:
            t = t.replace('.', '')
            t = t.replace(',', '.')

        # if only dots present, they might be thousand separators or decimal
        elif '.' in t and ',' not in t:
            parts = t.split('.')
            # if last part length == 2, interpret as decimal
            if len(parts[-1]) == 2:
                t = t
            else:
                # remove dots as thousand separators
                t = t.replace('.', '')

        # final clean: keep digits and one dot
        t = re.sub(r'[^0-9\.]', '', t)
        if not t:
            return None
        val = float(t)
        return val
    except Exception:
        return None


def findAmountsInText(text):
    """
    Extract monetary amounts from text. Returns list of ["AMOUNT", display_string].

    The function uses a fairly permissive regex to find number tokens with separators
    and optional currency symbols. It will try to deduplicate visually identical
    matches and return the list sorted by appearance.
    """
    ret = []
    if not text:
        return ret

    # match sequences like "€ 1.234,56", "1.234,56 €", "EUR 1234.56", "$1,234.56" or plain numbers with separators
    amt_re = re.compile(r'(?:EUR|USD|GBP|CHF|JPY|AUD|CAD|€|\$|£)?\s*\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{1,2})\s*(?:€|EUR|USD|GBP|CHF|JPY|AUD|CAD|\$|£)?', re.I)

    seen = set()
    for m in amt_re.finditer(text):
        s = m.group(0).strip()
        # normalize whitespace
        s_norm = re.sub(r'\s+', ' ', s)
        # try to parse numeric value to avoid picking IDs that look numeric
        val = _parse_amount_value(s_norm)
        # ignore plain integers that are very large but not amounts (heuristic)
        if val is None:
            continue
        # ignore zero or negative
        if val <= 0:
            continue

        # dedupe by numeric value + short string
        key = (round(val, 2), re.sub(r'[^0-9]', '', s_norm)[-6:])
        if key in seen:
            continue
        seen.add(key)
        ret.append(["AMOUNT", s_norm])

    return ret


def pick_best_amount(amounts, text):
    """
    Choose the most probable invoice total from a list of amount candidates.
    amounts: list of ["AMOUNT", display_string]
    text: full document text for proximity checks

    Returns display_string or "".
    """
    if not amounts:
        return ""

    try:
        amt_keywords = ['gesamt', 'gesamtbetrag', 'summe', 'betrag', 'total', 'amount', 'due', 'zu zahlen', 'endbetrag']

        scores = {}
        for _label, astr in amounts:
            scores.setdefault(astr, {'freq':0, 'kw':0, 'value':0.0})

        # frequency
        for astr in list(scores.keys()):
            try:
                freq = len(safeFind(astr, text))
            except Exception:
                freq = 0
            scores[astr]['freq'] = freq

        # keyword proximity
        for astr in list(scores.keys()):
            kwcount = 0
            try:
                occs = safeFind(astr, text)
            except Exception:
                occs = []
            for idx in occs:
                start = max(0, idx - 80)
                end = min(len(text), idx + len(astr) + 80)
                window = text[start:end].lower()
                for kw in amt_keywords:
                    if kw in window:
                        kwcount += 1
            scores[astr]['kw'] = kwcount

        # numeric value
        for astr in list(scores.keys()):
            try:
                v = _parse_amount_value(astr)
                scores[astr]['value'] = v if v is not None else 0.0
            except Exception:
                scores[astr]['value'] = 0.0

        # scoring
        best = None
        bestscore = -1
        for astr, v in scores.items():
            score = v['kw'] * 10 + v['freq'] * 2 + (v['value'] / 10000.0)
            if score > bestscore:
                bestscore = score
                best = astr

        return best or ""
    except Exception:
        return ""


def pick_best_date(dates, text):
    """
    Choose the most probable document/invoice date from a list of date candidates.
    dates: list of ["DATE", "DD.MM.YYYY"]
    text: full document text for proximity checks

    Returns date string like 'DD.MM.YYYY' or "".
    """
    if not dates:
        return ""

    try:
        from datetime import datetime
        now = datetime.now()
        key_keywords = ['rechnung', 'rechnungsdatum', 'invoice', 'invoice date', 'datum', 'issued', 'ausgestellt', 'date']

        scores = {}
        for _label, dstr in dates:
            scores.setdefault(dstr, {'freq':0, 'kw':0, 'recency':0.0})

        # frequency
        for dstr in list(scores.keys()):
            try:
                freq = len(safeFind(dstr, text))
            except Exception:
                freq = 0
            scores[dstr]['freq'] = freq

        # keyword proximity
        for dstr in list(scores.keys()):
            kwcount = 0
            try:
                occs = safeFind(dstr, text)
            except Exception:
                occs = []
            for idx in occs:
                start = max(0, idx - 50)
                end = min(len(text), idx + len(dstr) + 50)
                window = text[start:end].lower()
                for kw in key_keywords:
                    if kw in window:
                        kwcount += 1
            scores[dstr]['kw'] = kwcount

        # recency
        for dstr in list(scores.keys()):
            try:
                dt = datetime.strptime(dstr, '%d.%m.%Y')
                days = abs((now - dt).days)
                scores[dstr]['recency'] = 1.0 / (1.0 + (days / 365.0))
            except Exception:
                scores[dstr]['recency'] = 0.0

        # final score
        best = None
        bestscore = -1
        for dstr, v in scores.items():
            score = v['kw'] * 10 + v['freq'] * 2 + v['recency']
            if score > bestscore:
                bestscore = score
                best = dstr

        return best or ""
    except Exception:
        return ""


def suggest_filename(text, date_hint=None, prefer_labels=None, maxlen=60):
    """
    Create a speaking filename base (without date/extension) from document text.

    Strategy:
      - Look for ORGANIZATION or PERSON-like tokens via simple heuristics (capitalized lines)
      - Prefer lines that contain keywords like invoice, rechnung, statement
      - Fall back to the first meaningful text line
      - Sanitize to remove filesystem-unfriendly characters and shorten to maxlen

    Returns a short string safe for use as filename (no extension).
    """
    if not text:
        return "document"

    txt = text.strip().replace('\r', '\n')

    # try to find a headline-like line (short, contains letters, mixed case)
    lines = [l.strip() for l in txt.split('\n') if l.strip()]

    # multilingual invoice keywords -> canonical prefix
    invoice_keywords = {
        'rechnung': 'Rechnung',
        'rechnungsnummer': 'Rechnung',
        'rechnung nr': 'Rechnung',
        'invoice': 'Invoice',
        'invoice no': 'Invoice',
        'statement': 'Statement',
        'facture': 'Facture',
        'fattura': 'Fattura',
        'factura': 'Factura'
    }

    # helper: find first matching keyword in the whole text
    prefix = None
    for k in invoice_keywords:
        if k in txt.lower():
            prefix = invoice_keywords[k]
            break

    candidate = None

    # If an invoice-like keyword exists, try to extract the company nearby
    if prefix:
        # look for lines that look like company names: containing GmbH, AG, Ltd, Inc, GmbH & Co, etc.
        company_designators = ['gmbh', 'gmbh & co', 'ag', 'ltd', 'limited', 'inc', 'llc', 'kg', 'ohg', 's.a.', 'sa']
        # search lines for company designators first
        for l in lines:
            low = l.lower()
            for d in company_designators:
                if d in low:
                    candidate = l
                    break
            if candidate:
                break

        # if none, search for a nearby capitalized line (title-like)
        if not candidate:
            # attempt to pick a line with multiple capitalized words
            for l in lines[:30]:
                words = [w for w in l.split() if w]
                if len(words) >= 1 and any(w[0].isupper() for w in words):
                    # prefer short lines that look like names
                    if len(words) <= 6 and any(c.isalpha() for c in l):
                        candidate = l
                        break

        # if still none, try to pick a line immediately after a keyword occurrence
        if not candidate:
            lowered = txt.lower()
            for k in invoice_keywords:
                idx = lowered.find(k)
                if idx != -1:
                    # find next non-empty line after the position
                    # compute approximate character index to line mapping
                    chars = txt[idx:idx+200]
                    # split subsequent text and choose first meaningful token line
                    subs = chars.split('\n')
                    if len(subs) > 1 and subs[1].strip():
                        candidate = subs[1].strip()
                        break

        # if we found a company-like candidate, build base as Prefix_Company
        if candidate:
            # remove short date fragments or labels from candidate
            candidate = re.sub(r"^(von|an|für|fuer)\s+", '', candidate, flags=re.I)
            company_name = re.sub(r'[^\w\s-]', '', candidate, flags=re.U)
            company_name = re.sub(r'\s+', '_', company_name).strip('_')
            base = f"{prefix}_{company_name}"
        else:
            base = f"{prefix}_Company"

        # append date later as usual
    else:
        # prefer lines that contain keywords (legacy behavior)
        keywords = ['invoice', 'rechnung', 'statement', 'rechnungnr', 'rechnung nr', 'rechnung nr.', 'rechnungsnummer']
        for l in lines:
            low = l.lower()
            for kw in keywords:
                if kw in low:
                    candidate = l
                    break
            if candidate:
                break

    # second pass: a short title-ish line (no more than 6 words, contains letters)
    if not candidate:
        for l in lines[:20]:
            if 3 <= len(l) <= 100 and len(l.split()) <= 6 and any(c.isalpha() for c in l):
                candidate = l
                break

    # third pass: first non-empty line
    if not candidate and len(lines) > 0:
        candidate = lines[0]

    if not candidate:
        candidate = "document"

    # remove typical leading words like 'von', 'an', 'für', 'fuer' etc and dates fragments
    candidate = re.sub(r"^(von|an|für|fuer)\s+", '', candidate, flags=re.I)

    # if date_hint provided, try to incorporate an identifier (e.g., Invoice ACME -> Invoice_ACME)
    # build base by taking alphanumeric + spaces
    base = re.sub(r'[^\w\s-]', '', candidate, flags=re.U)
    base = re.sub(r'\s+', '_', base).strip('_')

    if date_hint:
        # normalise date dd.mm.yyyy -> yyyymmdd or accept already yyyymmdd
        d = date_hint.strip()
        m = re.match(r"(\d{2})\.(\d{2})\.(\d{4})", d)
        if m:
            base = f"{base}_{m.group(3)}{m.group(2)}{m.group(1)}"
        else:
            # if other form, just append short sanitized date
            ds = re.sub(r'[^0-9]', '', d)
            if ds:
                base = f"{base}_{ds}"

    # trim length
    if len(base) > maxlen:
        base = base[:maxlen].rstrip('_')

    if not base:
        base = "document"

    return base


def load_zone_templates(config_path=None):
    """Load zone templates from JSON file. Returns dict with templates and settings.
    If file is not found, returns defaults embedded in code.
    """
    cfg = None
    if config_path is None:
        config_path = os.path.join(os.path.dirname(__file__), 'config', 'zones.json')
    try:
        with open(config_path, 'r', encoding='utf-8') as fh:
            cfg = json.load(fh)
    except Exception:
        logging.exception(f"Could not load zone config at {config_path}, using built-in defaults")
        cfg = {
            'zoned_ocr': False,
            'use_word_confidences': False,
            'templates': [],
            'fallback_order': []
        }
    return cfg


def rel_rect_to_px(rect_rel, width, height):
    """Convert relative rect [x0,y0,x1,y1] -> pixel box (left, upper, right, lower)"""
    x0, y0, x1, y1 = rect_rel
    left = int(round(x0 * width))
    upper = int(round(y0 * height))
    right = int(round(x1 * width))
    lower = int(round(y1 * height))
    # clamp
    left = max(0, min(left, width-1))
    upper = max(0, min(upper, height-1))
    right = max(0, min(right, width))
    lower = max(0, min(lower, height))
    return (left, upper, right, lower)


def ocr_zone(pil_image, box, lang='deu'):
    """Crop PIL image to box and run pytesseract.image_to_string returning text.
    box = (left, upper, right, lower)
    """
    try:
        crop = pil_image.crop(box)
        text = pytesseract.image_to_string(crop, lang=lang)
        return str(text)
    except Exception:
        logging.exception('OCR failed for zone')
        return ""


def ner_and_filter(text, nlp, full_text=None, allow_labels=None):
    """Run spaCy NER on text and filter entities using existing filter_ner_entities.
    Returns list of SimpleNamespace(label_=..., text=...)
    """
    try:
        doc = nlp(text)
        ents = filter_ner_entities(doc.ents, text=full_text, allow_labels=allow_labels)
        return ents
    except Exception:
        logging.exception('NER failed for zone')
        return []


def score_and_merge_zone_entities(zone_entity_map, templatesettings=None):
    """Score entities found in zones and produce merged entity list.
    zone_entity_map: { zone_id: [SimpleNamespace(label_, text), ...], ... }
    Returns merged_entities: list of dicts {text,label,best_zone,score,provenance}
    """
    merged = {}
    # basic scoring: occurrences in zone * zone weight
    for zone_id, zinfo in zone_entity_map.items():
        weight = zinfo.get('weight', 1.0)
        ents = zinfo.get('entities', [])
        for ent in ents:
            key = (ent.label_.upper(), ent.text.lower())
            score = weight * 1.0
            if key not in merged or merged[key]['score'] < score:
                merged[key] = {
                    'text': ent.text,
                    'label': ent.label_,
                    'best_zone': zone_id,
                    'score': score,
                    'provenance': [zone_id]
                }
            else:
                merged[key]['provenance'].append(zone_id)
    # convert to list
    out = []
    for v in merged.values():
        out.append(v)
    return out


def evaluate_template_quality(zone_entity_map, cfg):
    """Simple heuristic: sum entities and chars in zones, compare to thresholds."""
    min_entities = cfg.get('quality_thresholds', {}).get('min_entities', 1)
    min_chars = cfg.get('quality_thresholds', {}).get('min_chars_in_zones', 20)
    total_entities = 0
    total_chars = 0
    for zid, zinfo in zone_entity_map.items():
        ents = zinfo.get('entities', [])
        total_entities += len(ents)
        text = zinfo.get('text', '')
        total_chars += len(text)
    return (total_entities >= min_entities) and (total_chars >= min_chars)


def detect_zones_by_density(pilim, min_area_px=2000, blur_ksize=(25,25), merge_close_px=24, debug_images=False):
    """Simple density-based zone detector.

    Steps:
      - convert to grayscale
      - local contrast enhancement (CLAHE)
      - Gaussian blur to produce density map
      - Otsu threshold (inverted) to extract ink regions
      - morphological closing to join nearby text blocks
      - find contours and return bounding boxes above area threshold

    This is intentionally minimal and deterministic — no pytesseract dependency.

    If debug_images is True, writes intermediate images to /tmp for inspection
    (no timestamps; files are overwritten on each call).
    """
    if cv2 is None:
        return []
    import numpy as _np
    try:
        img = _np.array(pilim.convert('RGB'))[:, :, ::-1].copy()
    except Exception:
        return []

    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Local contrast enhancement (robust for varied scans)
    try:
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        gray_enh = clahe.apply(gray)
    except Exception:
        gray_enh = gray

    # Gaussian blur to form a density map (use smaller kernel than before)
    try:
        kx, ky = blur_ksize
        kx = max(3, kx if kx % 2 == 1 else kx + 1)
        ky = max(3, ky if ky % 2 == 1 else ky + 1)
        blurred = cv2.GaussianBlur(gray_enh, (kx, ky), 0)
    except Exception:
        blurred = gray_enh

    # Threshold: invert so text/ink becomes white on black background
    try:
        _, th = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    except Exception:
        # fallback to a simple fixed threshold
        _, th = cv2.threshold(blurred, 128, 255, cv2.THRESH_BINARY_INV)

    # Morphological closing to join nearby text into blocks
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (merge_close_px, merge_close_px))
    th_closed = cv2.morphologyEx(th, cv2.MORPH_CLOSE, kernel)

    # Find contours on the closed mask
    contours_info = cv2.findContours(th_closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    # compatibility for OpenCV versions returning 2 or 3 values
    contours = contours_info[-2] if len(contours_info) == 3 else contours_info[0]

    # If debug requested, write intermediate images to /tmp for inspection (no timestamps)
    if debug_images:
        try:
            # grayscale and enhanced
            cv2.imwrite('/tmp/mbai_density_gray.png', gray)
            cv2.imwrite('/tmp/mbai_density_gray_enh.png', gray_enh)
            # blurred / density map
            cv2.imwrite('/tmp/mbai_density_blurred.png', blurred)
            # threshold maps
            cv2.imwrite('/tmp/mbai_density_th.png', th)
            cv2.imwrite('/tmp/mbai_density_th_closed.png', th_closed)
            # overlay contours and bounding boxes on color image for visualization
            overlay = img.copy()
            try:
                cv2.drawContours(overlay, contours, -1, (0, 255, 0), 2)
            except Exception:
                pass
            try:
                for cnt in contours:
                    x, y, ww, hh = cv2.boundingRect(cnt)
                    cv2.rectangle(overlay, (x, y), (x + ww, y + hh), (0, 0, 255), 2)
            except Exception:
                pass
            cv2.imwrite('/tmp/mbai_density_contours.png', overlay)
        except Exception:
            logging.exception('Failed to write debug density images to /tmp')

    zones = []
    for idx, cnt in enumerate(contours):
        x, y, ww, hh = cv2.boundingRect(cnt)
        area = ww * hh
        if area < min_area_px:
            continue
        x1, y1, x2, y2 = x, y, x + ww, y + hh
        zones.append({
            'id': f'density_{idx}',
            'rect_px': (int(x1), int(y1), int(x2), int(y2)),
            'rect': [x1 / w, y1 / h, x2 / w, y2 / h],
            'weight': 1.0,
            'score': float(area),
            'area': int(area),
        })

    # Merge nearby single-line boxes that likely belong to the same block.
    # Criteria: similar height, similar left x position, and vertical gap <= 2x line height.
    zones = merge_single_line_blocks(zones, w, h, height_tol=0.25, x_tol=0.05, max_vertical_gap_multiplier=2.0, max_line_height=48)

    # Sort top-to-bottom, left-to-right for stability and reassign ids
    zones = sorted(zones, key=lambda z: (z['rect'][1], z['rect'][0]))
    for i, z in enumerate(zones):
        z['id'] = f'zone_{i}'
    return zones


def getPDFContents_zoned(filename, workdir, password=None, config_path=None, nlp=None, process_pages=1, lang='deu', debug=False):
    """Zoned OCR + NER flow. Returns tuple (full_text, zone_results)

    zone_results = {
       'template_id': ..., 'zones': [{id,name,rect,text,entities: [...] ,weight}],
       'merged_entities': [ ... ]
    }
    """
    cfg = load_zone_templates(config_path)
    if not cfg.get('zoned_ocr'):
        # fallback to existing behavior
        return getPDFContents(filename, workdir, password)

    # open pdf with same logic as getPDFContents but only render pages we need
    try:
        doc = fitz.open(filename)
    except RuntimeError as e:
        msg = str(e).lower()
        if 'password' in msg or 'encrypted' in msg or 'password required' in msg:
            if not password:
                raise ValueError('encrypted')
            try:
                with open(filename, 'rb') as fh:
                    data = fh.read()
                doc = fitz.open(stream=data, filetype='pdf', password=password)
            except RuntimeError:
                raise ValueError('bad_password')
            except Exception:
                raise
        else:
            raise

    # only handle first page by default
    npages = doc.page_count
    page_idx = 0
    try:
        page = doc.load_page(page_idx)
    except Exception:
        doc.close()
        return "", {}

    # render to pixmap at ~200 dpi
    mat = fitz.Matrix(200.0 / 72.0, 200.0 / 72.0)
    pix = page.get_pixmap(matrix=mat)
    exportfile = os.path.join(workdir, f"Page_no_{page_idx+1}.ppm")
    pix.save(exportfile)

    pilim = Image.open(exportfile)
    width, height = pilim.size

    # First, try density-based detection (default). If it returns zones, use them.
    # debug parameter controls whether intermediate images are written
    detected = detect_zones_by_density(pilim, debug_images=bool(debug))
    if detected:
        chosen_result = {}
        chosen_template = {'id': 'density', 'name': 'Density detection'}
        for z in detected:
            zid = z['id']
            pxbox = tuple(z['rect_px'])
            text = ocr_zone(pilim, pxbox, lang=lang)
            ents = []
            if nlp and text.strip():
                ents = ner_and_filter(text, nlp, full_text=None, allow_labels=['PER','ORG','LOC','MISC'])
            chosen_result[zid] = {
                'id': zid,
                'name': z.get('name', zid),
                'rect': z['rect'],
                'rect_px': pxbox,
                'weight': z.get('weight', 1.0),
                'text': text,
                'entities': ents
            }
    else:
        # fall back to template-driven zones (existing behavior)
        templates = {t['id']: t for t in cfg.get('templates', [])}
        fallback = cfg.get('fallback_order', list(templates.keys()))

        chosen_result = None
        chosen_template = None

        for tid in fallback:
            tmpl = templates.get(tid)
            if not tmpl:
                continue
            zone_entity_map = {}
            # process each enabled zone
            for zone in tmpl.get('zones', []):
                if not zone.get('enabled', True):
                    continue
                zid = zone['id']
                rect_rel = zone['rect']
                pxbox = rel_rect_to_px(rect_rel, width, height)
                text = ocr_zone(pilim, pxbox, lang=lang)
                ents = []
                if nlp and text.strip():
                    ents = ner_and_filter(text, nlp, full_text=None, allow_labels=['PER','ORG','LOC','MISC'])
                zone_entity_map[zid] = {
                    'id': zid,
                    'name': zone.get('name'),
                    'rect': rect_rel,
                    'rect_px': pxbox,
                    'weight': zone.get('weight', 1.0),
                    'text': text,
                    'entities': ents
                }
            # evaluate quality
            if evaluate_template_quality(zone_entity_map, cfg):
                chosen_result = zone_entity_map
                chosen_template = tmpl
                break
            else:
                continue

        # if none passed, pick last tried
        if chosen_result is None:
            chosen_result = zone_entity_map
            chosen_template = tmpl

    merged = score_and_merge_zone_entities(chosen_result, chosen_template)

    # build full_text by concatenating zone texts in reading order (template order)
    full_text_parts = []
    # If density detection was used, chosen_template may not have a 'zones' list; iterate chosen_result in order
    if isinstance(chosen_template, dict) and chosen_template.get('id') == 'density':
        for zid in sorted(chosen_result.keys()):
            full_text_parts.append(chosen_result[zid].get('text', ''))
    else:
        for z in chosen_template.get('zones', []):
            zid = z['id']
            if zid in chosen_result:
                full_text_parts.append(chosen_result[zid].get('text', ''))
    full_text = "\n\n".join([p for p in full_text_parts if p])

    # close doc
    try:
        doc.close()
    except Exception:
        pass

    zone_results = {
        'template_id': chosen_template.get('id'),
        'template_name': chosen_template.get('name'),
        'zones': list(chosen_result.values()),
        'merged_entities': merged
    }

    return full_text, zone_results


def merge_single_line_blocks(zones, page_w, page_h, height_tol=0.25, x_tol=0.05, max_vertical_gap_multiplier=2.0, max_line_height=48):
    """Merge single-line text boxes into multi-line blocks.

    Heuristic merge rules (simple and deterministic):
      - Consider boxes whose pixel-height <= max_line_height as single-line candidates
      - Group vertically adjacent candidates when:
        * Heights are similar within height_tol (relative)
        * Left x positions are within x_tol fraction of page width
        * Vertical gap between consecutive lines <= max_vertical_gap_multiplier * max(line_heights)

    Returns a new list of zones with merged entries. Keeps non-candidate zones unchanged.
    """
    if not zones:
        return zones

    # Prepare indexed candidates with pixel coords
    items = []
    for i, z in enumerate(zones):
        try:
            x0, y0, x1, y1 = [int(v) for v in z.get('rect_px', (0,0,0,0))]
        except Exception:
            # fallback to normalized rect
            rx0, ry0, rx1, ry1 = z.get('rect', [0,0,0,0])
            x0 = int(round(rx0 * page_w))
            y0 = int(round(ry0 * page_h))
            x1 = int(round(rx1 * page_w))
            y1 = int(round(ry1 * page_h))
        h = max(1, y1 - y0)
        items.append({
            'idx': i,
            'orig': z,
            'x0': x0,
            'y0': y0,
            'x1': x1,
            'y1': y1,
            'w': max(1, x1 - x0),
            'h': h,
        })

    # Split candidates (single-line heuristics) and others
    candidates = [it for it in items if it['h'] <= max_line_height]
    others = [it for it in items if it['h'] > max_line_height]

    # Sort candidates top-to-bottom
    candidates.sort(key=lambda it: (it['y0'], it['x0']))

    used = set()
    merged_results = []

    for i, it in enumerate(candidates):
        if it['idx'] in used:
            continue
        group = [it]
        used.add(it['idx'])
        last = it
        # try to attach following candidates as long as they meet the criteria
        for j in range(i+1, len(candidates)):
            other = candidates[j]
            if other['idx'] in used:
                continue
            # vertical gap (other top - last bottom)
            gap = other['y0'] - last['y1']
            if gap < 0:
                gap = 0
            allowed_gap = max_vertical_gap_multiplier * max(last['h'], other['h'])
            if gap <= allowed_gap:
                # height similarity (relative)
                max_h = max(last['h'], other['h'])
                if abs(last['h'] - other['h']) <= height_tol * max_h:
                    # left x similarity (absolute pixels, tolerance relative to page width)
                    if abs(last['x0'] - other['x0']) <= max(2, int(round(x_tol * page_w))):
                        group.append(other)
                        used.add(other['idx'])
                        last = other
                        continue
            # if it doesn't match, do not skip further ones — but break when gap becomes very large
            # (since sorted by y, further entries will only be further down). Use a conservative break.
            if other['y0'] - it['y1'] > max_vertical_gap_multiplier * max(it['h'], other['h']) * 4:
                break

        if len(group) == 1:
            # keep original zone
            merged_results.append(it['orig'])
        else:
            # merge group into a single zone
            x0 = min(g['x0'] for g in group)
            y0 = min(g['y0'] for g in group)
            x1 = max(g['x1'] for g in group)
            y1 = max(g['y1'] for g in group)
            rect_px = (int(x0), int(y0), int(x1), int(y1))
            rect = [x0 / float(page_w), y0 / float(page_h), x1 / float(page_w), y1 / float(page_h)]
            area = int((x1 - x0) * (y1 - y0))
            # build merged zone based on first original entry but update rects/scores
            base = group[0]['orig'].copy()
            base['rect_px'] = rect_px
            base['rect'] = rect
            base['area'] = area
            try:
                base['score'] = float(area)
            except Exception:
                base['score'] = area
            merged_results.append(base)

    # append non-candidate zones unchanged
    for o in others:
        merged_results.append(o['orig'])

    return merged_results
