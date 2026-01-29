from __future__ import annotations

import os
from PySide2.QtCore import Qt
from PySide2.QtWidgets import (QApplication, QTableWidgetItem, QMessageBox,
                               QAbstractItemView, QMenu, QInputDialog, QFileDialog)
from logic.services.tasks.summary_tasks import SummaryTask


class GridSyncMixin:
    """요약/그리드/DB 동기화."""

    def _add_summary_row(self, place_text: str, room_text: str):
        row = self.summary_table.rowCount()
        self.summary_table.insertRow(row)
        self.summary_table.setItem(row, 0, self._item(place_text))
        self.summary_table.setItem(row, 1, self._item(room_text))
        self.summary_table.setItem(row, 2, self._item("0"))
        self.summary_table.selectRow(row)
        self.current_summary_row = row

    def _find_summary_row(self, place_text: str, room_text: str):
        for r in range(self.summary_table.rowCount()):
            place_item = self.summary_table.item(r, 0)
            room_item = self.summary_table.item(r, 1)
            if not place_item or not room_item:
                continue
            if place_item.text() == str(place_text) and room_item.text() == str(room_text):
                return r
        return None

    def _upsert_summary_count(self, place_text: str, room_text: str, add_count: int):
        row = self._find_summary_row(place_text, room_text)
        if row is None:
            row = self.summary_table.rowCount()
            self.summary_table.insertRow(row)
            self.summary_table.setItem(row, 0, self._item(place_text))
            self.summary_table.setItem(row, 1, self._item(room_text))
            self.summary_table.setItem(row, 2, self._item("0"))
        item = self.summary_table.item(row, 2)
        try:
            current = int(item.text()) if item else 0
        except Exception:
            current = 0
        new_count = max(0, current + int(add_count))
        if item is None:
            self.summary_table.setItem(row, 2, self._item(str(new_count)))
        else:
            item.setText(str(new_count))
        self._sort_summary_table()

    def _update_summary_count(self):
        if self.current_summary_row is None:
            return
        item = self.summary_table.item(self.current_summary_row, 2)
        if item is None:
            self.summary_table.setItem(self.current_summary_row, 2, self._item(str(self.current_session_count)))
        else:
            item.setText(str(self.current_session_count))

    def _sort_summary_table(self):
        if self.summary_table.rowCount() == 0:
            return
        selected_key = None
        sel = self.summary_table.selectionModel()
        if sel and sel.hasSelection():
            row = sel.selectedRows()[0].row()
            place_item = self.summary_table.item(row, 0)
            room_item = self.summary_table.item(row, 1)
            if place_item and room_item:
                selected_key = (place_item.text(), room_item.text())

        rows = []
        for r in range(self.summary_table.rowCount()):
            place_item = self.summary_table.item(r, 0)
            room_item = self.summary_table.item(r, 1)
            count_item = self.summary_table.item(r, 2)
            if not place_item or not room_item:
                continue
            place_text = place_item.text()
            room_text = room_item.text()
            count_text = count_item.text() if count_item else "0"
            rows.append((place_text, room_text, count_text))

        def _room_key(v):
            try:
                return int(str(v).strip())
            except Exception:
                return str(v)

        rows.sort(key=lambda r: (str(r[0]), _room_key(r[1])))

        self.summary_table.setUpdatesEnabled(False)
        self.summary_table.blockSignals(True)
        try:
            self.summary_table.setRowCount(0)
            for place_text, room_text, count_text in rows:
                row = self.summary_table.rowCount()
                self.summary_table.insertRow(row)
                self.summary_table.setItem(row, 0, self._item(place_text))
                self.summary_table.setItem(row, 1, self._item(room_text))
                self.summary_table.setItem(row, 2, self._item(count_text))
            if self.summary_table.rowCount() > 0:
                target_row = 0
                if selected_key:
                    for r in range(self.summary_table.rowCount()):
                        place_item = self.summary_table.item(r, 0)
                        room_item = self.summary_table.item(r, 1)
                        if place_item and room_item and (place_item.text(), room_item.text()) == selected_key:
                            target_row = r
                            break
                self.summary_table.selectRow(target_row)
                self.current_summary_row = target_row
        finally:
            self.summary_table.blockSignals(False)
            self.summary_table.setUpdatesEnabled(True)

    # -------------------------------------------------------------------------
    # [1] UI 생성
    # -------------------------------------------------------------------------
    def _item(self, text):
        """테이블 아이템 생성 헬퍼."""
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignCenter)
        return item

    def _get_selected_rows(self):
        model = self.main_grid.selectionModel()
        if not model:
            return []
        return sorted([idx.row() for idx in model.selectedRows()])

    def _get_selected_read_nums(self):
        rows = self._get_selected_rows()
        read_nums = []
        for r in rows:
            item = self.main_grid.item(r, 0)
            if item:
                try:
                    read_nums.append(int(item.text()))
                except Exception as e:
                    print(f"[WARN] read_num 파싱 실패: {e}")
        return read_nums

    def _get_row_data_by_read_num(self, read_num):
        if not self.current_db_path:
            return None
        return self.controller.get_scan_by_read_num(self.current_db_path, read_num)

    def _delete_rows(self, delete_images: bool):
        read_nums = self._get_selected_read_nums()
        if not read_nums or not self.current_db_path:
            return
        msg = "선택한 결과와 이미지 파일을 함께 삭제할까요?" if delete_images else "선택한 결과만 삭제할까요?"
        if QMessageBox.question(self, "삭제 확인", msg) != QMessageBox.Yes:
            return
        for rn in read_nums:
            row = self._get_row_data_by_read_num(rn)
            if delete_images and row and row[4] and os.path.exists(row[4]):
                try:
                    os.remove(row[4])
                except Exception as e:
                    print(f"이미지 삭제 실패: {e}")
            self.controller.delete_scan_result(self.current_db_path, rn)
        for r in reversed(self._get_selected_rows()):
            self.main_grid.removeRow(r)
        self.update_statistics()
        self._schedule_summary_refresh()

    def _refresh_summary_async(self):
        if not self.current_db_path:
            return
        if self._summary_task_running:
            self._summary_refresh_pending = True
            return
        self._summary_task_running = True
        # 서비스에서 DB를 사용해 통계/요약 계산
        task = SummaryTask(self.db, self.current_db_path)
        task.signals.result.connect(self._apply_summary_data)
        task.signals.error.connect(self._on_summary_error)
        self.thread_pool.start(task)

    def _apply_summary_data(self, summary_rows, total, normal, error):
        self._summary_task_running = False
        if self._summary_refresh_pending:
            self._summary_refresh_pending = False
            self._schedule_summary_refresh(0)
        self.total_read = total
        self.lbl_total.setText(str(total))
        self.lbl_check.setText(str(error))
        self.control_panel.txt_temp.setText(str(total))

        counts = {(str(r[0]), str(r[1])): r[2] for r in summary_rows}

        self.summary_table.setUpdatesEnabled(False)
        for r in range(self.summary_table.rowCount()):
            place_item = self.summary_table.item(r, 0)
            room_item = self.summary_table.item(r, 1)
            if not place_item or not room_item:
                continue
            key = (place_item.text(), room_item.text())
            count = counts.get(key, 0)
            item = self.summary_table.item(r, 2)
            if item is None:
                self.summary_table.setItem(r, 2, self._item(str(count)))
            else:
                item.setText(str(count))
        self.summary_table.setUpdatesEnabled(True)

        sel = self.summary_table.selectionModel()
        if sel and sel.hasSelection():
            row = sel.selectedRows()[0].row()
            count_item = self.summary_table.item(row, 2)
            self.lbl_cur_cnt.setText(count_item.text() if count_item else "0")

    def _on_summary_error(self, msg):
        self._summary_task_running = False
        if self._summary_refresh_pending:
            self._summary_refresh_pending = False
        self._set_last_error_message(msg)

    def _schedule_summary_refresh(self, delay_ms=300):
        if self._summary_refresh_timer.isActive():
            self._summary_refresh_timer.stop()
        self._summary_refresh_timer.start(delay_ms)

    def _load_summary_from_db(self):
        """요약 테이블을 DB 기준으로 재구성."""
        if not self.current_db_path:
            return
        try:
            summary_rows = self.controller.get_summary_rows(self.current_db_path)
        except Exception:
            summary_rows = []

        if not summary_rows:
            summary_rows = []

        selected_key = None
        sel = self.summary_table.selectionModel()
        if sel and sel.hasSelection():
            row = sel.selectedRows()[0].row()
            place_item = self.summary_table.item(row, 0)
            room_item = self.summary_table.item(row, 1)
            if place_item and room_item:
                selected_key = (place_item.text(), room_item.text())

        self.summary_table.setUpdatesEnabled(False)
        self.summary_table.blockSignals(True)
        try:
            self.summary_table.setRowCount(0)
            def _room_key(v):
                try:
                    return int(str(v).strip())
                except Exception:
                    return str(v)

            for scanner_name, room_no, count, _ in sorted(
                summary_rows, key=lambda r: (str(r[0]), _room_key(r[1]))
            ):
                row = self.summary_table.rowCount()
                self.summary_table.insertRow(row)
                self.summary_table.setItem(row, 0, self._item(str(scanner_name)))
                self.summary_table.setItem(row, 1, self._item(str(room_no)))
                self.summary_table.setItem(row, 2, self._item(str(count)))

            if self.summary_table.rowCount() > 0:
                target_row = 0
                if selected_key:
                    for r in range(self.summary_table.rowCount()):
                        place_item = self.summary_table.item(r, 0)
                        room_item = self.summary_table.item(r, 1)
                        if place_item and room_item and (place_item.text(), room_item.text()) == selected_key:
                            target_row = r
                            break
                self.summary_table.selectRow(target_row)
        finally:
            self.summary_table.blockSignals(False)
            self.summary_table.setUpdatesEnabled(True)

        if self.summary_table.rowCount() > 0:
            place_item = self.summary_table.item(self.summary_table.currentRow(), 0)
            room_item = self.summary_table.item(self.summary_table.currentRow(), 1)
            if place_item and room_item:
                        self.reload_grid_from_db(place=place_item.text(), room=room_item.text())
        else:
            self.main_grid.setRowCount(0)
            self.lbl_cur_cnt.setText("0")

    def _on_main_grid_item_changed(self, item):
        if self._grid_block_changes or not self.current_db_path or item is None:
            return
        row = item.row()
        col = item.column()
        if col not in (2, 3):
            return
        read_num_item = self.main_grid.item(row, 0)
        if not read_num_item:
            return
        try:
            read_num = int(read_num_item.text())
        except Exception:
            return
        text = (item.text() or "").strip()
        if col == 2:
            self.controller.update_scan_meta(self.current_db_path, read_num, scanner_name=text)
        else:
            self.controller.update_scan_meta(self.current_db_path, read_num, room_no=text)
        self._schedule_summary_refresh()

    def _change_place_or_room(self, field_name: str):
        read_nums = self._get_selected_read_nums()
        if not read_nums or not self.current_db_path:
            return
        title = "고사장 변경" if field_name == "place" else "시험실 변경"
        text, ok = QInputDialog.getText(self, title, "변경할 값")
        if not ok or not text.strip():
            return
        for rn in read_nums:
            if field_name == "place":
                self.controller.update_scan_meta(self.current_db_path, rn, scanner_name=text.strip())
            else:
                self.controller.update_scan_meta(self.current_db_path, rn, room_no=text.strip())
        for r in self._get_selected_rows():
            col = 2 if field_name == "place" else 3
            item = self.main_grid.item(r, col)
            if item:
                item.setText(text.strip())
        self.update_statistics()
        self._schedule_summary_refresh()

    def _change_front_path(self):
        read_nums = self._get_selected_read_nums()
        if len(read_nums) != 1 or not self.current_db_path:
            QMessageBox.information(self, "안내", "1건만 선택해주세요.")
            return
        new_path, _ = QFileDialog.getOpenFileName(self, "앞면 경로 변경", "", "Images (*.jpg *.jpeg *.png *.bmp *.tif *.tiff)")
        if not new_path:
            return
        rn = read_nums[0]
        self.controller.update_scan_meta(self.current_db_path, rn, image_path=new_path)
        r = self._get_selected_rows()[0]
        item_path = self.main_grid.item(r, 7)
        item_name = self.main_grid.item(r, 8)
        if item_path:
            item_path.setText(new_path)
        if item_name:
            item_name.setText(os.path.basename(new_path))

    def _renumber_by_room(self):
        if not self.current_db_path:
            return
        all_rows = self.controller.get_all_scans(self.current_db_path)
        if not all_rows:
            return
        # row: (id, read_num, scanner_name, room_no, image_path, sheet_code, mark_result, is_valid, scan_time)
        ordered = sorted(all_rows, key=lambda r: (str(r[2]), str(r[3]), int(r[1])))
        ordered_read_nums = [r[1] for r in ordered]
        self.controller.renumber_read_nums(self.current_db_path, ordered_read_nums)
        self.reload_grid_from_db()
        self._schedule_summary_refresh()

    def _rename_image_files(self):
        if not self.current_db_path:
            return
        all_rows = self.controller.get_all_scans(self.current_db_path)
        if not all_rows:
            return
        if QMessageBox.question(self, "확인", "이미지 파일명을 일괄 변경할까요?") != QMessageBox.Yes:
            return
        for idx, row in enumerate(all_rows, start=1):
            path = row[4]
            if not path or not os.path.exists(path):
                continue
            base_dir = os.path.dirname(path)
            ext = os.path.splitext(path)[1]
            new_name = f"scan_{idx:05d}{ext}"
            new_path = os.path.join(base_dir, new_name)
            try:
                os.rename(path, new_path)
                self.controller.update_scan_meta(self.current_db_path, row[1], image_path=new_path)
            except Exception as e:
                print(f"파일명 변경 실패: {e}")
        self.reload_grid_from_db()
        self._schedule_summary_refresh()

    def reload_grid_from_db(self, place=None, room=None):
        """메인 그리드 갱신 (서비스에서 DB 읽기)."""
        if not self.current_db_path:
            return
        if place is None and room is None:
            sel = self.summary_table.selectionModel()
            if sel and sel.hasSelection():
                row = sel.selectedRows()[0].row()
                place_item = self.summary_table.item(row, 0)
                room_item = self.summary_table.item(row, 1)
                if place_item and room_item:
                    place = place_item.text()
                    room = room_item.text()
        self._grid_block_changes = True
        self.main_grid.setUpdatesEnabled(False)
        self.main_grid.setRowCount(0)
        if place is not None and room is not None:
            rows = self.controller.get_grid_rows(self.current_db_path, place, room)
        else:
            rows = self.controller.get_grid_rows(self.current_db_path)
        for row in rows:
            read_num = row[1]
            row_place = row[2]
            row_room = row[3]
            image_path = row[4]
            sheet_code = row[5]
            result_str = row[6]
            is_valid = row[7]
            error_message = row[9] if len(row) > 9 else ""
            review_done = row[13] if len(row) > 13 else 0
            if is_valid == 1:
                ui_status = ""
                review_status = "완료" if review_done else ""
                display_detail = ""
            else:
                ui_status = error_message if error_message else "오류"
                review_status = "완료" if review_done else "미점검"
                display_detail = result_str
            row_data = [
                str(read_num),
                str(sheet_code),
                str(row_place),
                str(row_room),
                ui_status,
                review_status,
                str(display_detail),
                str(image_path),
                os.path.basename(image_path) if image_path else "",
            ]
            self.main_grid.add_row_data(row_data)
            # 검토 상태 색상
            if review_status:
                item = self.main_grid.item(self.main_grid.rowCount() - 1, 5)
                if item:
                    if review_status == "미점검":
                        item.setForeground(Qt.red)
                    elif review_status == "완료":
                        item.setForeground(Qt.blue)
        self._grid_block_changes = False
        self.main_grid.setUpdatesEnabled(True)
        self._schedule_summary_refresh()

    def _on_summary_selected(self):
        sel = self.summary_table.selectionModel()
        if not sel or not sel.hasSelection():
            return
        row = sel.selectedRows()[0].row()
        place_item = self.summary_table.item(row, 0)
        room_item = self.summary_table.item(row, 1)
        if not place_item or not room_item:
            return
        place = place_item.text()
        room = room_item.text()
        self.reload_grid_from_db(place=place, room=room)







    def _find_text(self, from_current: bool):
        text, ok = QInputDialog.getText(self, "찾기", "검색어:")
        if not ok or not text:
            return
        start_row = 0
        if from_current:
            sel = self._get_selected_rows()
            if sel:
                start_row = sel[0] + 1
        for r in range(start_row, self.main_grid.rowCount()):
            for c in range(self.main_grid.columnCount()):
                item = self.main_grid.item(r, c)
                if item and text in item.text():
                    self.main_grid.selectRow(r)
                    self.main_grid.scrollToItem(item)
                    return
        QMessageBox.information(self, "찾기", "검색 결과가 없습니다.")

    def _copy_selected_rows(self):
        rows = self._get_selected_rows()
        if not rows:
            return
        lines = []
        for r in rows:
            vals = []
            for c in range(self.main_grid.columnCount()):
                item = self.main_grid.item(r, c)
                vals.append(item.text() if item else "")
            lines.append("\t".join(vals))
        QApplication.clipboard().setText("\n".join(lines))

    def _on_grid_context_menu(self, pos):
        if not self._get_selected_rows():
            return
        menu = QMenu(self)
        act_review = menu.addAction("현재건 판독결과 조회/수정")
        menu.addSeparator()
        act_copy = menu.addAction("복사")
        menu.addSeparator()
        act_del_all = menu.addAction("전체삭제+이미지 삭제")
        act_del_row = menu.addAction("선택삭제(이미지 제외)")
        menu.addSeparator()
        act_place = menu.addAction("고사장 변경")
        act_room = menu.addAction("시험실 변경")
        menu.addSeparator()
        act_front = menu.addAction("앞면 경로 변경")
        act_back = menu.addAction("뒷면 경로 변경")
        act_back.setEnabled(False)
        menu.addSeparator()
        act_renum = menu.addAction("고사장/시험실 순서로 번호 재부여")
        act_rename = menu.addAction("이미지파일명 일괄 변경")
        menu.addSeparator()
        act_find_start = menu.addAction("처음부터 찾기")
        act_find_next = menu.addAction("현재 이후부터 찾기")
        menu.addSeparator()
        act_recalc = menu.addAction("오류 표기 재계산")

        action = menu.exec_(self.main_grid.viewport().mapToGlobal(pos))
        if action == act_review:
            rn = self._get_selected_read_nums()[0]
            self._open_review_for_row(self._get_row_data_by_read_num(rn))
        elif action == act_copy:
            self._copy_selected_rows()
        elif action == act_del_all:
            self._delete_rows(delete_images=True)
        elif action == act_del_row:
            self._delete_rows(delete_images=False)
        elif action == act_place:
            self._change_place_or_room("place")
        elif action == act_room:
            self._change_place_or_room("room")
        elif action == act_front:
            self._change_front_path()
        elif action == act_renum:
            self._renumber_by_room()
        elif action == act_rename:
            self._rename_image_files()
        elif action == act_find_start:
            self._find_text(from_current=False)
        elif action == act_find_next:
            self._find_text(from_current=True)
        elif action == act_recalc:
            self._recalc_error_messages()

    def _recalc_error_messages(self):
        if not self.current_db_path:
            return
        if QMessageBox.question(self, "확인", "기존 데이터를 다시 판독하여 오류 표기를 갱신할까요?\n(시간이 다소 걸릴 수 있습니다)") != QMessageBox.Yes:
            return
        count = self.controller.recalc_error_messages(self.current_db_path)
        self.reload_grid_from_db()
        self._schedule_summary_refresh()
        QMessageBox.information(self, "완료", f"{count}건 오류 표기 재계산 완료")

    def update_statistics(self):
        """DB 통계(총 판독수/오류 매수) 갱신."""
        if not self.current_db_path:
            return
        self._refresh_summary_async()




