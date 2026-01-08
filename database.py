import sqlite3
import os
from datetime import datetime

class DBManager:
    def __init__(self, master_db_name="omr_master.db"):
        # 프로그램 실행 위치에 마스터 DB 파일 생성
        self.master_db_path = os.path.join(os.getcwd(), master_db_name)
        self.init_master_db()

    def init_master_db(self):
        """마스터 DB: 프로젝트 파일 목록을 관리하는 주소록"""
        conn = sqlite3.connect(self.master_db_path)
        cursor = conn.cursor()
        # 파일 경로, 파일명, 제목, 생성일
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
        """저장된 모든 프로젝트 파일 목록 가져오기"""
        conn = sqlite3.connect(self.master_db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT filename, title, full_path, created_at FROM files ORDER BY id DESC")
        rows = cursor.fetchall()
        conn.close()
        return rows

    def add_file_to_master(self, full_path, filename, title):
        """새 프로젝트 파일을 마스터 DB에 등록"""
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
            
        # ★중요: 등록과 동시에 해당 파일 안에 필요한 테이블들을 생성해줌
        self.create_project_tables(full_path)

    def delete_file_from_master(self, full_path):
        """목록에서만 삭제 (실제 파일은 안전을 위해 남겨둠)"""
        conn = sqlite3.connect(self.master_db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM files WHERE full_path = ?", (full_path,))
        conn.commit()
        conn.close()

    def create_project_tables(self, db_path):
        """
        [핵심] 개별 프로젝트 파일(.SSDB) 내부에 필요한 테이블 생성
        이게 있어야 스캔 데이터를 저장할 수 있음!
        """
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 1. 스캔 데이터 테이블 (판독 결과 저장)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tblScanData (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                read_num INTEGER,           -- 판독번호 (1, 2, 3...)
                scanner_name TEXT,          -- 스캐너 이름 (스캐너1)
                room_no TEXT,               -- 시험실 번호
                image_path TEXT,            -- 원본 이미지 경로
                sheet_code TEXT,            -- 용지 코드
                mark_result TEXT,           -- 판독 결과 (10100...)
                is_valid INTEGER DEFAULT 1, -- 유효표 여부 (1:유효, 0:무효)
                scan_time TEXT              -- 스캔 시간
            )
        ''')

        # 2. 설정 테이블 (양식 설정값 등)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tblSettings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        
        conn.commit()
        conn.close()
        print(f"DB 초기화 완료: {db_path}")

# database.py 파일의 기존 insert_scan_result 함수를 이것으로 교체하세요.

    def insert_scan_result(self, db_path, data):
        """스캔 결과 1건 저장 (판독 데이터 포함)"""
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # SQL문에 mark_result(마킹내용)와 is_valid(유효표 여부) 컬럼 추가
        sql = '''
            INSERT INTO tblScanData 
            (read_num, scanner_name, room_no, image_path, scan_time, sheet_code, mark_result, is_valid)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        '''
        
        # data 딕셔너리에서 필요한 값들을 뽑아서 저장
        cursor.execute(sql, (
            data['read_num'], 
            data['place'], 
            data['room'], 
            data['path'], 
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            data.get('sheet_code', ''),  # 용지 코드 (없으면 빈칸)
            data.get('mark_result', ''), # 판독 결과 (예: "10100...")
            data.get('is_valid', 1)      # 유효표 여부 (1:정상, 0:오류)
        ))
        conn.commit()
        conn.close()