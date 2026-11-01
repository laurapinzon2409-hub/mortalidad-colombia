"""Preprocesa los archivos oficiales del DANE (EEVV 2019) y genera un CSV liviano.

Uso:  python preparar_datos.py

Entradas (carpeta data/):  NoFetal2019.xlsx, Divipola.xlsx, CodigosDeMuerte.xlsx
Salida:                    data/mortalidad_2019.csv.gz

Por qué existe: leer el Excel de 19 MB con openpyxl consume cientos de MB de
RAM y varios segundos. En un plan gratuito de PaaS (512 MB) eso puede tumbar
la app, así que el cruce se hace una sola vez y la app lee el resultado.
"""
from pathlib import Path
import pandas as pd

DATA = Path(__file__).resolve().parent / 'data'
SALIDA = DATA / 'mortalidad_2019.csv.gz'


def construir() -> pd.DataFrame:
    # --- Defunciones no fetales ------------------------------------------
    df = pd.read_excel(
        DATA / 'NoFetal2019.xlsx', sheet_name='No_Fetales_2019',
        dtype={'COD_DANE': str, 'COD_DEPARTAMENTO': str, 'COD_MUNICIPIO': str},
    )
    df = df[df['AÑO'] == 2019].copy()
    df['COD_DANE'] = df['COD_DANE'].str.zfill(5)
    df['COD_DEPARTAMENTO'] = df['COD_DEPARTAMENTO'].str.zfill(2)
    df['COD_MUERTE'] = df['COD_MUERTE'].astype(str).str.strip().str.upper()

    # --- Divipola: nombres de departamento y municipio -------------------
    div = pd.read_excel(DATA / 'Divipola.xlsx', sheet_name='Hoja1', dtype=str)
    div['COD_DANE'] = div['COD_DANE'].str.zfill(5)
    div = div[['COD_DANE', 'DEPARTAMENTO', 'MUNICIPIO']].drop_duplicates('COD_DANE')
    df = df.merge(div, on='COD_DANE', how='left', validate='many_to_one')

    # --- Causas de muerte (CIE-10) ---------------------------------------
    cat = pd.read_excel(DATA / 'CodigosDeMuerte.xlsx', sheet_name='Final', header=8, dtype=str)
    c3, n3, c4, n4 = cat.columns[2], cat.columns[3], cat.columns[4], cat.columns[5]
    nombre4 = dict(zip(cat[c4].str.strip().str.upper(), cat[n4].str.strip()))
    nombre3 = dict(zip(cat[c3].str.strip().str.upper(), cat[n3].str.strip()))
    # Los códigos vienen a 4 caracteres (X950) o, en algunos casos, a 3 (F03).
    df['NOMBRE_CAUSA'] = df['COD_MUERTE'].map(nombre4).fillna(df['COD_MUERTE'].map(nombre3))

    # --- Variables legibles ----------------------------------------------
    df['SEXO_TXT'] = df['SEXO'].map({1: 'Hombre', 2: 'Mujer', 3: 'Indeterminado'})

    columnas = ['COD_DANE', 'COD_DEPARTAMENTO', 'DEPARTAMENTO', 'MUNICIPIO', 'MES',
                'SEXO_TXT', 'GRUPO_EDAD1', 'COD_MUERTE', 'NOMBRE_CAUSA']
    return df[columnas]


if __name__ == '__main__':
    out = construir()
    sin_geo = out['DEPARTAMENTO'].isna().sum()
    sin_causa = out['NOMBRE_CAUSA'].isna().sum()
    out.to_csv(SALIDA, index=False, compression='gzip')
    print(f'{len(out):,} defunciones -> {SALIDA.name} ({SALIDA.stat().st_size/1e6:.1f} MB)')
    print(f'Sin nombre de municipio/departamento: {sin_geo} | sin nombre de causa: {sin_causa}')
