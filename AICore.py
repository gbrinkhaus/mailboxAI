from PIL import Image
import pytesseract
from pdf2image import convert_from_path
from PyPDF2 import PdfReader
import fitz
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
def getPDFContents(filename, workdir, password=None):
    """
    Extract text from PDF. If the PDF is encrypted, attempt decryption using
    the provided password. If no password is provided and the PDF is encrypted,
    raise a ValueError('encrypted').

    Returns the extracted text (possibly via OCR fallback).
    """
    try:
        reader = PdfReader(filename)
    except Exception as e:
        raise

    # Handle encrypted PDFs
    if hasattr(reader, 'is_encrypted') and reader.is_encrypted:
        # If a password is provided, try to decrypt
        if password:
            try:
                # PyPDF2: decrypt returns 0 if failed, 1 if success
                decrypted = False
                try:
                    res = reader.decrypt(password)
                    decrypted = (res == 1 or res == True)
                except TypeError:
                    # Some PyPDF2 versions return int, others bool
                    decrypted = bool(reader.decrypt(password))

                if not decrypted:
                    raise ValueError('bad_password')
            except Exception:
                raise ValueError('bad_password')
        else:
            # Signal to caller that a password is required
            raise ValueError('encrypted')

    retstr = ""
    for page in reader.pages:
        # Some pages may return None from extract_text()
        txt = page.extract_text()
        if txt:
            retstr += txt + "\n\n"
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
