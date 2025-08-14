import os, shutil, sqlite3, json
from pathlib import Path
import uuid    
import dbhandler
from threading import Timer
from subprocess import call as callOS
import unicodedata
from flask import flash

debugmode = False

# general helper funcs *********************************************************************

# print msgs for debugging only *********************
def sPrint(*args):
    if debugmode:
        for ar in args:
            print(ar)

# python has an umlaut bug
def compare_str(s1, s2):
    def NFD(s):
        return unicodedata.normalize('NFD', s)
    return NFD(s1) == NFD(s2)

# make sure to not return true if searching for empty string
def safeFind(whattofind, where):
    if not whattofind:
        return []
    
    # Find all starting positions of exact matches
    matches = []
    len_what = len(whattofind)
    len_where = len(where)
    
    for i in range(len_where - len_what + 1):
        if compare_str(where[i:i+len_what], whattofind):
            matches.append(i)
            
    return matches

def isStopTag(tag):
    return len(safeFind("!!--STOP--!!", tag['texthints'])) > 0


# find specific key/values in list
def findInMultiList(whattofind, findin, keyarray):
    if len(whattofind) < 1 or len(findin) < 1 or len(keyarray) < 1:
        return -1

    #print(type(whattofind))
    #print(type(findin))
    #print(type(keyarray))

    evaltype = type(findin)
    
    # if evaltype == "list" and type(keyarray[0] != "num"):
    #    print("findInMultiList: tpye mismatch for list")
    #    return -1

    for rowid, row in enumerate(findin):
        found = True

        for keynr, thekey in enumerate(keyarray):
            if evaltype is list:
                if whattofind[thekey] != row[thekey]:
                    found = False
            elif evaltype is dict:
                if whattofind[thekey] != row[thekey]:
                    found = False
            else:
                if getattr(whattofind, thekey) != getattr(row, thekey):
                    found = False

        if found:
            return rowid
           
    return -1

# remove duplicates from list
def deduplicate(multilist, keyarray):
    newarray = []
    for row in multilist:
        if findInMultiList(row, newarray, keyarray) == -1:            
            newarray.append(row)

    return newarray



# general file funcs *********************************************************************

# create a path that always starts and never ends with "/" 
def cleanPath(path):
    result = ""

    if path is None or len(path) == 0: return result
    if path[0] != "/": result = "/"

    if path[-1] != "/":
        result = result + path
    else:
        result = result + path[:-1]

    return result


# load all local files in a path FROM LOCAL PATH
# relpath is there to track the relative path within the folder structure
def getLocalFiles(path, relpath, withsubfolders):
        # this would be used to track via handing out the original path: 
        # relpath = f.path[len(path)-1:] 
        filelist = []

        if path:
            for f in os.listdir(path):
                filetype = 'other'
                fullfile = path + '/' + f

                if os.path.isdir(fullfile) and withsubfolders:
                    filetype = 'DIR'
                    subdir = getLocalFiles(fullfile, relpath+'/'+f, withsubfolders)
                    for file in subdir:
                        filelist.append( file )

                if f.endswith('.pdf'):
                    filetype = 'pdf'

                filelist.append( { 'name': f, 'type': filetype, 'size': os.path.getsize(fullfile), "path": path, "relpath": relpath +'/'+f } )

        return sorted(filelist, key=lambda k: k['type'] + k['name'])


# config file funcs *********************************************************************
def load_config(datapath):
    configfile = datapath + "/config.json"
    if not os.path.isfile(configfile):
        shutil.copy("./templates/config.json", configfile)

    with open(configfile) as json_data_file:
        data = json.load(json_data_file)
    
    # standard presets
    if not 'targetpath' in data:
        data['targetpath'] = ""
    else:
        data['targetpath'] = cleanPath(data['targetpath'])

    if not 'sourcepath' in data:
        data['sourcepath'] = ""
    else:
        data['sourcepath'] = cleanPath(data['sourcepath'])

    if not 'levelstructure' in data:
        data['levelstructure'] = [  { 'id': 0, 'short': 'L1', 'descr': 'Level 1 - Main folder' },
                                    { 'id': 1, 'short': 'L2', 'descr': 'Level 2 - 2nd topic' },
                                    { 'id': 2, 'short': 'L3', 'descr': 'Level 3 - Person or specific topic' } ]

    # decide whether processed files are to be deleted
    if not 'movefiles' in data:
        data['movefiles'] = False
    data['movechanged'] = False

    return data


def write_config(cfg, datapath):
    with open(datapath + "/config.json", "w") as outfile:
        json.dump(cfg, outfile)


# Other app funcs **********************************************************************

# basic, one-time app init
def initApp(app):
    global debugmode
    debugmode = app.config['DEBUG']
    app.config['SECRET_KEY'] = 'uzN0y47GYdi8bFdLjYfqktxbMHUORlPp'
    app.nerEnts = [["MISC", "Topics"], ["PER", "Persons"], ["ORG", "Organisations"], ["LOC", "Locations"]]
    app.initMessages = ""
    
    app.datapath = os.path.expanduser("~/Library/Application Support/mailboxAI")
    if debugmode:
        app.datapath += "_DEV"

    app.workdir = app.datapath + "/.appcache/"
    if not os.path.exists(app.workdir):
        Path(app.workdir).mkdir(parents=True, exist_ok=True)

    app.localcfg = load_config(app.datapath)
    app.maxlevels = 3
    app.dbhandler = dbhandler.dbhandler()

    if not app.dbhandler.establish_db(app.localcfg['targetpath']):
        app.initMessages += "Database not found. New, empty database was created."

    app.isInitialized = isInitialized(app)
    app.filter = {"FILE": "", "DATE": ""}
    app.filterstring = ""

    # store current Document for modal on docs page
    app.currentDocument = "no file selected"

    # clear cache folder
    for f in os.listdir(app.workdir): os.remove(os.path.join(app.workdir, f))

    # the target fodler is stored in DB with a machine ID, unique for each machine
    macid = str(uuid.UUID(int=uuid.getnode()))
    print("Machine ID: " + macid)

    def open_browser():
        url = "http://127.0.0.1:8080"
        if debugmode:
            url = "http://127.0.0.1:5001"
        
        callOS(["open", "-a", "Google Chrome", "-n", url])

    Timer(5, open_browser).start()

    return

# check whether app can be used
def isInitialized(app):
    return app.dbhandler.check_db(app.localcfg['targetpath']) and app.localcfg['sourcepath'] != "" and app.localcfg['targetpath'] != ""


# reset app values
def resetApp(app):
    app.filecontents = ""
    app.copyFile = True

    # contains the recognized entitites in an OCR situation
    app.recognizedtags = []
    # contains the confirmed entitites: recognized in OCR + stored in DB
    app.confirmedtags = []
    # contains all stored tags from database
    app.storedtags = app.dbhandler.get_db_tags()
    app.filestotags = app.dbhandler.get_db_content('files_to_tags')

    
    localfilelist = getLocalFiles(app.localcfg['targetpath'], "", True)
    app.docfilelist = sorted(localfilelist, key=lambda x: x['path'])
    # contains all folders with documents
    app.subfolders = [[],[],[]]

    # contains the recognized dates
    app.datetags = []
    app.levels = []
    app.files = []
    app.currenttags = []
    
    # store file info for OCR + processing
    app.currentfile = ""
    app.fullfilename = ""
    app.dateonly = ""
    app.topicnameonly = ""
    app.fullpathplusname = ""

    app.prevfile = "./static/images/preview.jpg"
    if os.path.isfile(app.prevfile): os.remove(app.prevfile)
    shutil.copy(app.prevfile + ".bak", app.prevfile)
    return


# ========================= Batch Split (Marker-based) Utilities =========================
# These helpers provide a deterministic way to split a PDF by recognizing
# intentionally inserted separator pages. The separator is a generated marker
# image/PDF stored under the app's datapath and matched via perceptual hash.

import io
import math
from typing import List, Tuple

from PIL import Image, ImageDraw, ImageFont
from pdf2image import convert_from_path
from PyPDF2 import PdfReader, PdfWriter


def ensure_marker_assets(app) -> dict:
    """Ensure a default marker image and PDF exist in app.datapath.

    Returns a dict with paths: { 'png': <path>, 'pdf': <path> }.
    """
    marker_png = os.path.join(app.datapath, "marker_newdoc.png")
    marker_pdf = os.path.join(app.datapath, "marker_newdoc.pdf")

    # Create PNG if missing
    if not os.path.isfile(marker_png):
        img_w, img_h = 1654, 2339  # ~A4 at 200 DPI
        img = Image.new("RGB", (img_w, img_h), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)

        # Draw a bold border and a large X pattern to be robust for scanning
        border = 60
        draw.rectangle([border, border, img_w - border, img_h - border], outline=(0, 0, 0), width=15)
        draw.line((border, border, img_w - border, img_h - border), fill=(0, 0, 0), width=12)
        draw.line((img_w - border, border, border, img_h - border), fill=(0, 0, 0), width=12)

        # Title text
        text = "MAILBOXAI NEW DOCUMENT SEPARATOR"
        try:
            # Use a generic font if available; fallback to default
            font = ImageFont.truetype("Arial.ttf", 80)
        except Exception:
            font = ImageFont.load_default()
        tw, th = draw.textsize(text, font=font)
        draw.text(((img_w - tw) / 2, img_h * 0.45), text, fill=(0, 0, 0), font=font)

        # Instruction line
        sub = "Insert this page between letters to split the batch"
        try:
            subfont = ImageFont.truetype("Arial.ttf", 40)
        except Exception:
            subfont = ImageFont.load_default()
        sw, sh = draw.textsize(sub, font=subfont)
        draw.text(((img_w - sw) / 2, img_h * 0.55), sub, fill=(0, 0, 0), font=subfont)

        img.save(marker_png, format="PNG")

    # Create single-page PDF if missing
    if not os.path.isfile(marker_pdf):
        img = Image.open(marker_png)
        rgb = img.convert("RGB")
        rgb.save(marker_pdf, "PDF", resolution=200.0)

    return {"png": marker_png, "pdf": marker_pdf}


def rasterize_pdf_pages(pdf_path: str, dpi: int = 150, max_pages: int = None) -> List[Image.Image]:
    """Rasterize PDF pages to PIL Images using pdf2image.
    Returns a list of PIL Images. Optionally limit to max_pages for previews.
    """
    if not os.path.isfile(pdf_path):
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    pages = convert_from_path(pdf_path, dpi=dpi)
    if max_pages:
        pages = pages[:max_pages]
    return pages


def _dct_2d(matrix: List[List[float]]) -> List[List[float]]:
    """Compute a 2D DCT (type II) of a square matrix (list of lists)."""
    N = len(matrix)
    result = [[0.0] * N for _ in range(N)]
    for u in range(N):
        for v in range(N):
            sum_val = 0.0
            for i in range(N):
                for j in range(N):
                    sum_val += matrix[i][j] * math.cos(((2 * i + 1) * u * math.pi) / (2 * N)) * math.cos(((2 * j + 1) * v * math.pi) / (2 * N))
            c_u = math.sqrt(1 / N) if u == 0 else math.sqrt(2 / N)
            c_v = math.sqrt(1 / N) if v == 0 else math.sqrt(2 / N)
            result[u][v] = c_u * c_v * sum_val
    return result


def compute_phash(image: Image.Image, hash_size: int = 8, highfreq_factor: int = 4) -> int:
    """Compute perceptual hash (pHash) for a PIL image.
    Returns a 64-bit integer (for hash_size=8)."""
    img_size = hash_size * highfreq_factor
    img = image.convert("L").resize((img_size, img_size), Image.Resampling.LANCZOS)
    # Build matrix
    pixels = list(img.getdata())
    matrix = [pixels[i * img_size:(i + 1) * img_size] for i in range(img_size)]
    # 2D DCT
    dct = _dct_2d(matrix)
    # Top-left region
    vals = []
    for x in range(hash_size):
        for y in range(hash_size):
            vals.append(dct[x][y])
    # Exclude DC term at [0,0]
    vals = vals[1:]
    avg = sum(vals) / len(vals)
    bits = 0
    for idx, v in enumerate(vals):
        bits <<= 1
        bits |= 1 if v > avg else 0
    return bits


def phash_distance(h1: int, h2: int) -> int:
    """Hamming distance between two integer pHashes."""
    return bin(h1 ^ h2).count("1")


def find_marker_pages(page_images: List[Image.Image], marker_image: Image.Image, ham_thr: int = 10) -> List[int]:
    """Return zero-based page indices that match the marker image within a Hamming distance threshold."""
    marker_hash = compute_phash(marker_image)
    hits = []
    for idx, img in enumerate(page_images):
        try:
            h = compute_phash(img)
            if phash_distance(marker_hash, h) <= ham_thr:
                hits.append(idx)
        except Exception:
            continue
    return hits


def build_split_points_from_markers(marker_indices: List[int], total_pages: int, include_first: bool = True) -> List[int]:
    """Build split start indices from marker positions. By default page 0 is a split start.
    We treat the page AFTER a marker as a new document start.
    """
    starts = [0] if include_first else []
    for mi in marker_indices:
        if mi + 1 < total_pages:
            starts.append(mi + 1)
    # De-duplicate and sort
    return sorted(set([s for s in starts if 0 <= s < total_pages]))


def split_pdf_by_pages(pdf_path: str, split_starts: List[int], out_dir: str, drop_pages: List[int] = None) -> List[Tuple[str, Tuple[int, int]]]:
    """Split a PDF given start indices. Returns list of (filepath, (start,end)) ranges.
    drop_pages: optional list of page indices to exclude (e.g., marker pages).
    """
    drop_set = set(drop_pages or [])
    reader = PdfReader(pdf_path)
    n = len(reader.pages)
    if not split_starts:
        return []
    split_starts = sorted(set([s for s in split_starts if 0 <= s < n]))
    # Build ranges as [start, next_start) and finalize last to n
    ranges = []
    for i, s in enumerate(split_starts):
        e = split_starts[i + 1] if i + 1 < len(split_starts) else n
        ranges.append((s, e))

    Path(out_dir).mkdir(parents=True, exist_ok=True)
    outputs = []
    base = os.path.splitext(os.path.basename(pdf_path))[0]
    for idx, (s, e) in enumerate(ranges, start=1):
        writer = PdfWriter()
        for p in range(s, e):
            if p in drop_set:
                continue
            writer.add_page(reader.pages[p])
        if len(writer.pages) == 0:
            continue
        outpath = os.path.join(out_dir, f"{base}_part_{idx:03d}.pdf")
        with open(outpath, "wb") as f:
            writer.write(f)
        outputs.append((outpath, (s, e - 1)))
    return outputs


