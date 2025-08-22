import os, shutil, json
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
from datetime import datetime
from typing import List, Tuple

from PIL import Image, ImageDraw, ImageFont
from pdf2image import convert_from_path
import pymupdf as fitz

def split_pdf_by_pages(pathonly: str, filename: str, split_starts: List[int]) -> int:
    """Split a PDF given start indices. Returns list of (filepath, (start,end)) ranges.
    drop_pages: optional list of page indices to exclude (e.g., marker pages)."""

    if not split_starts:
        return 0

    timestamp = datetime.now().strftime("%d%m%y-%H.%M.%S")

    pdf_path = os.path.join(pathonly, filename)
    doc = fitz.open(pdf_path)
    n = doc.page_count

    # first page must be a "virtual" delimiter
    if 0 not in split_starts:
        split_starts.append(0)

    # if last page is not a delimiter, add one at the end
    if n not in split_starts:
        # keep compatibility with original logic which used n+1 sentinel
        split_starts.append(n + 1)

    split_starts = sorted(split_starts)

    success_count = 0
    for idx in range(len(split_starts) - 1):
        # original logic used 1-based page numbers in the output ranges
        start_page_num = 1 + split_starts[idx]
        end_page_num = split_starts[idx + 1] - 1

        # only if there are pages to write
        if end_page_num - start_page_num >= 0:
            outpath = os.path.join(pathonly, f"split_{timestamp}_part{idx:03d}.pdf")

            # create a new PDF and insert the requested pages
            new_doc = fitz.open()
            for page_num in range(start_page_num, end_page_num + 1):
                # convert to 0-based index
                page_index = page_num - 1
                # insert_pdf can copy a range; use from_page==to_page to copy a single page
                new_doc.insert_pdf(doc, from_page=page_index, to_page=page_index)

            # save only if we added pages
            if new_doc.page_count > 0:
                new_doc.save(outpath)
                success_count += 1

            new_doc.close()

    doc.close()
    return success_count


