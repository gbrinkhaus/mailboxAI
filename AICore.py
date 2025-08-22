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
