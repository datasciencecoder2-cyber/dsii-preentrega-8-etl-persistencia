"""Pruebas de extracción, limpieza, persistencia, atomicidad y reproducibilidad."""
from dataclasses import replace
from contextlib import closing
from pathlib import Path
import csv
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from src.extraer import extraer_ventas
from src.transformar import transformar_ventas
from src.cargar import cargar_ventas
from src.pipeline import ejecutar_pipeline

BASE = Path(__file__).resolve().parents[1]
ORIGEN = BASE / "datos" / "ventas_transaccionales.csv"
DDL = BASE / "schema.sql"


class TestETL(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.filas = extraer_ventas(ORIGEN)
        cls.ventas, cls.calidad = transformar_ventas(cls.filas)

    def test_01_csv_entrada_39_filas(self):
        self.assertEqual(len(self.filas), 39)

    def test_02_datos_limpios_30_ventas(self):
        self.assertEqual(len(self.ventas), 30)
        self.assertEqual(self.calidad["ventas_validas"], 30)

    def test_03_duplicados_dos(self):
        self.assertEqual(self.calidad["duplicados_identicos"], 2)

    def test_04_no_confirmados_tres(self):
        self.assertEqual(self.calidad["no_confirmadas"], 3)

    def test_05_invalidos_cuatro(self):
        self.assertEqual(self.calidad["filas_invalidas"], 4)

    def test_06_categoria_normalizada(self):
        self.assertEqual({v.categoria for v in self.ventas}, {"Alimentos", "Hogar", "Tecnologia"})

    def test_07_importes_centavos(self):
        v = next(v for v in self.ventas if v.id_venta == 1001)
        self.assertEqual(v.precio_unitario_centavos, 12050)
        self.assertEqual(v.total_centavos, 12050)

    def test_08_fechas_y_meses_coherentes(self):
        self.assertTrue(all(v.fecha[:7] == v.mes for v in self.ventas))
        self.assertTrue(all(len(v.fecha) == 10 for v in self.ventas))

    def test_09_cliente_vacio_se_descarta(self):
        filas = [dict(self.filas[0], cliente_id="")]
        with self.assertRaisesRegex(ValueError, "No existen ventas confirmadas"):
            transformar_ventas(filas)

    def test_10_conflicto_de_id_aborta(self):
        filas = [self.filas[0], dict(self.filas[0], cantidad="5")]
        with self.assertRaisesRegex(ValueError, "Conflicto en id_venta"):
            transformar_ventas(filas)

    def test_11_no_deja_persistencia_si_falla_CSV(self):
        with tempfile.TemporaryDirectory() as temporal:
            carpeta=Path(temporal)
            malo=carpeta/'malo.csv'
            malo.write_text('id_venta,fecha\n1,2026-01-01\n',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'Faltan columnas'):
                ejecutar_pipeline(malo,carpeta/'base.db',DDL,carpeta/'reporte.json')
            self.assertFalse((carpeta/'base.db').exists())

    def test_12_crea_SQLite_tabla_y_vista(self):
        with tempfile.TemporaryDirectory() as temporal:
            base=Path(temporal)/'analytics.db'
            carga=cargar_ventas(self.ventas,base,DDL)
            self.assertEqual(carga['filas_en_sqlite'], 30)
            with closing(sqlite3.connect(base)) as con:
                self.assertEqual(con.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='ventas_analiticas'").fetchone()[0],1)
                self.assertEqual(con.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='view' AND name='resumen_mensual'").fetchone()[0],1)

    def test_13_idempotencia_repetir_sin_duplicar(self):
        with tempfile.TemporaryDirectory() as temporal:
            base=Path(temporal)/'analytics.db'
            primera=cargar_ventas(self.ventas,base,DDL)
            segunda=cargar_ventas(self.ventas,base,DDL)
            self.assertEqual(primera['insertadas'],30)
            self.assertEqual(segunda['insertadas'],0)
            self.assertEqual(segunda['actualizadas'],0)
            self.assertEqual(segunda['sin_cambios'],30)
            self.assertEqual(segunda['filas_en_sqlite'],30)

    def test_14_actualiza_venta_corregida_no_duplica(self):
        with tempfile.TemporaryDirectory() as temporal:
            base=Path(temporal)/'analytics.db'
            cargar_ventas(self.ventas,base,DDL)
            original=self.ventas[0]
            corregida=replace(original,cantidad=original.cantidad+1,total_centavos=original.total_centavos+original.precio_unitario_centavos)
            resultado=cargar_ventas([corregida],base,DDL)
            self.assertEqual(resultado['actualizadas'],1)
            self.assertEqual(resultado['filas_en_sqlite'],30)
            with closing(sqlite3.connect(base)) as con:
                self.assertEqual(con.execute('SELECT total_centavos FROM ventas_analiticas WHERE id_venta=?',(original.id_venta,)).fetchone()[0],corregida.total_centavos)

    def test_15_rollback_simulado_revierte_primera_insercion(self):
        with tempfile.TemporaryDirectory() as temporal:
            base=Path(temporal)/'analytics.db'
            cargar_ventas(self.ventas,base,DDL)
            nuevo=replace(self.ventas[0],id_venta=99999)
            with self.assertRaisesRegex(RuntimeError,'Fallo simulado'):
                cargar_ventas([nuevo],base,DDL,simular_fallo=True)
            with closing(sqlite3.connect(base)) as con:
                self.assertEqual(con.execute('SELECT COUNT(*) FROM ventas_analiticas').fetchone()[0],30)
                self.assertEqual(con.execute('SELECT COUNT(*) FROM ventas_analiticas WHERE id_venta=99999').fetchone()[0],0)

    def test_16_reconciliacion_vista_con_total(self):
        with tempfile.TemporaryDirectory() as temporal:
            base=Path(temporal)/'analytics.db'
            resultado=cargar_ventas(self.ventas,base,DDL)
            total=sum(x['ingresos_centavos'] for x in resultado['resumen_mensual'])
            self.assertEqual(total,resultado['ingresos_centavos_en_sqlite'])
            self.assertEqual(total,self.calidad['total_centavos_en_archivo'])

    def test_17_integridad_suma_ayudada_por_CHECK(self):
        with tempfile.TemporaryDirectory() as temporal:
            base=Path(temporal)/'analytics.db'
            cargar_ventas(self.ventas,base,DDL)
            with closing(sqlite3.connect(base)) as con:
                with self.assertRaises(sqlite3.IntegrityError):
                    con.execute("UPDATE ventas_analiticas SET total_centavos=1 WHERE id_venta=1001")

    def test_18_reporte_existe_solo_al_terminar(self):
        with tempfile.TemporaryDirectory() as temporal:
            carpeta=Path(temporal)
            resultado=ejecutar_pipeline(ORIGEN,carpeta/'analytics.db',DDL,carpeta/'reporte.json')
            guardado=json.loads((carpeta/'reporte.json').read_text(encoding='utf-8'))
            self.assertEqual(guardado['calidad']['ventas_validas'],30)
            self.assertEqual(resultado['carga']['filas_en_sqlite'],30)

    def test_19_CLI_independiente_directorio_trabajo(self):
        with tempfile.TemporaryDirectory() as temporal:
            carpeta=Path(temporal)
            cmd=[sys.executable,str(BASE/'main.py'),'--db',str(carpeta/'db.sqlite'), '--reporte',str(carpeta/'reporte.json')]
            resultado=subprocess.run(cmd,cwd=temporal,capture_output=True,text=True,check=False)
            self.assertEqual(resultado.returncode,0,resultado.stderr)
            self.assertIn('ETL FINALIZADO: OK',resultado.stdout)
            self.assertTrue((carpeta/'db.sqlite').is_file())

    def test_20_CLI_repetido_mantiene_filas(self):
        with tempfile.TemporaryDirectory() as temporal:
            carpeta=Path(temporal)
            cmd=[sys.executable,str(BASE/'main.py'),'--db',str(carpeta/'db.sqlite'), '--reporte',str(carpeta/'reporte.json')]
            primero=subprocess.run(cmd,capture_output=True,text=True)
            segundo=subprocess.run(cmd,capture_output=True,text=True)
            self.assertEqual(primero.returncode,0,primero.stderr)
            self.assertEqual(segundo.returncode,0,segundo.stderr)
            self.assertIn('Insertadas: 0 | Actualizadas: 0 | Sin cambios: 30',segundo.stdout)

    def test_21_documentacion_contiene_requisitos_y_pasos(self):
        doc=(BASE/'README.md').read_text(encoding='utf-8')
        self.assertIn('## Requisitos',doc)
        self.assertIn('## Pasos para ejecutar',doc)
        self.assertIn('## Publicación incremental en GitHub',doc)


if __name__=='__main__':
    unittest.main()
