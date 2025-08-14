# Funcs to get TAG from DB ********************************************************************
def getTagByID(id):
        return list(filter(lambda x: x['id'] == id, app.storedtags))
def getTagsByText(text):
        return list(filter(lambda x: compare_str(x['text'], text), app.storedtags))
def getTagByTypeAndText(type, text):
        return list(filter(lambda x: x['label'] == type and compare_str(x['text'], text), app.storedtags))

# Imports must happen after funcs to avoid recursion ******************************************
import os, shutil, re, signal
from pathlib import Path
from datetime import datetime

from subprocess import call as callOS, Popen
# from numpy import matrix as Matrix

from flask import Flask, render_template, request, url_for, flash, redirect, jsonify, send_file
from PIL import Image

import spacy
import de_core_news_md

import AICore
from helperfuncs import *


# ********** APP INIT **************************************************************************
os.system('clear')

app = Flask(__name__)

initApp(app)
# reset the vars that will be cleaned after each document
resetApp(app)

# load SPACY NLP - remember that lang must also be set in PDFOCR function 
nlp = spacy.load("de_core_news_md") # german
# print(list(spacy.info()['pipelines'].keys()))
# nlp = spacy.load("en_core_web_md") # english


# ********** ROUTES *****************************************************************************

# HOME route ************************
@app.route('/', methods=['GET', 'POST'])
def index():

    # If GET, load page ************************
    if request.method == 'GET':

        # clear app if reset button has been pressed, (thats why it's a json request)
        if request.content_type and request.content_type == 'application/json':
            resetApp(app)

        if app.initMessages != "":
            flash(app.initMessages, "danger")
            app.initMessages = ""

        app.infiles = getLocalFiles( app.localcfg['sourcepath'], "", False )

        return render_template('index.html', appobj=app)

    # when POST, execute OCR on a chosen file ************************
    else:
        resetApp(app)
        callstr = request.get_json()['filename']

        if callstr != '':
            app.fullfilename = callstr
            app.dateonly = ""
            app.topicnameonly = app.fullfilename[0:-4]
            app.fullpathplusname = app.localcfg['sourcepath'] + "/" + callstr

            # get the list of all subfolders so that we can display them in the folder paths
            # goes down 3 levels, hard coded
            subfolders = [[],[],[]]
            localpaths = list(filter(lambda x: x["type"] == 'DIR' and not x['name'][0] == ".", app.docfilelist))
            for dir in localpaths:
                parent = ""
                for x, subdir in enumerate(dir['relpath'].split("/")):
                    if x > 0 and x <= 3:
                        thetag = getTagsByText(subdir)
                        if thetag:
                            dict = {'subdir': subdir, 'parent': parent, 'tag': thetag[0]}
                            if dict not in subfolders[x-1]:
                                subfolders[x-1].append(dict)
                        parent = subdir

            # need both json and object in template - alternative code would be to import json.loads into jinja - both ugly 
            # or, nicer way: use ajax on demand call - will maybe use in the future
            app.subfolders = subfolders
            app.subfolderstring = json.dumps(subfolders)
            
            # sPrint(localpaths, subfolders, app.subfolders)

            # copy file to workdir - this is always done, even if not copied again later
            app.currentfile = app.fullfilename.strip()
            shutil.copyfile(app.fullpathplusname, app.workdir + app.currentfile)
            filename = app.workdir + app.currentfile

            # extract the pdf contents
            AICore.write_PDFpreview(filename, app.prevfile)
            app.filecontents = AICore.getPDFContents(filename, app.workdir)
                
            # app.storedtags are those currently stored in the Database
            # app.recognizedtags are the tags that were recognized for this pdf
            # app.confirmedtags are the tags that are proposed by the file matching
            # app.datetags are the dates found in the text
            
            # find date strings in pdf text and store
            dates = findDatesInText(app.filecontents)
            app.datetags += dates

            # AICore candidate: add all known (stored) database tags that can be found in the text
            ents = []
            for tag in app.storedtags:
                if tag["label"] != "ACTION" and tag["text"] != "" and tag["texthints"] != "":
                    hints = tag['texthints'].split("||")
                    for hint in hints:
                        matches = safeFind(hint, app.filecontents)
                        if matches:  # If there are any matches
                            ents.append({"id": tag["id"], "label": tag["label"], "text": tag["text"], "texthints": tag["texthints"], 'occurence': len(matches)})

            # AICore candidate: do NER on recognized text and double check the results *******************
            nlp = de_core_news_md.load()
            doc = nlp(app.filecontents)
            for ent in doc.ents:
                a = checkEnt(ent)
                if a:
                    matches = safeFind(a['text'], app.filecontents)
                    ents.append({"id": a["id"], "label": a['label'], "text": a['text'], 'occurence': len(matches)})

            # add all the ents to the left field, deduplicated
            app.recognizedtags = deduplicate(ents, ["label", "text"])

            # find the closest match of existing file tags **********************************
            confirmed_ids = getValidTagIDs(app.recognizedtags)
            bestmatch = AICore.getBestTagMatch(confirmed_ids, app)

            if bestmatch:
                filetags = list(filter(lambda x: x[0] == bestmatch['id'], app.filestotags))
                for match in filetags:
                    tag = getTagByID(match[1])
                    # add to confirmedtags, using active field IF the matches from the best file are also in the current file
                    if len(tag) > 0:
                        # if findInMultiList({"label": tag[0]["label"], "text": tag[0]["text"]}, app.recognizedtags, ["label", "text"]) != -1 \
                        #         or len(safeFind(tag[0]['texthints'], app.filecontents)) > 0 or tag[0]["label"] == "ACTION":
                        active = ""
                        if match[2]: 
                            active = "active" 
                        pathlevel = match[2] if match[2] not in (None, -1) else "-"
                        app.confirmedtags.append( { "id": match[1], "label": tag[0]["label"], "text": tag[0]["text"], "pathlevel": pathlevel, "active": active, "texthints": tag[0]["texthints"] } )

        # end of POST method
        return json.dumps({'success':True}), 200, {'ContentType':'application/json'} 


# Pull all valid ids from an array of tags ******************
def getValidTagIDs(tagarray):
    retarray = []
    for tag in tagarray:
        if not tag['id'] == -1 and not isStopTag(tag):
            retarray.append({ 'id': tag['id'], 'occ': tag['occurence'] })

    return retarray


# Check for valid ents ******************
def checkEnt(ent):
    retarray = {}
    check = True

    label = ent.label_.strip().replace("\n", " ")
    text = ent.text.strip().replace("\n", " ")

    # sPrint(text, (text.find("(") > -1) != (text.find(")") > -1))

    # check whether this is a valid tag - not using regex as it got too messy to read
    if len(label) <= 1 or len(text) <= 2 or len(text) > 80 or \
        text.find("|") != -1 or text.find("|") >= 0 or text.find("|") == len(text) or text.find(".") > -1\
        or ((text.find("(") > -1) != (text.find(")") > -1)) \
        or ((text.find("{") > -1) != (text.find("}") > -1)) \
        or ((text.find("[") > -1) != (text.find("]") > -1)):
        check = False 

    id = -1
    tagexists = getTagByTypeAndText(label, text)
    if tagexists:
        # must double check in case we have the same tag as both stop and positive tag
        check = False 
        for tag in tagexists:
            if not isStopTag(tag):
                id = tag['id']
                check = True

        if len(tagexists) > 1:
            sPrint("Found", len(tagexists), "database tags for recognized tag:", text)
        
    
    if check:
        retarray = {"id": id, "label": label, "text": text}

    return retarray


# PROCESS the file ************************************************
@app.route('/processfile', methods=('GET', 'POST'))
def processfile():

    if request.method == 'POST':

        relativefolder = request.form['Hiddenpath']
        targetfolder = app.localcfg['targetpath'] + relativefolder
        app.dateonly = request.form['DT'] 
        app.fullfilename = request.form['FN'] + "-" + app.dateonly + ".pdf"

        if app.currentfile != "" and  app.fullfilename != "": 
            dest = ""
            Path(targetfolder).mkdir(parents=True, exist_ok=True)
            if not os.path.isfile(targetfolder + app.fullfilename):
                dest = shutil.move(app.workdir + app.currentfile, targetfolder + app.fullfilename)
            else:
                flash('File: ' + targetfolder + app.fullfilename + ' already exists! Please choose another filename.', "danger")

            # if pdf file should be removed from input folder, check whether copy has happened
            if app.localcfg['movefiles'] and dest:
                if os.path.isfile(targetfolder + app.fullfilename) :
                    os.remove(app.fullpathplusname)


        hintstring = request.form['Tag-Hints']
        hintarray = json.loads(hintstring)

        # write description file 
        # f_1 = open(targetfolder + filename + "_descr.txt", "a")  
        description = ("Filename: " + app.fullfilename + "\n")
        description += ("Folder: " + targetfolder + "\n")
        description += ("Tags: " + hintstring + "\n")
        description += ("OCR recognition: " + app.filecontents + "\n")

        # prepare all recognized tags that are also in db (meaning they have an id)
        recarray = getValidTagIDs(app.recognizedtags)
        
        # write file into DB
        conn = app.dbhandler.get_db_connection()
        sqlcursor = conn.execute('INSERT INTO files (name, full_path, date, tags, path, description) VALUES (?, ?, ?, ?, ?, ?)', (app.fullfilename, targetfolder, app.dateonly, json.dumps(recarray), relativefolder, description))
        conn.commit()
        fileid = sqlcursor.lastrowid
        conn.close()

        if fileid > 0:
            # Get the original file contents for case-sensitive matching
            file_text = app.filecontents
            
            for hint in hintarray:
                if len(hint) > 0:
                    ent = hint[0]
                    if ent != "FILE" and ent != "DATE":
                        val = hint[1]
                        # if there is a path, store it, otherwise, set to -1
                        if isinstance(hint[2], int) and hint[2]:
                            active = hint[2]
                        else:
                            active = -1
                        
                        # Get or create the tag
                        tagarray = getTagByTypeAndText(ent, val)
                        if len(tagarray) > 0:
                            tagid = tagarray[0]['id']
                        else: 
                            tagid = addTagToDB(ent, val, val)
                        
                        occurrence_count = 0
                        # Count occurrences using safeFind - use the tag text from the first item in tagarray
                        if tagarray and len(tagarray) > 0 and 'texthints' in tagarray[0]:
                            for tag in tagarray[0]['texthints'].split("||"):   
                                matches = safeFind(tag, file_text)
                                # Add the number of matches found
                                occurrence_count += len(matches)
                            
                        # Use the new method to add tag with the actual occurrence count
                        app.dbhandler.add_tag_to_file(fileid, tagid, active, occurrence_count)
                        
                        if app.debug:
                            print(f"Added tag: {val} (ID: {tagid}) with {occurrence_count} occurrences")

        flash('File ' + app.fullfilename + ' written!', "success")
        resetApp(app)

    return redirect(url_for('index'))


# DOCS route ******************
@app.route('/documents', methods=('GET', 'POST'))
def documents():
            
    resetApp(app)
    dbfilelist = app.dbhandler.getallDBfiles(app.localcfg['targetpath'], False)

    allpaths = []
    latest_id = 0

    # go through all files on the hard drive
    for file in app.docfilelist:
        validFile = file['type'] == "pdf"
        id = 0

        if validFile:
            file['tagarray'] = []

            # look whether there is a corresponding file in the DB
            retarray = list(filter(lambda x: compare_str(cleanPath(x['full_path']), cleanPath(file['path'])) and compare_str(x['filename'], file['name']), dbfilelist))

            # debug
            # for x in dbfilelist:
            #     if x['filename'] == file['name']:
            #         sPrint(x['full_path'], file['path'], x['filename'], file['name'])
            #         sPrint(retarray)

            # if so, search for the corresponding tags and add all to the file info
            if len(retarray) > 0:
                thisfile = {'db_id': retarray[0]['id'], 'db_date': retarray[0]['date'] }
                tagidarray = list(filter(lambda x: x['file_id'] == thisfile['db_id'], app.filestotags))
                tagarray = []
                for tagid in tagidarray:
                    #in stored tags, every tag should only appear once - still, check:
                    array2 = getTagByID(tagid['tag_id'])
                    if len(array2) > 0:
                        tagarray.append({'label': array2[0]['label'], 'text': array2[0]['text'], 'texthints': array2[0]['texthints']})
                
                thisfile.update({'tagarray': tagarray})
                file.update(thisfile)
            # if no file in DB, note it
            else:
                file['db_id'] = -1


            # if file in filter, store the file info in the app's filelist
            for x, thefilter in enumerate(app.filter):
                value = app.filter[thefilter]
                if value != '':
                    # sPrint(thefilter, value)
                    # if date or filename, see whether any filter cond is NOT met
                    if (thefilter == 'FILE' and file['name'].find(value) == -1) or \
                       (thefilter == 'DATE' and file['db_date'].find(value) == -1):
                          validFile = False
                    # if searching in tags, see whether any filter cond is met
                    elif thefilter != 'FILE' and thefilter != 'DATE': # and hasattr(file, 'tagarray'):
                        # tagarray = json.loads(value)
                        for tag in value: 
                            found = list(filter(lambda x: x['label'] == thefilter and x['text'] == tag, file['tagarray']))
                            if not found:
                                validFile = False
                
            if validFile: 
                app.files.append(file)

                # prepare the path info for the app's path list
                subpath = file['path'].replace(app.localcfg['targetpath'], "")
                file['splitpath'] = [x for x in subpath.split("/") if x]
                parent = ""
                for idx, part in enumerate(file['splitpath']):
                    if idx < app.maxlevels:
                        found = list(filter(lambda x: x['subpath'] == part and x['parent'] == parent, allpaths))
                        if not found:
                            allpaths.append({ 'id': latest_id, 'parent': parent, 'subpath': part, 'level': idx})
                            parent += "/" + str(latest_id)
                        else:
                            parent = str(found[0]['parent']) + "/" + str(found[0]['id'])
                            
                        latest_id += 1
            
    app.allpaths = allpaths

    return render_template('documents.html', appobj=app)


# Select a document to be the one that is selected in the document file modal ************
@app.route('/selectDocument', methods=('GET', 'POST'))
def selectDocument():
    if request.method == 'POST':

        fullpath = request.get_json()
        thedoc = list(filter(lambda x: x['path']+"/"+x['name'] == fullpath, app.files))
        app.currentDoc = thedoc[0]
        app.proposedtags = app.storedtags

        popctr = 0
        for x in range(len(app.proposedtags)):
            y = x - popctr
            id = findInMultiList({"label": app.proposedtags[y]["label"], "text": app.proposedtags[y]["text"]}, app.currentDoc['tagarray'], ["label", "text"])
            if id != -1:
                app.proposedtags.pop(y)
                popctr += 1
        
    return render_template('fileModalContents.html', appobj=app)


# Select a document to be the one that is selected in the document file modal ************
@app.route('/addFileToDB', methods=('GET', 'POST'))
def addFileToDB():
    if request.method == 'POST':

        fileobj = request.get_json()
        fullpathandname = fileobj['path']+"/"+fileobj['name']
        # fileobj contains relative path WITH filename
        relpath = fileobj['relpath'][0:fileobj['relpath'].rfind("/")+1]
        date = findDatesInText(fileobj['name'])
        if date:
            date = date[0][1]
        else:
            stamp = datetime.fromtimestamp(os.path.getmtime(fullpathandname))
            # Format the date in German format (DD.MM.YYYY)
            date = stamp.strftime("%d.%m.%Y")

        # write description file 
        # f_1 = open(targetfolder + filename + "_descr.txt", "a")  
        description = ("Filename: " + fileobj['name'] + "\n")
        description += ("Folder: " + fileobj['path'] + "\n")
        description += ("Tags: " + json.dumps(fileobj['tagarray']) + "\n")
        description += ("OCR recognition: " + "unknown" + "\n")

        # write file into DB
        conn = app.dbhandler.get_db_connection()
        sqlcursor = conn.execute('INSERT INTO files (name, full_path, date, tags, path, description) VALUES (?, ?, ?, ?, ?, ?)', (fileobj['name'], fileobj['path'], date, "", relpath, description))
        conn.commit()
        fileid = sqlcursor.lastrowid
        conn.close()

        app.dbhandler.addMissingFolderTags(app, fileid, relpath)
        resetApp(app)

    return json.dumps({'success':True}), 200, {'ContentType':'application/json'} 


# check and add the missing tags for ONE file ************
@app.route('/checkTags', methods=('GET', 'POST'))
def checkTags():
    if request.method == 'POST':
        fileobj = request.get_json()
        relpath = fileobj['relpath'][0:fileobj['relpath'].rfind("/")+1]
        app.dbhandler.addMissingFolderTags(app, fileobj['db_id'], relpath)
        success = True

    return json.dumps({'success':success}), 200, {'ContentType':'application/json'}


# check DB integrity for All files 
@app.route('/checkAllTagIntegrity', methods=('GET', 'POST'))
def checkAllTagIntegrity():
    if request.method == 'POST':
        # go over files to tags relation list
        dbfilelist = app.dbhandler.getallDBfiles(app.localcfg['targetpath'], True)
        for file in dbfilelist:
            app.dbhandler.addMissingDBTags(app, file)

    success = True
    return json.dumps({'success':success}), 200, {'ContentType':'application/json'}


@app.route('/rebuildFilesTags', methods=('POST',))
def rebuildFilesTags():
    """Repair action: rebuild compact tags vector for all files."""
    app.dbhandler.rebuild_all_files_tags()
    return json.dumps({'success': True}), 200, {'ContentType': 'application/json'}


# Find any type of date in a text ************
def findDatesInText(text):
    retarray = []
    dtarray = re.findall(r'\d{1,2}\.\d{1,2}\.\d{2,4}', text)
    dtarray = deduplicate(dtarray, [0])
    
    for date in dtarray:
        retarray.append( [ "DATE", date ] )

    return retarray


# Remove a tag from a file ************
@app.route('/deleteTagToFile', methods=('GET', 'POST'))
def deleteTagToFile():
    if request.method == 'POST':
        id = request.get_json()['id']
        text = request.get_json()['tag']
        label = request.get_json()['label']

        thetag = getTagByTypeAndText(label, text)
        success = False

        if thetag:
            conn = app.dbhandler.get_db_connection()
            conn.execute('DELETE FROM files_to_tags WHERE file_id = ? AND tag_id = ?', (id, thetag[0]['id']))
            conn.commit()
            conn.close()
            success = True

    return json.dumps({'success':success}), 200, {'ContentType':'application/json'} 


# Add a tag to a file ************
@app.route('/addTagToFile', methods=('GET', 'POST'))
def addTagToFile():
    if request.method == 'POST':
        id = request.get_json()['id']
        text = request.get_json()['tag']
        label = request.get_json()['label']

        thetag = getTagByTypeAndText(label, text)

        success = False
        if thetag:
            app.dbhandler.writeTagToFile(id, thetag[0]['id'], -1)
            success = True

    return json.dumps({'success':success}), 200, {'ContentType':'application/json'} 


# Open folder at location ************
@app.route('/openLocation', methods=('GET', 'POST'))
def openLocation():

    if request.method == 'POST':
        location = request.get_json()['loc']
        fullpath = request.get_json()['fullpath']
        path = ""
        if fullpath:
            path += location
        else:
            path += app.localcfg['targetpath'] + location

        if path == "":
            callOS(["open", os.path.expanduser("~")])
        elif not os.path.exists(path):
            flash('Invalid path: ' + path, "danger")
            return "Path not found", 404
        else:
            callOS(["open", "-R", path])

    return render_template('documents.html', appobj=app)


# DOCS route ******************
@app.route('/howto', methods=('GET', 'POST'))
def howto():
            
    return render_template('howto.html', appobj=app)


# Add a level ************
@app.route('/setFilter', methods=('GET', 'POST'))
def setFilter():
    # sPrint('setLevel!')

    if request.method == 'POST':
        app.filterstring = json.dumps(request.get_json())
        app.filter = request.get_json()

    # return render_template('documents.html', appobj=app)
    return json.dumps({'success':True}), 200, {'ContentType':'application/json'} 


# Route to ADD a TAG to the DB from Javascript***********************************************
@app.route('/addTag', methods=('GET', 'POST'))
def addTag():
    sPrint('addTag route!')

    if request.method == 'POST':
        jsonobj = request.get_json()

        addTagToDB(jsonobj['type'], jsonobj['text'], jsonobj['hint'])

    # Return the type of tag in order to be able to act on it **********
    return json.dumps({'success':True}), 200, {'ContentType':'application/json'} 


# Func to ADD a TAG to the DB ***********************************************
def addTagToDB(type, text, texthints):
    newhints = ""
    conn = app.dbhandler.get_db_connection()

    # Insert the TAG into DB **********
    currenthints = getTagByTypeAndText(type, text)
    otherhints = getTagsByText(text)
    newhints = texthints
    hint_id = -1

    ## IF tag already exists with another label, warn
    if len(otherhints) > 1 or (len(otherhints) == 1 and otherhints[0]['label'] != type and type != "ACTION"):
        return hint_id 

    result = conn.execute('SELECT * FROM tags WHERE tag = ? AND type = ? AND tag IS NOT NULL', ( text, type )).fetchall()
    if len(result) > 0:
        dbid = result[0]['id']
        if not len(currenthints) > 0:
            print("mismatch in storedtags, tag not found ", text, type)
            return hint_id 

    ## IF tag already exists in database, but hint not, then UPDATE
    if len(currenthints) > 0:
        # append the new hint to the existing hints if appropriate
        id = currenthints[0]['id']
        if type != "ACTION":
            newhints = currenthints[0]['texthints']
            if not texthints in newhints.split("||"): 
                newhints += "||" + texthints

        conn.execute('UPDATE tags SET texthints = ? WHERE id = ?', (newhints, id))

    ## IF tag not exists in database, INSERT it
    else:
        if not len(result) > 0:
            # Insert and get the new tag's ID
            cursor = conn.execute('INSERT INTO tags (type, tag, texthints) VALUES (?, ?, ?)', 
                               (type, text, newhints))
            hint_id = cursor.lastrowid
        else:
            print("mismatch in storedtags, tag found in db but not storedtags", text, type)
            # If we got here, we found a matching tag in result
            hint_id = result[0]['id']
    
    # For existing tags, we should have the ID from currenthints
    if len(currenthints) > 0:
        hint_id = currenthints[0]['id']
    
    conn.commit()
    conn.close()

    # Add the tag ID to current tags if it's not already there
    if hint_id != -1 and hint_id not in app.currenttags:
        app.currenttags.append(hint_id)

    app.storedtags = app.dbhandler.get_db_tags()
    return hint_id 


# Toggle move file settings ************
@app.route('/movesettings', methods=('GET', 'POST'))
def movesettings():
    if request.method == 'POST':
        app.localcfg['movefiles'] = request.get_json()['movesetting']
        app.localcfg['movechanged'] = True

    return json.dumps({'success':True}), 200, {'ContentType':'application/json'} 


# Edit app settings ************
@app.route('/settings', methods=('GET', 'POST'))
def settings():

    if request.method == 'POST':
        success = True

        # get paths from imnputs 
        newtarget = cleanPath(request.form['targetdir'])
        newsource = cleanPath(request.form['sourcedir'])

        # only act if something has changes
        targetchanged = newtarget != app.localcfg['targetpath']
        sourcechanged = newsource != app.localcfg['sourcepath']
        movechanged = app.localcfg['movechanged']

        # make sure that valid folders are selected
        
        if targetchanged:
            if not os.path.exists(newtarget):
                success = False
            else:
                if app.dbhandler.establish_db(app.localcfg['targetpath'], newtarget):
                    app.localcfg['targetpath'] = newtarget                
                    success = True

        if sourcechanged:
            if not os.path.exists(newsource):
                success = False
                flash('Invalid source path: ' + newsource, "danger")
            else:
                app.localcfg['sourcepath'] = newsource

            app.isInitialized = isInitialized(app)

        if (targetchanged or movechanged or sourcechanged) and success:
            if targetchanged: flash('Target path changed to: ' + app.localcfg['targetpath'], "success")
            if sourcechanged: flash('Source path changed to: ' + app.localcfg['sourcepath'], "success")
            if movechanged: flash('File move changed to: ' + str(app.localcfg['movefiles']), "success")
            write_config(app.localcfg, app.datapath)

        else:
            if not os.path.exists(newtarget): flash('Invalid target path: ' + newtarget, "danger")
            if not os.path.exists(newsource): flash('Invalid source path: ' + newsource, "danger")
            if not os.path.exists(app.dbhandler.get_db_file(newtarget)): 
                flash('No success copying database file to: ' + app.dbhandler.get_db_file(newtarget), "danger")
            else:
                flash('Database file already present at: ' + app.dbhandler.get_db_path(newtarget), "danger")
            if not (targetchanged or movechanged or sourcechanged): flash('No changes detected - config not written', "danger")

    return render_template('settings.html', appobj=app)


# FS listing API for folder picker **************************************************************
@app.route('/api/fs/list', methods=['GET'])
def api_fs_list():
    """List subdirectories of a given path for the folder picker.

    Query params:
      - path (optional): absolute or ~-expanded path. Defaults to user home.
      - include_hidden (optional): if truthy (1,true,yes), do NOT filter hidden/system entries

    Returns JSON:
      { "path": str, "entries": [ {"name": str, "path": str, "hasChildren": bool} ] }
    """
    req_path = request.args.get('path', '').strip()
    include_hidden = str(request.args.get('include_hidden', '')).lower() in { '1', 'true', 'yes' }
    base = Path(req_path).expanduser() if req_path else Path.home()
    try:
        p = base.resolve(strict=False)
        if not p.exists():
            return jsonify({"error": "Path not found", "path": str(p)}), 404
        if not p.is_dir():
            return jsonify({"error": "Not a directory", "path": str(p)}), 400

        # Resolve platform UF_HIDDEN flag safely without adding a top-level import
        try:
            import stat as _stat
            UF_HIDDEN = getattr(_stat, 'UF_HIDDEN', 0)
        except Exception:
            UF_HIDDEN = 0

        # macOS Finder-like filtering helpers
        HIDE_AT_ROOT = {
            'System', 'Library', 'usr', 'bin', 'sbin', 'etc', 'var', 'tmp', 'dev', 'Volumes',
            'cores', 'private', 'opt', 'net'
        }

        def load_hidden_file_set(parent: Path):
            hidden_set = set()
            try:
                hf = parent / '.hidden'
                if hf.exists() and hf.is_file():
                    for line in hf.read_text(errors='ignore').splitlines():
                        name = line.strip()
                        if name:
                            hidden_set.add(name)
            except Exception:
                pass
            return hidden_set

        parent_hidden = load_hidden_file_set(p)
        is_root = p == p.anchor or str(p) == '/'

        def is_hidden_dir(path_obj: Path) -> bool:
            if include_hidden:
                return False
            name = path_obj.name
            # dot-prefixed
            if name.startswith('.'):
                return True
            # UF_HIDDEN flag (macOS/BSD)
            try:
                if UF_HIDDEN:
                    st = os.stat(path_obj, follow_symlinks=False)
                    if getattr(st, 'st_flags', 0) & UF_HIDDEN:
                        return True
            except Exception:
                # If stat fails, do not hide based on flag
                pass
            # .hidden file listing
            if name in parent_hidden:
                return True
            # Common system folders at filesystem root
            if is_root and name in HIDE_AT_ROOT:
                return True
            return False

        entries = []
        try:
            children = sorted(p.iterdir(), key=lambda c: c.name.lower())
        except PermissionError:
            children = []
        for child in children:
            # Only directories and not hidden (unless include_hidden)
            if not child.is_dir():
                continue
            if is_hidden_dir(child):
                continue
            # Determine if it has visible subdirectories (respecting filter)
            has_children = False
            try:
                for grand in child.iterdir():
                    if grand.is_dir() and not is_hidden_dir(grand):
                        has_children = True
                        break
            except PermissionError:
                has_children = False
            entries.append({
                "name": child.name,
                "path": str(child),
                "hasChildren": has_children,
            })
        # Final sort by name case-insensitively
        entries.sort(key=lambda e: e['name'].lower())
        return jsonify({"path": str(p), "entries": entries}), 200
    except Exception as exc:
        # Log and return safe error
        try:
            app.logger.exception("/api/fs/list failed for %s: %s", req_path, exc)
        except Exception:
            pass
        return jsonify({"error": "Internal Server Error"}), 500


# Finish ************************************************
@app.route('/closeApp', methods=('GET', 'POST'))
def closeApp():
    print("closing")
    os.kill(os.getpid(), signal.SIGINT)

    return json.dumps({ "success": True, "message": "Server is shutting down..." })


# Heres how to pop in array iteration: Use len(), adjust indexes for popped items
""" 
thearray = [1,2,3,4,5,6]
popctr = 0
for x in range(len(thearray)):
    if thearray[x - popctr] % 2 == 1: 
        sPrint(thearray.pop(x - popctr), thearray)
        popctr += 1
"""


# ========================= Batch Split (Marker-based) Routes =========================
from flask import send_file

@app.route('/split/marker/download', methods=['GET'])
def split_marker_download():
    """Serve the official separator page PDF. Ensure it's generated first."""
    ensure_marker_assets(app)
    paths = ensure_marker_assets(app)
    return send_file(paths['pdf'], as_attachment=True, download_name='MAILBOXAI_Separator.pdf')


@app.route('/split/marker/preview', methods=['POST'])
def split_marker_preview():
    """Compute marker positions and proposed split points for a given PDF.

    JSON body:
      - filename: optional; PDF name in source folder. If omitted, uses app.currentfile in workdir.
      - ham_thr: optional int (default 10)
      - dpi: optional int (default 150)
      - max_pages: optional int for preview limit
    Returns JSON with markers and splits.
    """
    if request.is_json:
        payload = request.get_json() or {}
    else:
        payload = {}

    filename = payload.get('filename', '')
    ham_thr = int(payload.get('ham_thr', 10))
    dpi = int(payload.get('dpi', 150))
    max_pages = payload.get('max_pages')
    if max_pages is not None:
        try:
            max_pages = int(max_pages)
        except Exception:
            max_pages = None

    # Resolve path
    if filename:
        pdf_path = os.path.join(app.localcfg['sourcepath'], filename)
    elif getattr(app, 'currentfile', ''):
        pdf_path = os.path.join(app.workdir, app.currentfile)
    else:
        return jsonify({"success": False, "error": "No file specified and no current file selected."}), 400

    try:
        assets = ensure_marker_assets(app)
        marker_img = Image.open(assets['png'])
        pages = rasterize_pdf_pages(pdf_path, dpi=dpi, max_pages=max_pages)
        markers = find_marker_pages(pages, marker_img, ham_thr=ham_thr)
        splits = build_split_points_from_markers(markers, total_pages=len(pages))
        return jsonify({
            "success": True,
            "file": os.path.basename(pdf_path),
            "total_pages": len(pages),
            "marker_indices": markers,
            "split_starts": splits
        })
    except Exception as exc:
        sPrint("split_marker_preview error:", exc)
        return jsonify({"success": False, "error": str(exc)}), 500


@app.route('/split/marker/confirm', methods=['POST'])
def split_marker_confirm():
    """Perform the actual split based on detected markers and write PDFs.

    JSON body:
      - filename: optional; if omitted uses app.currentfile in workdir
      - ham_thr: optional; detection threshold (default 10)
      - dpi: optional; rasterization dpi (default 150)
      - drop_markers: bool (default True); remove separator pages from outputs
      - out_subdir: optional; create a subfolder in sourcepath for outputs
    Returns JSON with written file paths and page ranges.
    """
    if request.is_json:
        payload = request.get_json() or {}
    else:
        payload = {}

    filename = payload.get('filename', '')
    ham_thr = int(payload.get('ham_thr', 10))
    dpi = int(payload.get('dpi', 150))
    drop_markers = bool(payload.get('drop_markers', True))
    out_subdir = payload.get('out_subdir')

    if filename:
        pdf_path = os.path.join(app.localcfg['sourcepath'], filename)
        base_dir = app.localcfg['sourcepath']
    elif getattr(app, 'currentfile', ''):
        pdf_path = os.path.join(app.workdir, app.currentfile)
        base_dir = app.workdir
    else:
        return jsonify({"success": False, "error": "No file specified and no current file selected."}), 400

    try:
        assets = ensure_marker_assets(app)
        marker_img = Image.open(assets['png'])
        # Full set of pages for accurate splitting
        pages = rasterize_pdf_pages(pdf_path, dpi=dpi)
        marker_indices = find_marker_pages(pages, marker_img, ham_thr=ham_thr)
        split_starts = build_split_points_from_markers(marker_indices, total_pages=len(pages))

        out_dir = base_dir
        if out_subdir:
            out_dir = os.path.join(base_dir, out_subdir)

        drop_pages = marker_indices if drop_markers else []
        outputs = split_pdf_by_pages(pdf_path, split_starts, out_dir, drop_pages=drop_pages)

        return jsonify({
            "success": True,
            "outputs": [
                {"path": p, "range": {"start": r[0], "end": r[1]}} for (p, r) in outputs
            ],
            "marker_indices": marker_indices,
            "split_starts": split_starts,
            "out_dir": out_dir
        })
    except Exception as exc:
        sPrint("split_marker_confirm error:", exc)
        return jsonify({"success": False, "error": str(exc)}), 500
