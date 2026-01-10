import sqlite3
import os
from datetime import datetime

class DBManager:
    def __init__(self, master_db_name="omr_master.db"):
        self.master_db_path = os.path.join(os.getcwd(), master_db_name)
        self.init_master_db()

    def init_master_db(self):
        conn = sqlite3.connect(self.master_db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_path TEXT UNIQUE, 
                filename TEXT, 
                title TEXT,
                created_at TEXT
            )
        ''')
        conn.commit()
        conn.close()

    def get_all_files(self):
        conn = sqlite3.connect(self.master_db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT filename, title, full_path, created_at FROM files ORDER BY id DESC")
        rows = cursor.fetchall()
        conn.close()
        return rows

    def add_file_to_master(self, full_path, filename, title):
        conn = sqlite3.connect(self.master_db_path)
        cursor = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            cursor.execute("INSERT INTO files (full_path, filename, title, created_at) VALUES (?, ?, ?, ?)", 
                           (full_path, filename, title, now))
            conn.commit()
        except sqlite3.IntegrityError:
            print("이미 등록된 파일입니다.")
        finally:
            conn.close()
        self.create_project_tables(full_path)

    def delete_file_from_master(self, full_path):
        conn = sqlite3.connect(self.master_db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM files WHERE full_path = ?", (full_path,))
        conn.commit()
        conn.close()

    def create_project_tables(self, db_path):
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tblScanData (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                read_num INTEGER,           
                scanner_name TEXT,          
                room_no TEXT,               
                image_path TEXT,            
                sheet_code TEXT,            
                mark_result TEXT,           
                is_valid INTEGER DEFAULT 1, 
                scan_time TEXT              
            )
        ''')
        cursor.execute('CREATE TABLE IF NOT EXISTS tblSettings (key TEXT PRIMARY KEY, value TEXT)')
        conn.commit()
        conn.close()

    def insert_scan_result(self, db_path, data):
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        sql = '''
            INSERT INTO tblScanData 
            (read_num, scanner_name, room_no, image_path, scan_time, sheet_code, mark_result, is_valid)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        '''
        cursor.execute(sql, (
            data['read_num'], data['place'], data['room'], data['path'], 
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            data.get('sheet_code', ''), data.get('mark_result', ''), data.get('is_valid', 1)
        ))
        conn.commit()
        conn.close()

    # ========================================================
    # [추가] 데이터 수정 및 조회 기능 (완전판)
    # ========================================================
    def update_scan_result(self, db_path, read_num, mark_result, is_valid):
        """수정된 결과를 DB에 반영"""
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        sql = "UPDATE tblScanData SET mark_result = ?, is_valid = ? WHERE read_num = ?"
        cursor.execute(sql, (mark_result, is_valid, read_num))
        conn.commit()
        conn.close()

    def get_all_scans(self, db_path):
        """모든 스캔 데이터 가져오기"""
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tblScanData ORDER BY read_num ASC")
        rows = cursor.fetchall()
        conn.close()
        return rows

    def get_statistics(self, db_path):
        """통계 계산 (총매수, 정상, 오류)"""
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM tblScanData")
        total = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM tblScanData WHERE is_valid=1")
        normal = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM tblScanData WHERE is_valid=0")
        error = cursor.fetchone()[0]
        
        conn.close()
        return total, normal, error

    def get_summary_by_scanner(self, db_path):
        """[판독매수 화면] 고사장/시험실별 집계"""
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        sql = '''
            SELECT scanner_name, room_no, COUNT(*), SUM(CASE WHEN is_valid=0 THEN 1 ELSE 0 END)
            FROM tblScanData
            GROUP BY scanner_name, room_no
        '''
        cursor.execute(sql)
        rows = cursor.fetchall()
        conn.close()
        return rows

    def get_vote_counts(self, db_path, q_count=5):
        """[개표결과 화면] 문항별 득표수 계산"""
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT mark_result FROM tblScanData WHERE is_valid=1")
        rows = cursor.fetchall()
        conn.close()

        stats = {i+1: {'1': 0, '2': 0, '0': 0, '3': 0} for i in range(q_count)}

        for row in rows:
            result_str = row[0]
            for i, char in enumerate(result_str):
                if i < q_count and char in stats[i+1]:
                    stats[i+1][char] += 1
        return stats

    def get_raw_data_for_grid(self, db_path):
        """[판독자료 화면] 전체 데이터 리스트"""
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT read_num, sheet_code, mark_result, image_path FROM tblScanData ORDER BY read_num ASC")
        rows = cursor.fetchall()
        conn.close()
        return rows