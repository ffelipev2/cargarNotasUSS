import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import app as notes


class GradeFixture(unittest.TestCase):
    def setUp(self):
        self.docente = pd.DataFrame({
            "N": [1, 2, 3, ""],
            "Rut": ["11-1", "22-2", "33-3", "Promedio"],
            "Nombre": ["Ana Perez", "Luis Soto", "Eva Ruiz", ""],
            "SOLEMNE 1": [55, 60, 40, 52],
            "SOLEMNE 2": ["", "", "", ""],
            "CONTROLES": [62, 63, 64, 63],
            "NF": ["", "", "", ""],
        })
        self.blackboard = pd.DataFrame({
            "Apellidos": ["Soto", "Perez", "Ruiz"],
            "Nombre": ["Luis", "Ana", "Eva"],
            "Nombre de usuario": ["user2", "user1", "user3"],
            "ID de estudiante": ["222", "111", "333"],
            "Último acceso": ["09/09/2026", "08/09/2026", "07/09/2026"],
            "Disponibilidad": ["Sí", "Sí", "Sí"],
            "Solemne II [Puntos totales: 100 Escala Chilena]": ["6,4", "5.5", ""],
            "Control 1": ["3.0", "4.0", "5.0"],
        })
        self.source = self.blackboard.columns[6]
        self.target = "SOLEMNE 2"


class GradeSelectionTests(GradeFixture):
    def test_choices_include_all_evaluations_and_exclude_access_and_identity(self):
        self.assertEqual([o["value"] for o in notes.get_target_options(self.docente)], ["3", "4", "5", "6"])
        self.assertEqual([o["value"] for o in notes.get_source_options(self.blackboard)], ["6", "7"])

    def test_selected_grade_matches_students_and_preserves_other_columns(self):
        result = notes.build_result_dataframe(self.docente, self.blackboard, self.source, self.target)
        self.assertEqual(result.dataframe[self.target].tolist(), [55, 64, 10, ""])
        self.assertEqual((result.matched_count, result.unmatched_count, result.skipped_count), (2, 1, 1))
        self.assertEqual(result.columns, list(self.docente.columns))
        pd.testing.assert_frame_equal(result.dataframe.drop(columns=self.target), self.docente.drop(columns=self.target))
        metadata = notes.build_result_metadata(result)
        self.assertEqual(metadata["grade_column"], self.target)
        self.assertEqual(metadata["source_column"], self.source)

    def test_changing_source_uses_requested_column(self):
        result = notes.build_result_dataframe(self.docente, self.blackboard, "Control 1", self.target)
        self.assertEqual(result.dataframe[self.target].tolist(), [40, 30, 50, ""])

    def test_empty_evaluation_remains_selectable_without_using_another_grade(self):
        self.blackboard[self.source] = ""
        result = notes.build_result_dataframe(self.docente, self.blackboard, self.source, self.target)
        self.assertEqual(result.dataframe[self.target].tolist(), [10, 10, 10, ""])
        self.assertEqual(result.matched_count, 0)

    def test_invalid_missing_and_metadata_selections_are_rejected(self):
        for selection in ({}, {"source": "4", "target": "4"}, {"source": "6", "target": "0"},
                          {"source": "999", "target": "4"}, {"source": "6", "target": "-1"}):
            with self.subTest(selection=selection), self.assertRaises(notes.ProcessingError):
                notes.resolve_grade_selection(self.docente, self.blackboard, selection)

    def test_three_column_roster_can_create_nota(self):
        roster = self.docente.iloc[:, :3]
        source, target = notes.resolve_grade_selection(roster, self.blackboard, {"source": "6", "target": "-1"})
        result = notes.build_result_dataframe(roster, self.blackboard, source, target)
        self.assertEqual(result.columns, ["N", "Rut", "Nombre", "nota"])
        self.assertEqual(result.dataframe["nota"].tolist(), [55, 64, 10, ""])


class GradeSelectionRoutesTests(GradeFixture):
    def setUp(self):
        super().setUp()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        slots = {key: {**value, "folder": root / key} for key, value in notes.UPLOAD_SLOTS.items()}
        self.patches = patch.multiple(notes, UPLOAD_SLOTS=slots, RESULT_DIR=root / "results")
        self.patches.start()
        self.addCleanup(self.patches.stop)
        self.client = notes.app.test_client()

    def upload(self):
        response = self.client.post("/process", data={
            "docente_file": (io.BytesIO(self.docente.to_csv(index=False).encode("utf-8")), "docente.csv"),
            "blackboard_file": (io.BytesIO(self.blackboard.to_csv(index=False).encode("utf-8")), "blackboard.csv"),
        }, follow_redirects=True)
        self.assertIn(b'id="target-column"', response.data)
        return response

    def test_upload_select_process_download_and_regenerate_keep_selection(self):
        page = self.upload()
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'id="target-column"', page.data)
        self.assertIn(b'SOLEMNE 2', page.data)
        self.assertEqual(list(notes.RESULT_DIR.glob("*.xlsx")), [])

        page = self.client.post("/process", data={"source_column": "6", "target_column": "4"}, follow_redirects=True)
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'class="note-cell selected-grade">64</td>', page.data)
        self.assertEqual(page.data.count(b'class="note-cell selected-grade"'), 4)
        self.assertIn(self.source.encode("utf-8"), page.data)
        with self.client.session_transaction() as session:
            result_name = session["result_file"]
            self.assertEqual(session["grade_selection"], {"source": "6", "target": "4"})

        response = self.client.get("/download-result")
        self.assertEqual(response.status_code, 200)
        downloaded = pd.read_excel(io.BytesIO(response.data))
        response.close()
        self.assertEqual(list(downloaded.columns), list(self.docente.columns))
        self.assertEqual(downloaded[self.target].iloc[:3].tolist(), [55, 64, 10])
        self.assertEqual(downloaded["CONTROLES"].tolist(), [62, 63, 64, 63])

        notes.get_result_metadata_path(result_name).unlink()
        self.assertIn(self.source.encode("utf-8"), self.client.get("/").data)
        (notes.RESULT_DIR / result_name).unlink()
        response = self.client.get("/download-result")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(pd.read_excel(io.BytesIO(response.data))[self.target].iloc[:3].tolist(), [55, 64, 10])
        response.close()

    def test_missing_selection_does_not_generate_automatic_result(self):
        self.upload()
        page = self.client.post("/process", follow_redirects=True)
        self.assertIn("Selecciona la evaluación".encode("utf-8"), page.data)
        response = self.client.get("/download-result")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(list(notes.RESULT_DIR.glob("*.xlsx")), [])

    def test_replacing_file_and_clearing_reset_selection_and_result(self):
        self.upload()
        self.client.post("/process", data={"source_column": "6", "target_column": "4"})
        self.client.post("/process", data={
            "blackboard_file": (io.BytesIO(self.blackboard.to_csv(index=False).encode("utf-8")), "replacement.csv"),
            "source_column": "7", "target_column": "3",
        })
        with self.client.session_transaction() as session:
            self.assertNotIn("grade_selection", session)
            self.assertNotIn("result_file", session)
        self.assertEqual(list(notes.RESULT_DIR.glob("*.xlsx")), [])
        self.client.post("/process", data={"source_column": "7", "target_column": "3"})
        self.client.post("/clear-all")
        with self.client.session_transaction() as session:
            self.assertNotIn("grade_selection", session)
            self.assertNotIn("result_file", session)
        self.assertEqual(list(notes.RESULT_DIR.glob("*.xlsx")), [])


if __name__ == "__main__":
    unittest.main()
