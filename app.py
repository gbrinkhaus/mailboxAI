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

from flask import Flask, render_template, request, url_for, flash, redirect

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
        callstr = request.get_json()['filename'].strip()

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
            app.currentfile = app.fullfilename
            shutil.copyfile(app.fullpathplusname, app.workdir + app.fullfilename)
            filename = app.workdir + app.fullfilename

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
                        occurence = safeFind(hint, app.filecontents) 
                        if occurence > 0:
                            ents.append({"id": tag["id"], "label": tag["label"], "text": tag["text"], "texthints": tag["texthints"], 'occurence': occurence})

            # AICore candidate: do NER on recognized text and double check the results *******************
            nlp = de_core_news_md.load()
            doc = nlp(app.filecontents)
            for ent in doc.ents:
                a = checkEnt(ent)
                if a:
                    ents.append({"id": a["id"], "label": a['label'], "text": a['text'], 'occurence': safeFind(a['text'], app.filecontents) })

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
                        #         or safeFind(tag[0]['texthints'], app.filecontents) != -1 or tag[0]["label"] == "ACTION":
                        active = ""
                        if match[2]: 
                            active = "active" 
                        app.confirmedtags.append( { "id": match[1], "label": tag[0]["label"], "text": tag[0]["text"], "pathlevel": match[2], "active": active, "texthints": tag[0]["texthints"] } )

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
            for hint in hintarray:
                if len(hint) > 0:
                    ent = hint[0]
                    if ent != "FILE" and ent != "DATE":
                        val = hint[1]
                        active = hint[2]
                        tagarray = getTagByTypeAndText(ent, val)
                        if len(tagarray) > 0:
                            tagid = tagarray[0]['id']
                        else: 
                            tagid = addTagToDB(ent, val, val)

                        conn = app.dbhandler.get_db_connection()
                        conn.execute('INSERT INTO files_to_tags (file_id, tag_id, is_folder) VALUES (?, ?, ?)', (fileid, tagid, active))
                        conn.commit()
                        conn.close()

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
            conn.execute('INSERT INTO tags (type, tag, texthints) VALUES (?, ?, ?)', (type, text, newhints))
        else:
            print("mismatch in storedtags, tag found in db but not storedtags", text, type)

    conn.commit()
    conn.close()

    # Insert the TAG ID into the current tag list of the app **********
    hint = app.dbhandler.get_db_tags(type, text)
    if hint != -1:
        hint_id = hint[0]['id']
        if not hint_id in app.currenttags and hint_id != -1:
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
                app.localcfg['targetpath'] = newtarget

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
            if not os.path.exists(newdb): 
                flash('Missing database file: ' + newFile + ' - <a href="">create new</a> ', "danger")
            if not (targetchanged or movechanged or sourcechanged): flash('No changes detected - config not written', "danger")

    return render_template('settings.html', appobj=app)


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
