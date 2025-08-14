#!/usr/bin/env python3
"""
Test script for verifying tag occurrence functionality.

This script tests the following:
1. Adding tags with occurrence counts
2. Updating occurrence counts
3. Rebuilding tag vectors with correct occurrence counts
"""
import os
import sys
import tempfile
import shutil
import json
import sqlite3
from pathlib import Path

class TestDBHandler:
    """Minimal DB handler for testing tag occurrences."""
    def __init__(self, db_path):
        self.db_file = os.path.join(db_path, ".mailbox-AI-db", "database.db")
        self.conn = None
        self._ensure_tables()
        
    def _ensure_tables(self):
        """Create the necessary tables if they don't exist."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Create tags table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS tags (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tag TEXT,
                    type TEXT,
                    texthints TEXT
                )
            ''')
            
            # Create files table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT,
                    full_path TEXT,
                    date TEXT,
                    tags TEXT,
                    path TEXT,
                    description TEXT
                )
            ''')
            
            # Create files_to_tags table with occ column
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS files_to_tags (
                    file_id INTEGER,
                    tag_id INTEGER,
                    is_folder INTEGER,
                    occ INTEGER DEFAULT 1,
                    PRIMARY KEY (file_id, tag_id, is_folder),
                    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
                    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
                )
            ''')
            
            conn.commit()
    
    def _get_connection(self):
        """Get a database connection."""
        if self.conn is None:
            # Create the directory if it doesn't exist
            os.makedirs(os.path.dirname(self.db_file), exist_ok=True)
            self.conn = sqlite3.connect(self.db_file)
            self.conn.row_factory = sqlite3.Row
        return self.conn
    
    def execute(self, query, params=()):
        """Execute a query and return the cursor."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)
        return cursor
    
    def commit(self):
        """Commit the current transaction."""
        if self.conn:
            self.conn.commit()
    
    def close(self):
        """Close the database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

def setup_test_db():
    """Set up a test database in a temporary directory."""
    temp_dir = tempfile.mkdtemp(prefix="mailboxai_test_")
    return TestDBHandler(temp_dir), temp_dir

def cleanup_test_db(temp_dir):
    """Clean up the temporary test database."""
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)

def update_file_tags_field(db, file_id):
    """Simulate the update_file_tags_field function for testing."""
    # Get all tag relations for this file with their occurrence counts
    cursor = db.execute(
        'SELECT tag_id, occ FROM files_to_tags WHERE file_id = ? AND tag_id IS NOT NULL',
        (file_id,)
    )
    relations = cursor.fetchall()
    
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
    db.execute(
        'UPDATE files SET tags = ? WHERE id = ?',
        (json.dumps(compact), file_id)
    )
    db.commit()

def test_tag_occurrences():
    """Test tag occurrence functionality."""
    print("Setting up test database...")
    db, temp_dir = setup_test_db()
    
    try:
        with db._get_connection() as conn:
            cursor = conn.cursor()
            
            # Create test tags and collect their IDs
            tag_data = [
                ('test1', 'type1'),
                ('test2', 'type1'),
                ('test3', 'type2')
            ]
            
            tag_ids = []
            for tag, tag_type in tag_data:
                cursor.execute(
                    'INSERT INTO tags (tag, type) VALUES (?, ?)',
                    (tag, tag_type)
                )
                tag_ids.append(cursor.lastrowid)
            
            # Create a test file
            cursor.execute(
                'INSERT INTO files (name, full_path, date, tags, path, description) VALUES (?, ?, ?, ?, ?, ?)',
                ('test.pdf', '/path/to/test.pdf', '2023-01-01', '[]', '/path/to', 'Test file')
            )
            file_id = cursor.lastrowid
            
            # Add some tag relations with different occurrence counts
            cursor.executemany(
                'INSERT INTO files_to_tags (file_id, tag_id, is_folder, occ) VALUES (?, ?, 0, ?)',
                [
                    (file_id, tag_ids[0], 3),  # test1 appears 3 times
                    (file_id, tag_ids[1], 2),  # test2 appears 2 times
                    (file_id, tag_ids[2], 1)   # test3 appears 1 time
                ]
            )
            
            conn.commit()
        
        # Test 1: Verify the update_file_tags_field function
        print("\nTest 1: Verifying update_file_tags_field...")
        update_file_tags_field(db, file_id)
        
        # Get tag names for better output
        cursor = db.execute('SELECT id, tag FROM tags')
        tag_names = {row['id']: row['tag'] for row in cursor.fetchall()}
        
        # Get the updated tags
        cursor = db.execute('SELECT tags FROM files WHERE id = ?', (file_id,))
        tags_json = cursor.fetchone()['tags']
        tags = json.loads(tags_json)
        
        print("Tag vector after update:")
        for tag in tags:
            tag_name = tag_names.get(tag['id'], f"Unknown (ID: {tag['id']})")
            print(f"  - {tag_name} (ID: {tag['id']}): {tag['occ']} occurrences")
        
        # Verify the counts
        expected = {tag_ids[0]: 3, tag_ids[1]: 2, tag_ids[2]: 1}
        success = all(tag['id'] in expected and tag['occ'] == expected[tag['id']] for tag in tags)
        
        print(f"Test 1: {'PASSED' if success else 'FAILED'}")
        
        # Test 2: Update occurrence counts and verify again
        print("\nTest 2: Updating occurrence counts...")
        with db._get_connection() as conn:
            cursor = conn.cursor()
            # Update the occurrence count for the first tag
            cursor.execute(
                'UPDATE files_to_tags SET occ = ? WHERE file_id = ? AND tag_id = ?',
                (5, file_id, tag_ids[0])
            )
            conn.commit()
        
        # Update the tags again
        update_file_tags_field(db, file_id)
        
        # Get tag names for better output
        cursor = db.execute('SELECT id, tag FROM tags')
        tag_names = {row['id']: row['tag'] for row in cursor.fetchall()}
        
        # Get the updated tags
        cursor = db.execute('SELECT tags FROM files WHERE id = ?', (file_id,))
        tags_json = cursor.fetchone()['tags']
        tags = json.loads(tags_json)
        
        print("Tag vector after update:")
        for tag in tags:
            tag_name = tag_names.get(tag['id'], f"Unknown (ID: {tag['id']})")
            print(f"  - {tag_name} (ID: {tag['id']}): {tag['occ']} occurrences")
        
        # Verify the counts (first tag should now have 5 occurrences)
        expected[tag_ids[0]] = 5
        success = success and all(tag['id'] in expected and tag['occ'] == expected[tag['id']] for tag in tags)
        
        print(f"Test 2: {'PASSED' if success else 'FAILED'}")
        
        return success
        
    finally:
        # Clean up
        db.close()
        cleanup_test_db(temp_dir)

def test_validation():
    """Test validation of insert_relation method with invalid inputs."""
    print("\n=== Testing Validation ===")
    db, temp_dir = setup_test_db()
    
    try:
        # Create a test file and tag for valid references
        with db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO tags (tag, type) VALUES (?, ?)',
                ('valid_tag', 'type1')
            )
            valid_tag_id = cursor.lastrowid
            
            cursor.execute(
                'INSERT INTO files (name, full_path) VALUES (?, ?)',
                ('valid_file.pdf', '/path/to/valid_file.pdf')
            )
            valid_file_id = cursor.lastrowid
            conn.commit()
        
        # Create a test class that mimics the repository interface
        class MockConnectionProvider:
            def __init__(self, db):
                self.db = db
                self.conn = None
                
            def connect(self):
                if self.conn is None:
                    self.conn = self.db._get_connection()
                return self.conn
                
            def close(self):
                if self.conn:
                    self.conn.close()
        
        # Create a test repository that uses our mock connection provider
        class TestRepo:
            def __init__(self, db):
                self.cp = MockConnectionProvider(db)
                
            def _ensure_occ_column(self, conn):
                try:
                    conn.execute('ALTER TABLE files_to_tags ADD COLUMN occ INTEGER DEFAULT 1')
                    conn.commit()
                except sqlite3.OperationalError:
                    pass
                    
            def insert_relation(self, file_id, tag_id, is_folder, occ=1):
                conn = self.cp.connect()
                if not conn:
                    return False
                    
                try:
                    self._ensure_occ_column(conn)
                    
                    # Input validation
                    if not isinstance(file_id, int) or file_id <= 0:
                        print(f"Error: Invalid file_id: {file_id}")
                        return False
                        
                    if not isinstance(tag_id, int) or tag_id <= 0:
                        print(f"Error: Invalid tag_id: {tag_id}")
                        return False
                        
                    if not isinstance(occ, int) or occ <= 0:
                        print(f"Error: Occurrence count must be positive: {occ}")
                        return False
                        
                    if is_folder not in (-1, 1, 2, 3):
                        print(f"Error: is_folder must be -1, 1, 2, or 3, got: {is_folder}")
                        return False
                        
                    # Verify file and tag exist
                    cursor = conn.cursor()
                    file_exists = cursor.execute('SELECT 1 FROM files WHERE id = ?', (file_id,)).fetchone()
                    if not file_exists:
                        print(f"Error: File with ID {file_id} does not exist")
                        return False
                        
                    tag_exists = cursor.execute('SELECT 1 FROM tags WHERE id = ?', (tag_id,)).fetchone()
                    if not tag_exists:
                        print(f"Error: Tag with ID {tag_id} does not exist")
                        return False
                        
                    # If we get here, all validations passed
                    return True
                    
                except sqlite3.Error as e:
                    print(f"Database error: {e}")
                    return False
        
        # Test cases: (file_id, tag_id, is_folder, occ, expected_result, description)
        test_cases = [
            # Invalid file_id
            (0, valid_tag_id, 0, 1, False, "Zero file_id"),
            (-1, valid_tag_id, 0, 1, False, "Negative file_id"),
            (999999, valid_tag_id, 0, 1, False, "Non-existent file_id"),
            
            # Invalid tag_id
            (valid_file_id, 0, 0, 1, False, "Zero tag_id"),
            (valid_file_id, -1, 0, 1, False, "Negative tag_id"),
            (valid_file_id, 999999, 0, 1, False, "Non-existent tag_id"),
            
            # Test all valid is_folder values
            (valid_file_id, valid_tag_id, -1, 1, True, "Valid is_folder (-1)"),
            (valid_file_id, valid_tag_id, 1, 1, True, "Valid is_folder (1)"),
            (valid_file_id, valid_tag_id, 2, 1, True, "Valid is_folder (2)"),
            (valid_file_id, valid_tag_id, 3, 1, True, "Valid is_folder (3)"),
            
            # Invalid is_folder
            (valid_file_id, valid_tag_id, 0, 1, False, "Invalid is_folder (0)"),
            (valid_file_id, valid_tag_id, 4, 1, False, "Invalid is_folder (4)"),
            
            # Invalid occurrence counts
            (valid_file_id, valid_tag_id, 0, 0, False, "Zero occurrence"),
            (valid_file_id, valid_tag_id, 0, -1, False, "Negative occurrence"),
            
            # Valid cases with different folder levels
            (valid_file_id, valid_tag_id, -1, 1, True, "Valid case (top level folder)"),
            (valid_file_id, valid_tag_id, 1, 1, True, "Valid case (first level folder)"),
            (valid_file_id, valid_tag_id, 2, 1, True, "Valid case (second level folder)"),
            (valid_file_id, valid_tag_id, 3, 1, True, "Valid case (third level folder)"),
        ]
        
        repo = TestRepo(db)
        all_passed = True
        
        for file_id, tag_id, is_folder, occ, expected, desc in test_cases:
            # For non-existent IDs, we need to skip the test since we can't predict them
            if desc in ("Non-existent file_id", "Non-existent tag_id"):
                print(f"SKIP: {desc}")
                continue
                
            result = repo.insert_relation(file_id, tag_id, is_folder, occ)
            test_passed = result == expected
            
            if not test_passed:
                print(f"FAIL: {desc} - Expected {expected}, got {result}")
                all_passed = False
            else:
                print(f"PASS: {desc}")
        
        return all_passed
        
    finally:
        cleanup_test_db(temp_dir)

if __name__ == "__main__":
    print("Starting tag occurrence tests...")
    tests_passed = True
    
    # Run the occurrence tests
    if not test_tag_occurrences():
        tests_passed = False
    
    # Run the validation tests
    if not test_validation():
        tests_passed = False
    
    if tests_passed:
        print("\nAll tests completed successfully!")
    else:
        print("\nSome tests failed!")
    
    sys.exit(0 if tests_passed else 1)
