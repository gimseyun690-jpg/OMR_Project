import sqlite3
import os
import getpass
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
        import sqlite3

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.executescript("""
        CREATE TABLE IF NOT EXISTS tblScanData (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            read_num INTEGER,
            scanner_name TEXT,
            room_no TEXT,
            image_path TEXT,
            sheet_code TEXT,
            mark_result TEXT,
            is_valid INTEGER DEFAULT 1,
            scan_time TEXT,
            error_message TEXT,
            exam_no TEXT,
            birth TEXT,
            subject TEXT,
            review_done INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS tblRoster (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            exam_no TEXT,
            name TEXT,
            birth TEXT,
            subject TEXT,
            school TEXT,
            room TEXT,
            attendance TEXT
        );

        CREATE TABLE IF NOT EXISTS tblAnswer (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            q_num INTEGER,
            answer TEXT,
            score REAL
        );

        CREATE TABLE IF NOT EXISTS tblScoreResult (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            exam_no TEXT,
            name TEXT,
            correct_cnt INTEGER,
            score REAL,
            grade TEXT,
            note TEXT,
            scoring_mode TEXT,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS manual_edits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            read_num INTEGER NOT NULL,
            image_path TEXT,
            before_result TEXT,
            after_result TEXT,
            editor TEXT,
            reason TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS tblSettings (
            key TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_scan_readnum
            ON tblScanData(read_num);
        CREATE INDEX IF NOT EXISTS idx_scan_place_room
            ON tblScanData(scanner_name, room_no);
        CREATE INDEX IF NOT EXISTS idx_scan_is_valid
            ON tblScanData(is_valid);

        CREATE INDEX IF NOT EXISTS idx_manual_edits_readnum
            ON manual_edits(read_num);
        """)

        conn.commit()
        conn.close()


    # 공통 연결 메서드 추가
    def _get_conn(self, db_path):
        conn = sqlite3.connect(db_path)
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA busy_timeout=3000;")
        except Exception:
            pass
        return conn

    def connect(self, db_path):
        return self._get_conn(db_path)

    def insert_scan_result(self, db_path, data: dict):
        """
        tblScanData 삽입
        data keys: read_num, place, room, path, sheet_code, mark_result, is_valid
        """
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._get_conn(db_path) as conn:
            cur = conn.cursor()
            self._ensure_scan_columns(conn)
            cur.execute("""
                INSERT INTO tblScanData
                (read_num, scanner_name, room_no, image_path, sheet_code, mark_result, is_valid, scan_time, error_message, exam_no, birth, subject, review_done)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data.get("read_num"),
                data.get("place"),
                data.get("room"),
                data.get("path"),
                data.get("sheet_code"),
                data.get("mark_result"),
                data.get("is_valid", 1),
                created_at,
                data.get("error_message"),
                data.get("exam_no"),
                data.get("birth"),
                data.get("subject"),
                data.get("review_done", 0),
            ))
            conn.commit()

    def _ensure_scan_columns(self, conn):
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(tblScanData)")
        rows = cur.fetchall()
        cols = {row[1] for row in rows}
        if not cols:
            cur.executescript("""
                CREATE TABLE IF NOT EXISTS tblScanData (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    read_num INTEGER,
                    scanner_name TEXT,
                    room_no TEXT,
                    image_path TEXT,
                    sheet_code TEXT,
                    mark_result TEXT,
                    is_valid INTEGER DEFAULT 1,
                    scan_time TEXT,
                    error_message TEXT,
                    exam_no TEXT,
                    birth TEXT,
                    subject TEXT,
                    review_done INTEGER DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_scan_readnum
                    ON tblScanData(read_num);
                CREATE INDEX IF NOT EXISTS idx_scan_place_room
                    ON tblScanData(scanner_name, room_no);
                CREATE INDEX IF NOT EXISTS idx_scan_is_valid
                    ON tblScanData(is_valid);
            """)
            conn.commit()
            cur.execute("PRAGMA table_info(tblScanData)")
            rows = cur.fetchall()
            cols = {row[1] for row in rows}
        for name, col_type in (
            ("error_message", "TEXT"),
            ("exam_no", "TEXT"),
            ("birth", "TEXT"),
            ("subject", "TEXT"),
            ("review_done", "INTEGER"),
        ):
            if name not in cols:
                cur.execute(f"ALTER TABLE tblScanData ADD COLUMN {name} {col_type}")
        conn.commit()

    def update_review_done(self, db_path, read_num, done: int):
        with self._get_conn(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE tblScanData SET review_done = ? WHERE read_num = ?", (int(done), read_num))
            conn.commit()

    def _ensure_roster_columns(self, conn):
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(tblRoster)")
        cols = {row[1] for row in cur.fetchall()}
        if not cols:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS tblRoster (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    exam_no TEXT,
                    name TEXT,
                    birth TEXT,
                    subject TEXT,
                    school TEXT,
                    room TEXT,
                    attendance TEXT
                )
            """)
            conn.commit()
            return
        for name, col_type in (
            ("exam_no", "TEXT"),
            ("name", "TEXT"),
            ("birth", "TEXT"),
            ("subject", "TEXT"),
            ("school", "TEXT"),
            ("room", "TEXT"),
            ("attendance", "TEXT"),
        ):
            if name not in cols:
                cur.execute(f"ALTER TABLE tblRoster ADD COLUMN {name} {col_type}")
        conn.commit()

    def insert_manual_edit(self, db_path, read_num, image_path, before_result, after_result,
                           editor=None, reason=None):
        if editor is None:
            editor = getpass.getuser()
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # with문으로 close 자동 처리 (안전성)
        with self._get_conn(db_path) as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO manual_edits
                (read_num, image_path, before_result, after_result, editor, reason, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (read_num, image_path, before_result, after_result, editor, reason, created_at))
            conn.commit()
    # ========================================================
    # [추가] 데이터 수정/조회 기능 (레거시 포함)
    # ========================================================
    def update_scan_result(self, db_path, read_num, mark_result, is_valid):
        """수정 결과를 DB에 반영"""
        with self._get_conn(db_path) as conn:
            cursor = conn.cursor()
            sql = "UPDATE tblScanData SET mark_result = ?, is_valid = ? WHERE read_num = ?"
            cursor.execute(sql, (mark_result, is_valid, read_num))
            conn.commit()


    def update_scan_result_detail(
        self,
        db_path,
        read_num,
        mark_result,
        is_valid,
        error_message=None,
        sheet_code=None,
        exam_no=None,
        birth=None,
        subject=None,
    ):
        fields = ["mark_result = ?", "is_valid = ?"]
        values = [mark_result, is_valid]
        if error_message is not None:
            fields.append("error_message = ?")
            values.append(error_message)
        if sheet_code is not None:
            fields.append("sheet_code = ?")
            values.append(sheet_code)
        if exam_no is not None:
            fields.append("exam_no = ?")
            values.append(exam_no)
        if birth is not None:
            fields.append("birth = ?")
            values.append(birth)
        if subject is not None:
            fields.append("subject = ?")
            values.append(subject)
        values.append(read_num)
        with self._get_conn(db_path) as conn:
            cursor = conn.cursor()
            sql = f"UPDATE tblScanData SET {', '.join(fields)} WHERE read_num = ?"
            cursor.execute(sql, values)
            conn.commit()

    def get_scan_by_read_num(self, db_path, read_num):
        with self._get_conn(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tblScanData WHERE read_num = ?", (read_num,))
            return cursor.fetchone()

    def delete_scan_result(self, db_path, read_num):
        with self._get_conn(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM tblScanData WHERE read_num = ?", (read_num,))
            conn.commit()

    def update_scan_meta(self, db_path, read_num, scanner_name=None, room_no=None, image_path=None):
        fields = []
        values = []
        if scanner_name is not None:
            fields.append("scanner_name = ?")
            values.append(scanner_name)
        if room_no is not None:
            fields.append("room_no = ?")
            values.append(room_no)
        if image_path is not None:
            fields.append("image_path = ?")
            values.append(image_path)
        if not fields:
            return
        values.append(read_num)
        with self._get_conn(db_path) as conn:
            cursor = conn.cursor()
            sql = f"UPDATE tblScanData SET {', '.join(fields)} WHERE read_num = ?"
            cursor.execute(sql, values)
            conn.commit()

    def renumber_read_nums(self, db_path, ordered_read_nums):
        """
        ordered_read_nums:
          - legacy: [old_read_num, ...]
          - safe mode: [(id, old_read_num), ...]
        입력 순서대로 1..N 재부여.
        """
        with self._get_conn(db_path) as conn:
            cursor = conn.cursor()
            if not ordered_read_nums:
                return

            uses_row_id = (
                isinstance(ordered_read_nums[0], (tuple, list))
                and len(ordered_read_nums[0]) >= 2
            )

            entries = []
            if uses_row_id:
                # (id, read_num) 형태는 row id 기준으로 안전하게 재번호를 부여한다.
                for item in ordered_read_nums:
                    try:
                        row_id = int(item[0])
                        old_num = int(item[1])
                    except Exception:
                        continue
                    entries.append((row_id, old_num))
            else:
                # legacy 입력은 read_num 기준.
                seen = set()
                for item in ordered_read_nums:
                    try:
                        old_num = int(item)
                    except Exception:
                        continue
                    if old_num in seen:
                        continue
                    seen.add(old_num)
                    entries.append((None, old_num))

            if not entries:
                return

            cursor.execute("SELECT COALESCE(MAX(read_num), 0) FROM tblScanData")
            max_read_num = cursor.fetchone()[0] or 0
            temp_base = int(max_read_num) + len(entries) + 1000

            # 1차: 임시 번호로 이동
            for offset, (row_id, old_num) in enumerate(entries, start=1):
                temp_num = temp_base + offset
                if uses_row_id and row_id is not None:
                    cursor.execute(
                        "UPDATE tblScanData SET read_num = ? WHERE id = ?",
                        (temp_num, row_id),
                    )
                else:
                    cursor.execute(
                        "UPDATE tblScanData SET read_num = ? WHERE read_num = ?",
                        (temp_num, old_num),
                    )

            # 2차: 최종 1..N 부여
            for new_num, (row_id, old_num) in enumerate(entries, start=1):
                temp_num = temp_base + new_num
                if uses_row_id and row_id is not None:
                    cursor.execute(
                        "UPDATE tblScanData SET read_num = ? WHERE id = ?",
                        (new_num, row_id),
                    )
                else:
                    cursor.execute(
                        "UPDATE tblScanData SET read_num = ? WHERE read_num = ?",
                        (new_num, temp_num),
                    )
            conn.commit()

    def get_all_scans(self, db_path):
        """모든 스캔 데이터 불러오기"""
        with self._get_conn(db_path) as conn:
            cursor = conn.cursor()
            self._ensure_scan_columns(conn)
            cursor.execute("SELECT * FROM tblScanData ORDER BY read_num ASC")
            return cursor.fetchall()

    def get_scan_count(self, db_path):
        with self._get_conn(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM tblScanData")
            return cursor.fetchone()[0]

    def get_max_read_num(self, db_path):
        with self._get_conn(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COALESCE(MAX(read_num), 0) FROM tblScanData")
            value = cursor.fetchone()[0]
            try:
                return int(value or 0)
            except Exception:
                return 0

    def get_scan_count_by_place_room(self, db_path, place, room):
        with self._get_conn(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM tblScanData WHERE scanner_name = ? AND room_no = ?",
                (place, room),
            )
            return cursor.fetchone()[0]

    def get_scans_page(self, db_path, limit, offset=0):
        with self._get_conn(db_path) as conn:
            cursor = conn.cursor()
            self._ensure_scan_columns(conn)
            cursor.execute(
                "SELECT * FROM tblScanData ORDER BY read_num ASC LIMIT ? OFFSET ?",
                (limit, offset),
            )
            return cursor.fetchall()

    def get_scans_by_place_room(self, db_path, place, room, limit=None, offset=0):
        """고사장/시험실로 결과 조회 (선택 파라미터 지원)."""
        with self._get_conn(db_path) as conn:
            cursor = conn.cursor()
            self._ensure_scan_columns(conn)
            sql = """
                SELECT * FROM tblScanData
                WHERE scanner_name = ? AND room_no = ?
                ORDER BY read_num ASC
            """
            params = [place, room]
            if limit is not None:
                sql += " LIMIT ? OFFSET ?"
                params.extend([limit, offset])
            cursor.execute(sql, params)
            return cursor.fetchall()

    def get_scans_in_range(self, db_path, start_read_num, end_read_num):
        with self._get_conn(db_path) as conn:
            cursor = conn.cursor()
            self._ensure_scan_columns(conn)
            cursor.execute("""
            SELECT read_num, mark_result, is_valid, exam_no
            FROM tblScanData
            WHERE read_num BETWEEN ? AND ?
            ORDER BY read_num ASC
            """, (start_read_num, end_read_num))
            return cursor.fetchall()

    def get_statistics(self, db_path):
        """통계 계산 (총매수, 정상, 오류)"""
        with self._get_conn(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM tblScanData")
            total = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM tblScanData WHERE is_valid=1")
            normal = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM tblScanData WHERE is_valid=0")
            error = cursor.fetchone()[0]
            return total, normal, error

    def get_summary_by_scanner(self, db_path):
        """[판독매수 화면] 고사장/시험실별 집계"""
        with self._get_conn(db_path) as conn:
            cursor = conn.cursor()
            sql = '''
            SELECT scanner_name, room_no, COUNT(*), SUM(CASE WHEN is_valid=0 THEN 1 ELSE 0 END)
            FROM tblScanData
            GROUP BY scanner_name, room_no
            '''
            cursor.execute(sql)
            return cursor.fetchall()

    def get_vote_counts(self, db_path, q_count=5):
        """[개표결과 화면] 문항별 집계 계산"""
        with self._get_conn(db_path) as conn:
            self._ensure_scan_columns(conn)
            cursor = conn.cursor()
            cursor.execute("SELECT mark_result FROM tblScanData WHERE is_valid=1")
            rows = cursor.fetchall()

        stats = {i+1: {'1': 0, '2': 0, '0': 0, '3': 0} for i in range(q_count)}

        for row in rows:
            result_str = row[0]
            for i, char in enumerate(result_str):
                if i < q_count and char in stats[i+1]:
                    stats[i+1][char] += 1
        return stats

    def get_raw_data_for_grid(self, db_path):
        """[판독자료 화면] 전체 데이터 리스트"""
        with self._get_conn(db_path) as conn:
            self._ensure_scan_columns(conn)
            cursor = conn.cursor()
            cursor.execute("SELECT read_num, sheet_code, mark_result, image_path FROM tblScanData ORDER BY read_num ASC")
            return cursor.fetchall()
    
    def get_setting(self, db_path, key, default_value=""):
        """설정값 불러오기"""
        try:
            with self._get_conn(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS tblSettings (
                        key TEXT PRIMARY KEY,
                        value TEXT
                    )
                """)
                cursor.execute("SELECT value FROM tblSettings WHERE key=?", (key,))
                row = cursor.fetchone()
                return row[0] if row else default_value
        except:
            return default_value

    def save_setting(self, db_path, key, value):
        """설정값 저장 (없으면 생성, 있으면 수정)"""
        with self._get_conn(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tblSettings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            # UPSERT 방식 (SQLite 버전에 따라 직접 INSERT/DELETE 사용)
            cursor.execute("DELETE FROM tblSettings WHERE key=?", (key,))
            cursor.execute("INSERT INTO tblSettings (key, value) VALUES (?, ?)", (key, str(value)))
            conn.commit()

    # ========================================================
    # [추가] 명단/정답 입력 저장 및 조회
    # ========================================================
    def save_roster(self, db_path, rows):
        """rows: list of (exam_no, name, birth, subject, school, room, attendance)"""
        with self._get_conn(db_path) as conn:
            cur = conn.cursor()
            self._ensure_roster_columns(conn)
            cur.execute("DELETE FROM tblRoster")
            cur.executemany(
                "INSERT INTO tblRoster (exam_no, name, birth, subject, school, room, attendance) VALUES (?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            conn.commit()

    def load_roster(self, db_path):
        with self._get_conn(db_path) as conn:
            cur = conn.cursor()
            self._ensure_roster_columns(conn)
            cur.execute("SELECT exam_no, name, birth, subject, school, room, attendance FROM tblRoster ORDER BY id ASC")
            return cur.fetchall()

    def save_answers(self, db_path, rows):
        """rows: list of (q_num, answer, score)"""
        with self._get_conn(db_path) as conn:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS tblAnswer (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    q_num INTEGER,
                    answer TEXT,
                    score REAL
                )
            """)
            cur.execute("DELETE FROM tblAnswer")
            cur.executemany(
                "INSERT INTO tblAnswer (q_num, answer, score) VALUES (?, ?, ?)",
                rows,
            )
            conn.commit()

    def load_answers(self, db_path):
        with self._get_conn(db_path) as conn:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS tblAnswer (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    q_num INTEGER,
                    answer TEXT,
                    score REAL
                )
            """)
            cur.execute("SELECT q_num, answer, score FROM tblAnswer ORDER BY q_num ASC")
            return cur.fetchall()

    # ========================================================
    # [추가] 채점 결과 저장 및 조회
    # ========================================================
    def save_score_results(self, db_path, rows, scoring_mode):
        """rows: list of (exam_no, name, correct_cnt, score, grade, note)"""
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._get_conn(db_path) as conn:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS tblScoreResult (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    exam_no TEXT,
                    name TEXT,
                    correct_cnt INTEGER,
                    score REAL,
                    grade TEXT,
                    note TEXT,
                    scoring_mode TEXT,
                    created_at TEXT
                )
            """)
            cur.execute("DELETE FROM tblScoreResult")
            cur.executemany(
                "INSERT INTO tblScoreResult (exam_no, name, correct_cnt, score, grade, note, scoring_mode, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [(r[0], r[1], r[2], r[3], r[4], r[5], scoring_mode, created_at) for r in rows],
            )
            conn.commit()

    def load_score_results(self, db_path):
        with self._get_conn(db_path) as conn:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS tblScoreResult (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    exam_no TEXT,
                    name TEXT,
                    correct_cnt INTEGER,
                    score REAL,
                    grade TEXT,
                    note TEXT,
                    scoring_mode TEXT,
                    created_at TEXT
                )
            """)
            cur.execute("""
                SELECT exam_no, name, correct_cnt, score, grade, note, scoring_mode, created_at
                FROM tblScoreResult
                ORDER BY id ASC
            """)
            return cur.fetchall()

    # ========================================================
    # [추가] 문항 분석 캐시
    # ========================================================
    def get_analysis_signature(self, db_path):
        with self._get_conn(db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*), MAX(scan_time) FROM tblScanData")
            scan_cnt, scan_max = cur.fetchone()
            cur.execute("SELECT COUNT(*), MAX(id) FROM tblAnswer")
            ans_cnt, ans_max = cur.fetchone()
            cur.execute("SELECT COUNT(*), MAX(id) FROM tblScoreResult")
            score_cnt, score_max = cur.fetchone()
        return f"scan:{scan_cnt}|{scan_max}|ans:{ans_cnt}|{ans_max}|score:{score_cnt}|{score_max}"

    def save_item_analysis(self, db_path, rows):
        with self._get_conn(db_path) as conn:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS tblItemAnalysis (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    q_num INTEGER,
                    answer TEXT,
                    correct_rate TEXT,
                    difficulty TEXT,
                    discrimination TEXT,
                    note TEXT
                )
            """)
            cur.execute("DELETE FROM tblItemAnalysis")
            cur.executemany(
                "INSERT INTO tblItemAnalysis (q_num, answer, correct_rate, difficulty, discrimination, note) VALUES (?, ?, ?, ?, ?, ?)",
                rows,
            )
            conn.commit()

    def load_item_analysis(self, db_path):
        with self._get_conn(db_path) as conn:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS tblItemAnalysis (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    q_num INTEGER,
                    answer TEXT,
                    correct_rate TEXT,
                    difficulty TEXT,
                    discrimination TEXT,
                    note TEXT
                )
            """)
            cur.execute("""
                SELECT q_num, answer, correct_rate, difficulty, discrimination, note
                FROM tblItemAnalysis
                ORDER BY q_num ASC
            """)
            return cur.fetchall()


