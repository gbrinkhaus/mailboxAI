import os, shutil, sqlite3, json, re
from pathlib import Path

# =============================
# Light-weight data access layer
# =============================
# This section introduces small repository classes per table plus a connection
# provider. Purpose: make DB usage explicit and readable without changing
# existing behavior. All current call sites keep working; we only route some
# helpers through the repos when available.

class ConnectionProvider:
    # Wrap connection creation so repos can obtain a fresh sqlite3 connection.
    #
    # Here we pass in a callable (e.g. dbhandler.get_db_connection) instead of a
    # static path to avoid depending on internal dbFile path state.
    def __init__(self, connect_fn):
        self._connect_fn = connect_fn

    def connect(self):
        return self._connect_fn()


class BaseRepo:
    def __init__(self, cp: ConnectionProvider):
        self.cp = cp


class FilesRepo(BaseRepo):
    # Access for table `files` (id, name, full_path, date, tags, path, description)
    def list_all(self):
        conn = self.cp.connect()
        if not conn:
            return []
        try:
            return conn.execute('SELECT * FROM files ORDER BY path ASC').fetchall()
        finally:
            conn.close()

    def get_by_id(self, file_id: int):
        conn = self.cp.connect()
        if not conn:
            return None
        try:
            rows = conn.execute('SELECT * FROM files WHERE id = ?', (file_id,)).fetchall()
            return rows[0] if rows else None
        finally:
            conn.close()

    def insert(self, name, full_path, date, tags_json, path, description):
        conn = self.cp.connect()
        if not conn:
            return 0
        try:
            cur = conn.execute(
                'INSERT INTO files (name, full_path, date, tags, path, description) VALUES (?, ?, ?, ?, ?, ?)',
                (name, full_path, date, tags_json, path, description)
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    def update_tags(self, file_id: int, tags_json: str):
        conn = self.cp.connect()
        if not conn:
            return
        try:
            conn.execute('UPDATE files SET tags = ? WHERE id = ?', (tags_json, file_id))
            conn.commit()
        finally:
            conn.close()

class TagsRepo(BaseRepo):
    # Access for table `tags` (id, tag, type, texthints)
    def list_all_valid(self):
        conn = self.cp.connect()
        if not conn:
            return []
        try:
            return conn.execute('SELECT * FROM tags WHERE tag IS NOT NULL').fetchall()
        finally:
            conn.close()

    def get_by_id(self, tag_id: int):
        conn = self.cp.connect()
        if not conn:
            return None
        try:
            rows = conn.execute('SELECT * FROM tags WHERE id = ?', (tag_id,)).fetchall()
            return rows[0] if rows else None
        finally:
            conn.close()

    def find_by_text(self, text: str):
        conn = self.cp.connect()
        if not conn:
            return []
        try:
            return conn.execute('SELECT * FROM tags WHERE tag = ?', (text,)).fetchall()
        finally:
            conn.close()

    def find_by_type_and_text(self, type_: str, text: str):
        conn = self.cp.connect()
        if not conn:
            return []
        try:
            return conn.execute('SELECT * FROM tags WHERE type = ? AND tag = ?', (type_, text)).fetchall()
        finally:
            conn.close()

    def add_tag(self, type, text, texthints):
        """
        Add or update a tag in the database.
        
        Args:
            type: The type of the tag (e.g., 'PERSON', 'LOCATION')
            text: The text of the tag
            texthints: Additional hints or context for the tag
            
        Returns:
            int: The ID of the tag, or -1 if the tag couldn't be added/updated
        """
        newhints = ""
        conn = self.cp.connect()
        if not conn:
            return -1
            
        try:
            # Get existing tags with the same text and type
            currenthints = self.find_by_type_and_text(type, text)
            otherhints = self.find_by_text(text)
            newhints = texthints
            hint_id = -1

            # If tag already exists with another label, warn and return -1
            if len(otherhints) > 1 or (len(otherhints) == 1 and otherhints[0]['type'] != type and type != "ACTION"):
                return hint_id 

            # Check if tag exists
            result = self.find_by_type_and_text(type, text)

            if len(result) > 0:
                dbid = result[0]['id']
                if not len(currenthints) > 0:
                    print("mismatch in storedtags, tag not found ", text, type)
                    return hint_id 

            # If tag exists in database, update it
            if len(currenthints) > 0:
                id = currenthints[0]['id']
                if type != "ACTION":
                    newhints = currenthints[0]['texthints']
                    if not texthints in newhints.split("||"): 
                        newhints += "||" + texthints

                conn.execute('UPDATE tags SET texthints = ? WHERE id = ?', (newhints, id))
                conn.commit()

            # If tag doesn't exist, insert it
            else:
                if not len(result) > 0:
                    cursor = conn.execute('INSERT INTO tags (type, tag, texthints) VALUES (?, ?, ?)', 
                                       (type, text, newhints))
                    conn.commit()
                    hint_id = cursor.lastrowid
                else:
                    print("mismatch in storedtags, tag found in db but not storedtags", text, type)
                    hint_id = result[0]['id']
            
                # For existing tags, get the ID from currenthints
                if len(currenthints) > 0:
                    hint_id = currenthints[0]['id']
                
            return hint_id
            
        except Exception as e:
            print(f"Error in addTagToDB: {e}")
            return -1
            
        finally:
            conn.close()


class FilesToTagsRepo(BaseRepo):
    # Access for table `files_to_tags` (file_id, tag_id, is_folder, occ)
    
    def _ensure_occ_column(self, conn):
        # Ensure the occ column exists in the files_to_tags table
        try:
            conn.execute('ALTER TABLE files_to_tags ADD COLUMN occ INTEGER DEFAULT 1')
            conn.commit()
        except sqlite3.OperationalError:
            # Column already exists, ignore
            pass

    def list_all(self):
        conn = self.cp.connect()
        if not conn:
            return []
        try:
            self._ensure_occ_column(conn)
            return conn.execute(
                'SELECT * FROM files_to_tags WHERE file_id is not NULL AND tag_id is not NULL ORDER BY file_id DESC'
            ).fetchall()
        finally:
            conn.close()

    def list_by_file_id(self, file_id: int):
        conn = self.cp.connect()
        if not conn:
            return []
        try:
            self._ensure_occ_column(conn)
            return conn.execute(
                'SELECT * FROM files_to_tags WHERE file_id = ? AND tag_id IS NOT NULL',
                (file_id,)
            ).fetchall()
        finally:
            conn.close()

    def insert_relation(self, file_id: int, tag_id: int, is_folder: int = -1, occ: int = 1) -> bool:
        # Insert or update a file-tag relation with validation.
        # Args:
        #     file_id: ID of the file (must exist in files table)
        #     tag_id: ID of the tag (must exist in tags table)
        #     is_folder: Whether this is a folder relation (0 or 1)
        #     occ: Number of occurrences (must be positive)
        # Returns:
        #     bool: True if the operation was successful, False otherwise
        # Input validation
        if not isinstance(file_id, int) or file_id <= 0:
            print(f"Error: Invalid file_id: {file_id}")
            return False
            
        if not isinstance(tag_id, int) or tag_id <= 0:
            print(f"Error: Invalid tag_id: {tag_id}")
            return False
        
        # files can have tags which were added manually, so occ can be 0
        if not isinstance(occ, int) or occ < 0:
            print(f"Error: Occurrence count must be positive: {occ}")
            return False
            
        if is_folder not in (-1, 1, 2, 3):
            print(f"Error: is_folder must be -1, 1, 2, or 3, got: {is_folder}")
            return False
            
        conn = self.cp.connect()
        if not conn:
            return False
            
        try:
            self._ensure_occ_column(conn)
            
            # Verify file and tag exist
            file_exists = conn.execute('SELECT 1 FROM files WHERE id = ?', (file_id,)).fetchone()
            if not file_exists:
                print(f"Error: File with ID {file_id} does not exist")
                return False
                
            tag_exists = conn.execute('SELECT 1 FROM tags WHERE id = ?', (tag_id,)).fetchone()
            if not tag_exists:
                print(f"Error: Tag with ID {tag_id} does not exist")
                return False
            
            # Use transaction to ensure atomicity
            with conn:
                # Check if the relation already exists
                existing = conn.execute(
                    'SELECT rowid, occ FROM files_to_tags WHERE file_id = ? AND tag_id = ?',
                    (file_id, tag_id)
                ).fetchone()
                
                if existing:
                    # Update existing relation, adding the new occurrences
                    new_occ = existing['occ'] + occ
                    conn.execute(
                        'UPDATE files_to_tags SET occ = ? WHERE rowid = ?',
                        (new_occ, existing['rowid'])
                    )
                else:
                    # Insert new relation with the given occurrence count
                    conn.execute(
                        'INSERT INTO files_to_tags (file_id, tag_id, is_folder, occ) VALUES (?, ?, ?, ?)',
                        (file_id, tag_id, is_folder, occ)
                    )
            return True
            
        except sqlite3.Error as e:
            print(f"Database error in insert_relation: {e}")
            return False
            
        finally:
            conn.close()
            
    def get_occurrence_count(self, file_id: int, tag_id: int) -> int:
        # Get the occurrence count of a specific tag for a file
        conn = self.cp.connect()
        if not conn:
            return 0
        try:
            self._ensure_occ_column(conn)
            row = conn.execute(
                'SELECT occ FROM files_to_tags WHERE file_id = ? AND tag_id = ?',
                (file_id, tag_id)
            ).fetchone()
            return row['occ'] if row and 'occ' in row else 0
        finally:
            conn.close()


class HintsRepo(BaseRepo):
    # Access for table `hints` (level, folder, type, tag)
    def replace(self, level: int, folder: str, type_: str, tag: str):
        conn = self.cp.connect()
        if not conn:
            return
        try:
            conn.execute(
                'REPLACE INTO hints (level, folder, type, tag) VALUES (?, ?, ?, ?)',
                (level, folder, type_, tag)
            )
            conn.commit()
        finally:
            conn.close()

class dbhandler:
    def __init__(self):
        self.dbFile = ""
        # Repositories will be initialized once a DB connection is available
        self._cp = None
        self.files = None
        self.tags = None
        self.f2t = None
        self.hints = None

    def init_repos(self):
        # Initialize repository instances. Safe to call multiple times.
        self._cp = ConnectionProvider(self.get_db_connection)
        self.files = FilesRepo(self._cp)
        self.tags = TagsRepo(self._cp)
        self.f2t = FilesToTagsRepo(self._cp)
        self.hints = HintsRepo(self._cp)

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
            # If we created/moved a DB, initialize repos
            if success:
                self.init_repos()

        # 2. db to be kept at original location
        else:
            # 2. db does exist, then copy it to backup
            if self.check_db(orglpath):
                self.dbFile = self.get_db_file(orglpath)
                shutil.copy(self.dbFile, self.dbFile + ".bak")
                success = True
                # DB lives at original location; initialize repos
                self.init_repos()
            # 2. db doesn't exist at source, copy template to source folder
            else:
                success = self.copyOrMove_db("./templates", orglpath, "copy")
                if success:
                    self.init_repos()

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
            # New DB location established; initialize repos
            self.init_repos()

        return success


    # db access funcs ******************************************************************************
    # connect to db - using globals to avoid having to pass the app object in all get_db_content calls
    def get_db_connection(self):
        if os.path.isfile(self.dbFile):
            conn = sqlite3.connect(self.dbFile)
            conn.row_factory = sqlite3.Row
            return conn

        return False 


    def get_db_tags(self, type=None, label=None):
        result = []
        resultarray = []

        if self.tags and self._cp:
            if type is None or label is None:
                result = self.tags.list_all_valid()
            else:
                conn = self._cp.connect()
                if conn:
                    try:
                        result = conn.execute(
                            'SELECT * FROM tags WHERE tag = ? AND type = ? AND tag IS NOT NULL',
                            (label, type)
                        ).fetchall()
                    finally:
                        conn.close()
        else:
            conn = self.get_db_connection()
            if conn:
                try:
                    if type is None or label is None:
                        result = conn.execute('SELECT * FROM tags WHERE tag IS NOT NULL').fetchall()
                    else:
                        result = conn.execute('SELECT * FROM tags WHERE tag = ? AND type = ? AND tag IS NOT NULL', (label, type)).fetchall()
                finally:
                    conn.close()

        if len(result) > 0:
            for data_out in result:  
                resultarray.append({"id": data_out['id'], "text": data_out['tag'], "label": data_out['type'], "texthints": data_out['texthints']} )
        
            resultarray = sorted(resultarray, key=lambda x: x['label'] + x['text'])

        return resultarray


    def update_file_tags_field(self, fileid):
        # Rebuild the compact tag vector stored in `files.tags` for a given file.
        #
        # The vector is built from `files_to_tags` relations, using the actual occurrence
        # counts stored in the `occ` column. The result is a JSON array of objects with
        # the shape: [{ "id": <tag_id:int>, "occ": <occurrence:int> }, ...]
        if not self.f2t:
            self.init_repos()
            
        try:
            # Get all tag relations for this file with their occurrence counts
            relations = self.f2t.list_by_file_id(fileid)
            
            # Group by tag_id and sum occurrences
            tag_occurrences = {}
            for rel in relations:
                tag_id = rel['tag_id']
                occ = rel['occ']
                if tag_id in tag_occurrences:
                    tag_occurrences[tag_id] += occ
                else:
                    tag_occurrences[tag_id] = occ
            
            # Build the compact vector
            compact = [{'id': tid, 'occ': occ} for tid, occ in tag_occurrences.items()]
            
            # Update the files.tags field
            conn = self.get_db_connection()
            if conn:
                try:
                    conn.execute(
                        'UPDATE files SET tags = ? WHERE id = ?',
                        (json.dumps(compact), fileid)
                    )
                    conn.commit()
                finally:
                    conn.close()
                    
        except Exception as e:
            print(f"update_file_tags_field error for file {fileid}: {e}")
            raise  # Re-raise to allow callers to handle the error


    def rebuild_all_files_tags(self):
        # Normalize the `files.tags` column for all files by rebuilding it from
        # `files_to_tags` relations using the compact vector format:
        #     [{ "id": <tag_id:int>, "occ": 1 }]
        #
        # This is a repair utility to fix legacy rows that may contain full tag
        # objects or otherwise malformed JSON. The method prints minimal progress
        # info to the console.

        # 1) Collect all file IDs
        file_rows = []
        if self.files:
            file_rows = self.files.list_all()
        else:
            conn = self.get_db_connection()
            if conn:
                try:
                    file_rows = conn.execute('SELECT id FROM files ORDER BY id ASC').fetchall()
                finally:
                    conn.close()

        # 2) Rebuild tags per file
        total = len(file_rows)
        for idx, row in enumerate(file_rows, start=1):
            file_id = row['id'] if 'id' in row.keys() else row[0]
            try:
                self.update_file_tags_field(file_id)
            except Exception as e:
                print(f"rebuild_all_files_tags: failed for file {file_id}: {e}")
            # Light progress output to give user feedback during longer runs
            if idx % 50 == 0 or idx == total:
                print(f"rebuild_all_files_tags: processed {idx}/{total} files")

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
        # Create or update a file-tag relation.
        #
        # Args:
        #     file_id: ID of the file
        #     tag_id: ID of the tag (must not be modified during this operation)
        #     is_folder: Flag indicating if this is a folder relation
        #
        # Returns:
        #     bool: Always returns True for backward compatibility
        try:
            # Ensure repositories are initialized
            if not self.f2t or not self._cp:
                self.init_repos()
                
            # Use the repository method to handle the relation
            # The repository will handle the update-or-insert logic
            self.f2t.insert_relation(file_id, tag_id, is_folder, 1)
            
            # Update the compact tag vector in the files table
            self.update_file_tags_field(file_id)
            
        except Exception as e:
            print(f"Error in writeTagToFile: {e}")
            # Fallback to direct SQL if repository operation fails
            try:
                conn = self.get_db_connection()
                if conn:
                    try:
                        cursor = conn.cursor()
                        # Try to update existing relation
                        cursor.execute(
                            'UPDATE files_to_tags SET occ = COALESCE(occ, 0) + 1 WHERE file_id = ? AND tag_id = ?',
                            (file_id, tag_id)
                        )
                        
                        # If no rows were updated, insert new relation
                        if cursor.rowcount == 0:
                            cursor.execute(
                                'INSERT INTO files_to_tags (file_id, tag_id, is_folder, occ) VALUES (?, ?, ?, 1)',
                                (file_id, tag_id, is_folder)
                            )
                        conn.commit()
                        
                        # Update the compact tag vector in the files table
                        self.update_file_tags_field(file_id)
                        
                    except Exception as inner_e:
                        print(f"Error in writeTagToFile fallback: {inner_e}")
                        if conn:
                            conn.rollback()
                        raise
                    finally:
                        conn.close()
            except Exception as fallback_e:
                print(f"Fatal error in writeTagToFile fallback: {fallback_e}")
                # Continue to return True for backward compatibility
                
        return True  # Maintain backward compatibility


    # check and add the missing tags ************
    def add_tag_to_file(self, file_id: int, tag_id: int, is_folder: int, occurrence_count: int = 1) -> bool:
        # Add a tag to a file with the specified occurrence count.
        #
        # Args:
        #     file_id: ID of the file to tag
        #     tag_id: ID of the tag to add
        #     is_folder: Whether this is a folder relation (0 or 1)
        #     occurrence_count: Number of occurrences of this tag in the file (default: 1)
        #
        # Returns:
        #     bool: True if the operation was successful, False otherwise
        if not self.f2t:
            self.init_repos()
        return self.f2t.insert_relation(file_id, tag_id, is_folder, occurrence_count)

    def addMissingFolderTags(self, app, fileid, relpath):
        from app import getTagsByText
        for x, tag in enumerate(relpath.split("/")):
            if tag != "":
                tagfound = getTagsByText(tag)
                if tagfound:
                    id = tagfound[0]['id']
                    self.writeTagToFile(fileid, id, x)

    def addMissingDBTags(self, app, file):
        from app import getTagByID, getTagByTypeAndText
        tagsfromDesc = []
        tagstr = re.search(r"(\[(.*?)\]\])", file['desc'])
        if tagstr:
            tagsfromDesc = json.loads(tagstr[0])

        allCurrentTags = list(filter(lambda x: x['file_id'] == file['id'], app.filestotags))
        missingTags = []

        for tag in allCurrentTags:
            # get all tags from filename and path
            filename = os.path.basename(file)
            path = os.path.dirname(file)
            
            if tagstr:  # Only try to parse if tagstr was found
                tagsfromDesc = json.loads(tagstr[0])
                
            newTag = getTagByID(tag['tag_id'])

            # if tag is missing completely
            if not newTag:
                missingTags.append({'id': tag['tag_id'], 'label': "unknown", 'text': "unknown"})
            # only double check tags if DB description is filled
            elif tagsfromDesc:
                found = False

                missingTags.append({'id': tag['tag_id'], 'label': newTag[0]['label'], 'text': newTag[0]['text']})
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


    def addTagToDB(self, type, text, texthints):
        """
        Add or update a tag in the database.
        
        Args:
            type: The type of the tag (e.g., 'PERSON', 'LOCATION')
            text: The text of the tag
            texthints: Additional hints or context for the tag
            
        Returns:
            int: The ID of the tag, or -1 if the tag couldn't be added/updated
        """
        return self.tags.add_tag(type, text, texthints)
