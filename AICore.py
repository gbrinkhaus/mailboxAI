from PIL import Image
import pytesseract
from pdf2image import convert_from_path
import pymupdf as fitz
import numpy
import json
from helperfuncs import *
import os
import re
import string
from types import SimpleNamespace


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

    # remove typical leading words like 'von', 'an', 'an:' etc and dates fragments
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



''' Tried to fix image because of constant troubles with jpeg - to no avail - ppm does work

def detect_and_fix(img_path):
    # detect for premature ending
    try:
        with open( img_path, 'rb') as im :
            im.seek(-2,2)
            if im.read() == b'\xff\xd9':
                print('Image OK :', img_path) 
            else: 
                # fix image
                img = cv2.imread(img_path)
                cv2.imwrite( img_path, img)
                print('FIXED corrupted image :', img_path)           
    except(IOError, SyntaxError) as e :
      print(e)
      print("Unable to load/write Image : {} . Image might be destroyed".format(img_path) )
'''
