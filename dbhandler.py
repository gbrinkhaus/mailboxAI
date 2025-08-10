import os, shutil, sqlite3, json, re
from pathlib import Path
from app import getTagByID, getTagsByText, getTagByTypeAndText

class dbhandler:
    def __init__(self):
        self.dbFile = ""

    # db file + path funcs ******************************************************************************
    def get_db_file(self, newpath=None):
        dbfile = '/database.db'
        if newpath:
            return self.get_db_path(newpath) + dbfile
        else:
            return self.dbFile

    # get or create db path
    def get_db_path(self, newpath=None):
        dbfolder = "/.mailbox-AI-db"
        if newpath:
            return newpath + dbfolder
        else:
            return self.dbFile[:self.dbFile.rindex('/')]

    # make sure db exists
    def check_db(self, path):
        return os.path.isfile(self.get_db_file(path))

    # create or copy db to new location - 2x2 cases: 
    def establish_db(self, orglpath, targetpath=None):
        success = False

        # 1. db to be created at new targetpath
        if targetpath:
            if not self.check_db(targetpath):
                # 2. db does exist at source, but not at target, then move it to target
                if self.check_db(orglpath):
                    success = self.copyOrMove_db(orglpath, targetpath, "move")
                # 2. no db at source or target, copy template to target folder
                else:
                    success = self.copyOrMove_db("./templates", targetpath, "copy")

        # 2. db to be kept at original location
        else:
            # 2. db does exist, then copy it to backup
            if self.check_db(orglpath):
                self.dbFile = self.get_db_file(orglpath)
                shutil.copy(self.dbFile, self.dbFile + ".bak")
                success = True
            # 2. db doesn't exist at source, copy template to source folder
            else:
                success = self.copyOrMove_db("./templates", orglpath, "copy")

        return success

    # copy or move db to new location  
    def copyOrMove_db(self, sourcepath, targetpath, copyOrMove):
        success = False

        # db in original location must exist
        if self.check_db(sourcepath):
            # target path may not exist, then create it
            if not os.path.exists(self.get_db_path(targetpath)):
                Path(self.get_db_path(targetpath)).mkdir(parents=True, exist_ok=True)
            # copy file
            shutil.copy(self.get_db_file(sourcepath), self.get_db_file(targetpath))
            # remove source if desired
            if copyOrMove == "move":
                os.remove(self.get_db_file(sourcepath))

            self.dbFile = self.get_db_path(targetpath)
            success = True

        return success


    # db access funcs ******************************************************************************
    # connect to db - using globals to avoid having to pass the app object in all get_db_content calls
    def get_db_connection(self):
        if os.path.isfile(self.dbFile):
            conn = sqlite3.connect(self.dbFile)
            conn.row_factory = sqlite3.Row
            return conn

        return False 


    # unified get db contents function
    def get_db_tags(self, type = None, label = None):
        conn = self.get_db_connection()
        result = []
        resultarray = []

        if conn:
            if type is None or label is None:
                result = conn.execute('SELECT * FROM tags WHERE tag IS NOT NULL').fetchall()
            else:
                result = conn.execute('SELECT * FROM tags WHERE tag = ? AND type = ? AND tag IS NOT NULL', ( label, type )).fetchall()
            conn.close()

        if len(result) > 0:
            for data_out in result:  
                resultarray.append({"id": data_out['id'], "text": data_out['tag'], "label": data_out['type'], "texthints": data_out['texthints']} )  
        
            resultarray = sorted(resultarray, key=lambda x: x['label'] + x['text'])

        return resultarray


    def update_file_tags_field(self, app, fileid):
        conn = self.get_db_connection()
        tag_rows = conn.execute('SELECT tag_id FROM files_to_tags WHERE file_id = ?', (fileid,)).fetchall()
        tag_ids = [row['tag_id'] for row in tag_rows]
        tag_objs = [app.getTagByID(tid)[0] for tid in tag_ids if app.getTagByID(tid)]
        conn.execute('UPDATE files SET tags = ? WHERE id = ?', (json.dumps(tag_objs), fileid))
        conn.commit()
        conn.close()


    # unified get db contents function
    def get_db_content(self, type, query=''):
        conn = self.get_db_connection()
        result = []

        if conn:
            if(type == 'files'):
                result = conn.execute('SELECT * FROM files ORDER BY path ASC').fetchall()

            elif(type == 'onefile'):
                result = conn.execute('SELECT * FROM files WHERE id = ?', [query]).fetchall()

            # order is descending because I want newest file tags as highest prio
            elif(type == 'files_to_tags'):
                result = conn.execute('SELECT * FROM files_to_tags WHERE file_id is not NULL AND tag_id is not NULL ORDER BY file_id DESC').fetchall()
                
            # elif(type == 'tags'):
            #     result = conn.execute('SELECT * FROM tags WHERE tag = ?', [query] ).fetchall()

            else:
                print("get_db_content - unknown operator:" + type)
            conn.close()

        return result


    # return a list of all files with their tags and levels FROM DB
    def getallDBfiles(self, targetpath, withDesc):
        files = self.get_db_content('files')
        filelist = []

        for file in files:
            # I' m replacing the fullpath from the db because it doesn't reflect move of targetdir
            fullpath = targetpath + file['path']
            thisfile = {'id': file['id'], 'full_path': fullpath, 'filename': file['name'], 'date': file['date'], 'tags': file['tags'], 'path': file['path'] }
            if withDesc:
                thisfile['desc'] = file['description']
            thisfile['exists'] = os.path.isfile(fullpath + "/" + file['name'])

            levels = file['path'].split("/")
            for i, level in enumerate(levels):
                if level != '':
                    thisfile['L'+str(i)] = level

            # tags = file['tags'].split("||")
            # for i, tag in enumerate(tags):
            #    if tag != '':
            #        thisfile['T'+str(i)] = tag

            filelist.append(thisfile)

        # sorting is redundant now that I read in ordered way
        return sorted(filelist, key=lambda x: x['path'])


    # write level hints into DB
    def writeLevelHints(self, level, foldername, tags):
        conn = self.get_db_connection()
        if conn:
            values = tags.split("||")
            
            i = 0
            while i < len(values):
                if not values[i] == "":
                    conn.execute('REPLACE INTO hints (level, folder, type, tag) VALUES (?, ?, ?, ?)', (level, foldername, values[i].strip(), values[i+1].strip() ) )
                    conn.commit()
                    i += 2
                else:
                    break

            conn.close()
    

    def writeTagToFile(self, file_id, tag_id, is_folder):
            conn = self.get_db_connection()
            conn.execute('INSERT INTO files_to_tags (file_id, tag_id, is_folder) VALUES (?, ?, ?)', (file_id, tag_id, is_folder))
            conn.commit()
            conn.close()
            success = True


    # check and add the missing tags ************
    def addMissingFolderTags(self, app, fileid, relpath):
        for x, tag in enumerate(relpath.split("/")):
            if(tag != ""):
                tagfound = getTagsByText(tag)
                if tagfound:
                    id = tagfound[0]['id']
                    self.writeTagToFile(fileid, id, x)


    # check and add the missing tags ************
    def addMissingDBTags(self, app, file):
        tagsfromDesc = []
        tagstr = re.search(r"(\[(.*?)\]\])", file['desc'])
        if tagstr:
            tagsfromDesc = json.loads(tagstr[0])

        allCurrentTags = list(filter(lambda x: x['file_id'] == file['id'], app.filestotags))
        missingTags = []

        for tag in allCurrentTags:
            newTag = getTagByID(tag['tag_id'])

            # if tag is missing completely
            if not newTag:
                missingTags.append( {'id': tag['tag_id'], 'label': "unknown", 'text': "unknown"} )
            # only double check tags if DB description is filled
            elif tagsfromDesc:
                found = False

                missingTags.append( {'id': tag['tag_id'], 'label': newTag[0]['label'], 'text': newTag[0]['text'] } )
                for x, oldTag in enumerate(tagsfromDesc):
                    if newTag[0]['label'] == oldTag[0] and newTag[0]['text'] == oldTag[1]:
                        found = True
                        missingTags.pop()
                        tagsfromDesc = tagsfromDesc[:x] + tagsfromDesc[x+1:]
                        break

                if not found:
                    missingTags.append(newTag[0])
            # else:
            #  print("skipping file with no DB tags: ", fileid)

        for tag in missingTags:
            if not tag['label'] == "ACTION":
                print("missing tags for file:", file['id'], file['filename'], "tag:", tag['id'], tag['text'])
                guessTag = getTagByTypeAndText(tag['label'], tag['text'])
                if guessTag:
                    print("guessing it to be:", guessTag[0]['id'], guessTag[0]['text'])
                    # self.writeTagToFile(fileid, id, x)

        for tag in tagsfromDesc:
            if not tag[0] == "FILE" and not tag[0] == "DATE" and not tag[0] == "ACTION":
                guessTag = getTagByTypeAndText(tag[0], tag[1])
                print("tag not found for file:", file['id'], file['filename'], tag[0], tag[1])
                if guessTag:
                    print("guessing it to be:", guessTag[0]['id'], guessTag[0]['text'])
                    # self.writeTagToFile(fileid, id, x)

