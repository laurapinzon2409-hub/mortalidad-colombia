"""Dashboard de mortalidad no fetal en Colombia, 2019 (DANE, EEVV).

Lee `data/mortalidad_2019.csv.gz` (generado con `python preparar_datos.py`).
Si ese archivo no existe pero sí están los Excel oficiales, lo genera al arrancar.
"""
import json
import os
from pathlib import Path

import pandas as pd
import plotly.express as px
from dash import Dash, Input, Output, dash_table, dcc, html

BASE = Path(__file__).resolve().parent
DATA = BASE / 'data'
CSV = DATA / 'mortalidad_2019.csv.gz'
GEOJSON = DATA / 'colombia_departamentos.geojson'

MESES = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']

# Rangos de GRUPO_EDAD1 definidos en la tabla de referencia de la actividad.
CATEGORIAS_EDAD = [
    ('Mortalidad neonatal', range(0, 5), 'Menos de 1 mes'),
    ('Mortalidad infantil', range(5, 7), '1 a 11 meses'),
    ('Primera infancia', range(7, 9), '1 a 4 años'),
    ('Niñez', range(9, 11), '5 a 14 años'),
    ('Adolescencia', range(11, 12), '15 a 19 años'),
    ('Juventud', range(12, 14), '20 a 29 años'),
    ('Adultez temprana', range(14, 17), '30 a 44 años'),
    ('Adultez intermedia', range(17, 20), '45 a 59 años'),
    ('Vejez', range(20, 25), '60 a 84 años'),
    ('Longevidad / Centenarios', range(25, 29), '85 años o más'),
    ('Edad desconocida', range(29, 30), 'Sin información'),
]
GRUPO_A_CATEGORIA = {g: nombre for nombre, grupos, _ in CATEGORIAS_EDAD for g in grupos}
ORDEN_EDAD = [f'{nombre} ({rango})' for nombre, _, rango in CATEGORIAS_EDAD]
ETIQUETA_EDAD = {nombre: f'{nombre} ({rango})' for nombre, _, rango in CATEGORIAS_EDAD}

COLORES_SEXO = {'Hombre': '#2f6db5', 'Mujer': '#d9632f', 'Indeterminado': '#8a8f98'}


def cargar_datos() -> pd.DataFrame:
    if not CSV.exists():
        from preparar_datos import construir  # genera el cruce desde los Excel DANE
        construir().to_csv(CSV, index=False, compression='gzip')
    df = pd.read_csv(CSV, dtype={'COD_DANE': str, 'COD_DEPARTAMENTO': str})
    df['COD_DEPARTAMENTO'] = df['COD_DEPARTAMENTO'].str.zfill(2)
    df['MUNICIPIO_ETQ'] = df['MUNICIPIO'].str.title() + ' (' + df['DEPARTAMENTO'].str.title() + ')'
    df['CATEGORIA_EDAD'] = df['GRUPO_EDAD1'].map(GRUPO_A_CATEGORIA).map(ETIQUETA_EDAD)
    for col in ['DEPARTAMENTO', 'SEXO_TXT', 'COD_MUERTE']:
        df[col] = df[col].astype('category')
    return df


df = cargar_datos()
with open(GEOJSON, encoding='utf-8') as f:
    geojson = json.load(f)

DEPARTAMENTOS = sorted(df['DEPARTAMENTO'].dropna().unique())
SEXOS = [s for s in ['Hombre', 'Mujer', 'Indeterminado'] if s in set(df['SEXO_TXT'].unique())]


def vacia(titulo, mensaje='No hay datos para la selección actual'):
    fig = px.scatter(title=titulo)
    fig.update_layout(
        xaxis={'visible': False}, yaxis={'visible': False},
        annotations=[{'text': mensaje, 'showarrow': False, 'xref': 'paper', 'yref': 'paper', 'x': .5, 'y': .5}],
    )
    return fig


def estilo(fig, **kw):
    opciones = {'margin': {'l': 40, 'r': 20, 't': 60, 'b': 40}, 'template': 'plotly_white',
                'font': {'family': 'Segoe UI, Arial, sans-serif'}, 'title': {'x': 0.02, 'font': {'size': 16}}}
    opciones.update(kw)
    fig.update_layout(**opciones)
    return fig


app = Dash(__name__, title='Mortalidad en Colombia 2019')
server = app.server  # gunicorn app:server

app.layout = html.Div([
    html.Header([
        html.H1('Mortalidad en Colombia 2019'),
        html.P('Dashboard interactivo de defunciones no fetales · Fuente: DANE, Estadísticas Vitales EEVV 2019'),
    ], className='encabezado'),
    html.Div([
        html.Div([
            html.Label('Departamento'),
            dcc.Dropdown(id='filtro-departamento', clearable=False, value='TODOS',
                         options=[{'label': 'Todos los departamentos', 'value': 'TODOS'}] +
                                 [{'label': d.title(), 'value': d} for d in DEPARTAMENTOS]),
        ], className='filtro'),
        html.Div([
            html.Label('Sexo'),
            dcc.Dropdown(id='filtro-sexo', multi=True, value=SEXOS, options=SEXOS, clearable=False),
        ], className='filtro'),
        html.Div([
            html.Label('Rango de meses'),
            dcc.RangeSlider(id='filtro-mes', min=1, max=12, step=1, value=[1, 12], allowCross=False,
                            marks={i + 1: m for i, m in enumerate(MESES)}),
        ], className='filtro ancho'),
    ], className='barra'),
    html.Div(
        'Los filtros se aplican a todo el tablero. El mapa y el gráfico por sexo comparan departamentos, '
        'por eso no se reducen al departamento elegido (el elegido aparece resaltado en el mapa).',
        className='nota'),
    html.Div(id='tarjetas', className='tarjetas'),
    html.Div([dcc.Graph(id='mapa'), dcc.Graph(id='linea-mensual')], className='fila'),
    html.Div([dcc.Graph(id='ciudades-violentas'), dcc.Graph(id='menor-mortalidad')], className='fila'),
    html.Div([dcc.Graph(id='sexo-departamento')], className='fila'),
    html.Div([dcc.Graph(id='histograma-edad')], className='fila'),
    html.Div([
        html.H2('Diez principales causas de muerte'),
        dash_table.DataTable(
            id='tabla-causas', page_size=10,
            columns=[{'name': 'Posición', 'id': 'posicion'}, {'name': 'Código CIE-10', 'id': 'codigo'},
                     {'name': 'Causa', 'id': 'causa'}, {'name': 'Total de casos', 'id': 'total'}],
            style_table={'overflowX': 'auto'},
            style_cell={'textAlign': 'left', 'padding': '8px', 'fontFamily': 'Segoe UI, Arial'},
            style_cell_conditional=[{'if': {'column_id': 'total'}, 'textAlign': 'right'}],
            style_header={'backgroundColor': '#17365D', 'color': 'white', 'fontWeight': 'bold'},
            style_data_conditional=[{'if': {'row_index': 'odd'}, 'backgroundColor': '#f6f8fb'}],
        ),
    ], className='tabla'),
    html.Footer('Fuente: DANE, Estadísticas Vitales EEVV 2019 (NoFetal2019, Divipola, CodigosDeMuerte). '
                'Aplicación académica.'),
], className='contenedor')


def tarjeta(valor, etiqueta):
    return html.Div([html.Strong(f'{valor:,}'.replace(',', '.')), html.Span(etiqueta)], className='tarjeta')


@app.callback(
    Output('tarjetas', 'children'), Output('mapa', 'figure'), Output('linea-mensual', 'figure'),
    Output('ciudades-violentas', 'figure'), Output('menor-mortalidad', 'figure'),
    Output('sexo-departamento', 'figure'), Output('histograma-edad', 'figure'),
    Output('tabla-causas', 'data'),
    Input('filtro-departamento', 'value'), Input('filtro-sexo', 'value'), Input('filtro-mes', 'value'),
)
def actualizar(departamento, sexos, meses):
    sexos = sexos or []
    base = df[df['SEXO_TXT'].isin(sexos) & df['MES'].between(meses[0], meses[1])]  # sin filtro de depto
    f = base if departamento == 'TODOS' else base[base['DEPARTAMENTO'] == departamento]
    ambito = 'Colombia' if departamento == 'TODOS' else departamento.title()
    periodo = f'{MESES[meses[0] - 1]}–{MESES[meses[1] - 1]}' if meses[0] != meses[1] else MESES[meses[0] - 1]

    # Tarjetas -----------------------------------------------------------
    cuenta_sexo = f['SEXO_TXT'].value_counts()
    tarjetas = [tarjeta(len(f), f'Defunciones · {ambito}, {periodo}'),
                tarjeta(int(cuenta_sexo.get('Hombre', 0)), 'Hombres'),
                tarjeta(int(cuenta_sexo.get('Mujer', 0)), 'Mujeres')]

    # 1. Mapa: total por departamento ------------------------------------
    por_depto = (base.groupby(['COD_DEPARTAMENTO', 'DEPARTAMENTO'], observed=True).size()
                 .reset_index(name='total'))
    por_depto['DEPARTAMENTO'] = por_depto['DEPARTAMENTO'].astype(str).str.title()
    if len(por_depto):
        mapa = px.choropleth_map(por_depto, geojson=geojson, locations='COD_DEPARTAMENTO',
                                 featureidkey='properties.DPTO_CCDGO', color='total',
                                 hover_name='DEPARTAMENTO', color_continuous_scale='Reds',
                                 map_style='white-bg', center={'lat': 4.6, 'lon': -73.5}, zoom=4.2,
                                 labels={'total': 'Defunciones', 'COD_DEPARTAMENTO': 'Código'},
                                 title='Total de muertes por departamento, 2019')
        mapa.update_traces(marker_line_width=0.6, marker_line_color='#ffffff')
        if departamento != 'TODOS':
            sel = por_depto[por_depto['DEPARTAMENTO'].str.upper() == departamento]
            mapa.add_traces(px.choropleth_map(sel, geojson=geojson, locations='COD_DEPARTAMENTO',
                                              featureidkey='properties.DPTO_CCDGO')
                            .update_traces(marker_opacity=0, marker_line_width=3, marker_line_color='#17365d',
                                           hoverinfo='skip', showscale=False).data)
        estilo(mapa, coloraxis_colorbar={'title': 'Defunciones'}, margin={'l': 0, 'r': 0, 't': 50, 'b': 0})
    else:
        mapa = vacia('Total de muertes por departamento, 2019')

    # 2. Línea: muertes por mes ------------------------------------------
    por_mes = f.groupby('MES').size().reindex(range(meses[0], meses[1] + 1), fill_value=0).reset_index(name='total')
    por_mes['mes_txt'] = por_mes['MES'].map(lambda m: MESES[m - 1])
    linea = px.line(por_mes, x='mes_txt', y='total', markers=True,
                    labels={'mes_txt': 'Mes (2019)', 'total': 'Defunciones'},
                    title=f'Total de muertes por mes · {ambito}')
    linea.update_traces(line_color='#17365d')
    linea.update_yaxes(rangemode='tozero')
    estilo(linea)

    # 3. Barras: 5 municipios con más muertes por arma de fuego (X95) ----
    x95 = f[f['COD_MUERTE'].astype(str).str.startswith('X95')]
    top5 = (x95.groupby('MUNICIPIO_ETQ').size().sort_values(ascending=False).head(5)
            .reset_index(name='total').sort_values('total'))
    titulo_x95 = 'Cinco ciudades con más homicidios por arma de fuego (X95)'
    if len(top5):
        fig_x95 = px.bar(top5, x='total', y='MUNICIPIO_ETQ', orientation='h', text='total',
                         labels={'total': 'Casos X95', 'MUNICIPIO_ETQ': 'Ciudad'}, title=titulo_x95)
        fig_x95.update_traces(marker_color='#b3261e', textposition='outside', cliponaxis=False)
        fig_x95.update_xaxes(range=[0, top5['total'].max() * 1.15])
        estilo(fig_x95, margin={'l': 200, 'r': 40, 't': 60, 'b': 40})
    else:
        fig_x95 = vacia(titulo_x95)

    # 4. Circular: 10 municipios con menor mortalidad --------------------
    # Se consideran municipios con al menos un registro; el desempate es
    # alfabético (hay varios municipios empatados con 1 defunción).
    menor = (f.groupby('MUNICIPIO_ETQ').size().reset_index(name='total')
             .sort_values(['total', 'MUNICIPIO_ETQ']).head(10))
    titulo_menor = f'Diez municipios con menor número de muertes · {ambito}'
    if len(menor):
        pie = px.pie(menor, names='MUNICIPIO_ETQ', values='total', title=titulo_menor,
                     color_discrete_sequence=px.colors.qualitative.Set3)
        pie.update_traces(textinfo='value', hovertemplate='%{label}<br>%{value} defunciones<extra></extra>')
        estilo(pie, legend={'font': {'size': 11}})
    else:
        pie = vacia(titulo_menor)

    # 6. Barras apiladas: sexo por departamento ---------------------------
    sexo_depto = base.groupby(['DEPARTAMENTO', 'SEXO_TXT'], observed=True).size().reset_index(name='total')
    sexo_depto['DEPARTAMENTO'] = sexo_depto['DEPARTAMENTO'].astype(str).str.title()
    orden = sexo_depto.groupby('DEPARTAMENTO')['total'].sum().sort_values(ascending=False).index.tolist()
    if len(sexo_depto):
        fig_sexo = px.bar(sexo_depto, x='DEPARTAMENTO', y='total', color='SEXO_TXT', barmode='stack',
                          category_orders={'DEPARTAMENTO': orden}, color_discrete_map=COLORES_SEXO,
                          labels={'DEPARTAMENTO': 'Departamento', 'total': 'Defunciones', 'SEXO_TXT': 'Sexo'},
                          title='Muertes por sexo y departamento')
        fig_sexo.update_xaxes(tickangle=-45)
        estilo(fig_sexo, margin={'l': 50, 'r': 20, 't': 60, 'b': 150}, legend_title_text='Sexo')
    else:
        fig_sexo = vacia('Muertes por sexo y departamento')

    # 7. Histograma: distribución por grupo de edad -----------------------
    if len(f):
        fig_edad = px.histogram(f, x='CATEGORIA_EDAD', category_orders={'CATEGORIA_EDAD': ORDEN_EDAD},
                                labels={'CATEGORIA_EDAD': 'Grupo de edad (GRUPO_EDAD1)'},
                                title=f'Distribución de muertes por grupo de edad · {ambito}')
        fig_edad.update_traces(marker_color='#2f6db5')
        fig_edad.update_layout(yaxis_title='Defunciones', bargap=0.05)
        fig_edad.update_xaxes(tickangle=-30)
        estilo(fig_edad, margin={'l': 50, 'r': 20, 't': 60, 'b': 130})
    else:
        fig_edad = vacia('Distribución de muertes por grupo de edad')

    # 5. Tabla: 10 principales causas -------------------------------------
    causas = (f.groupby(['COD_MUERTE', 'NOMBRE_CAUSA'], observed=True).size().reset_index(name='total')
              .sort_values('total', ascending=False).head(10).reset_index(drop=True))
    causas = causas[causas['total'] > 0]
    tabla = [{'posicion': i + 1, 'codigo': str(r.COD_MUERTE), 'causa': r.NOMBRE_CAUSA, 'total': f'{r.total:,}'.replace(',', '.')}
             for i, r in causas.iterrows()]

    return tarjetas, mapa, linea, fig_x95, pie, fig_sexo, fig_edad, tabla


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8050)), debug=False)
