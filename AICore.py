from PIL import Image
import pytesseract
from pdf2image import convert_from_path
from PyPDF2 import PdfReader
import numpy
import json
from helperfuncs import *


def write_PDFpreview(filename, prevfile):
    # Import pdf file + write to preview  
    pages = convert_from_path(filename, dpi=100, fmt="jpeg", last_page=1)  
    pages[0].save(prevfile, 'JPEG')  
    return


def getPDFOCR(filename, workdir, pagenr):
    # Pt.1: Import pdf file  
#    pages = convert_from_path(filename, dpi=150, output_folder=workdir, fmt="jpeg", 
#        jpegopt={'quality':90,'progressive':False,'optimize':False})  
#    pages = convert_from_path(filename, dpi=200, fmt="jpeg", grayscale=True, output_folder=workdir, 
#        jpegopt={'quality':90,'progressive':False,'optimize':False})  
#    print(pytesseract.get_tesseract_version()) 
#    page = convert_from_path(filename, dpi=200, fmt="jpeg", grayscale=True, first_page=pagenr, last_page=pagenr, 
#        jpegopt={'quality':90,'progressive':False,'optimize':True})[0]  

    page = convert_from_path(filename, dpi=200, output_folder=workdir, fmt="ppm", grayscale=True, first_page=pagenr, last_page=pagenr)[0]  

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
def getPDFContents(filename, workdir):
    reader = PdfReader(filename)
    retstr = ""

    for page in reader.pages:
         retstr += page.extract_text() + "\n\n"
    npages = len(reader.pages)

    # if file has no contents (newline=2chars), create via OCR
    if len(retstr) < npages * 3:
        retstr = ""
        for pagenr in range(1, npages+1 ):
            retstr += getPDFOCR(filename, workdir, pagenr)

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
    retval = 0.0
    match1 = []
    match2 = []

    if array1 and array2:
        allids = [ x['id'] for x in array1 ] + [ x['id'] for x in array2 ]
        allids = set(allids) # deduplicate
        allids = sorted(allids)

        for id in allids:
            found = 0
            for val in array1:
                if val['id'] == id:
                    found = val['occ']
                    break
            match1.append( found )

            found = 0
            for val in array2:
                if val['id'] == id:
                    found = val['occ']
                    break
            match2.append( found )

        # maxlen = max(len(a1), len(a2))
        # # bring both to same length
        # for i in range(len(a1), maxlen):
        #     a1.append(-1)
        # for i in range(len(a2), maxlen):
        #     a2.append(-1)

        retval = cos_sim(match1, match2)
        if retval:
            sPrint("similarity", match1, match2, retval)

    return retval

# Find fingerprint of best matching document ******************
def getBestTagMatch(foundtags, app):
    foundfile = {}
    bestsimil = 0

    dbfilelist = app.dbhandler.getallDBfiles(app.localcfg['targetpath'], False)
    for file in dbfilelist:
        if file['tags']:
            rectags = json.loads(file['tags'])
            a = vsmSimilarity(foundtags, rectags)
            sPrint("checked file: ", file)
            if a > bestsimil:
                bestsimil = a
                foundfile = file
                sPrint("!! found new best hit.")

    # fullarray = []
    # retarray = []
    # bestfound = 0s
    # currentfile = -1
    # # compress to one file + array of tags
    # for filetag in app.filestotags:
    #     if filetag[0] != currentfile:
    #         taglist = list(filter(lambda x: x[0] == filetag[0], app.filestotags))
    #         currentfile = filetag[0]

    #         tagarray = []
    #         patharray = []
    #         for tag in taglist:
    #             tagarray.append(tag[1])
    #             patharray.append(tag[2])
                
    #         fullarray.append([ currentfile, tagarray, patharray ])
        
    # # iterate over all files
    # for file in fullarray:
    #     found = 0
    #     for tag in file[1]:
    #         if tag in foundtags:
    #             found += 1

    #     # we should only store if more than 1 hit
    #     if found > bestfound:
    #         bestfound = found
    #         retarray = list(filter(lambda x: x[0] == file[0], fullarray))

    return foundfile



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
