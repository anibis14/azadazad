import requests
import pandas as pd
import dash
from dash import dcc, html
from dash.dependencies import Input, Output, State
import plotly.express as px
import threading
import time
from datetime import datetime
from flask_caching import Cache

# Initialisation de la variable globale en haut du fichier
data_lock = threading.Lock()

# Variables globales pour stocker les données mises à jour
prices_df = pd.DataFrame()
solde = 0  # Solde initial
frais = 0
spread = 0
investissement = 0
historique = []

# Liste des brokers pour BTC/USD, ETH/USD, SOL/USD, BNB/USD, XRP/USD
BROKERS = {
    'Binance': {
        'BTC': 'https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT',
        'ETH': 'https://api.binance.com/api/v3/ticker/price?symbol=ETHUSDT',
        'SOL': 'https://api.binance.com/api/v3/ticker/price?symbol=SOLUSDT',
        'BNB': 'https://api.binance.com/api/v3/ticker/price?symbol=BNBUSDT',
        'XRP': 'https://api.binance.com/api/v3/ticker/price?symbol=XRPUSDT'
    },
    'Coinbase Pro': {
        'BTC': 'https://api.coinbase.com/v2/prices/BTC-USD/spot',
        'ETH': 'https://api.coinbase.com/v2/prices/ETH-USD/spot',
        'SOL': 'https://api.coinbase.com/v2/prices/SOL-USD/spot',
        'BNB': 'https://api.coinbase.com/v2/prices/BNB-USD/spot',
        'XRP': 'https://api.coinbase.com/v2/prices/XRP-USD/spot'
    },
    'Bitfinex': {
        'BTC': 'https://api-pub.bitfinex.com/v2/ticker/tBTCUSD',
        'ETH': 'https://api-pub.bitfinex.com/v2/ticker/tETHUSD',
        'SOL': 'https://api-pub.bitfinex.com/v2/ticker/tSOLUSD',
        'BNB': 'https://api-pub.bitfinex.com/v2/ticker/tBNBUSD',
        'XRP': 'https://api-pub.bitfinex.com/v2/ticker/tXRPUSD'
    }
}

# Fonction pour obtenir les prix des cryptomonnaies à partir des APIs des brokers
def get_broker_prices():
    prices = []
    timestamp = datetime.now()
    try:
        for broker, symbols in BROKERS.items():
            for symbol, url in symbols.items():
                response = requests.get(url)
                data = response.json()
                if broker in ['Binance']:
                    prices.append({'broker': broker, 'symbol': symbol, 'price': float(data['price']), 'timestamp': timestamp})
                elif broker == 'Coinbase Pro':
                    prices.append({'broker': broker, 'symbol': symbol, 'price': float(data['data']['amount']), 'timestamp': timestamp})
                elif broker == 'Bitfinex':
                    prices.append({'broker': broker, 'symbol': symbol, 'price': float(data[6]), 'timestamp': timestamp})
    except Exception as e:
        print(f"Error fetching prices: {e}")

    return prices

# Collecte des données de prix
def collect_all_prices():
    global prices_df
    try:
        new_data = get_broker_prices()
        with data_lock:
            prices_df = pd.concat([prices_df, pd.DataFrame(new_data)], ignore_index=True)
        print(f"Collected all prices: {prices_df.tail(1)}")  # Log pour vérifier les données combinées
    except Exception as e:
        print(f"Error collecting all prices: {e}")

# Fonction pour calculer le plus grand écart en pourcentage entre deux brokers pour chaque crypto
def calculate_max_spread(prices_df):
    max_spreads = {}
    symbols = prices_df['symbol'].unique()
    for symbol in symbols:
        symbol_df = prices_df[prices_df['symbol'] == symbol]
        max_spread = 0
        brokers = symbol_df['broker'].unique()
        for i in range(len(brokers)):
            for j in range(i + 1, len(brokers)):
                price_i = symbol_df[symbol_df['broker'] == brokers[i]]['price'].iloc[-1]
                price_j = symbol_df[symbol_df['broker'] == brokers[j]]['price'].iloc[-1]
                spread = abs(price_i - price_j) / min(price_i, price_j) * 100
                if spread > max_spread:
                    max_spread = spread
                    max_spread_brokers = (brokers[i], brokers[j])
        max_spreads[symbol] = (max_spread, max_spread_brokers)
    return max_spreads

# Fonction pour mettre à jour les données globales
def update_data():
    while True:
        collect_all_prices()
        time.sleep(1)  # Pause de 10 secondes entre chaque mise à jour

# Fonction pour calculer le profit net
def calculate_profit(investissement, spread_percent, frais_percent):
    return ((investissement * (1 + spread_percent / 100)) - (investissement * frais_percent / 100)) - investissement

# Création du dashboard avec Dash
def create_dashboard():
    app = dash.Dash(__name__)
    cache = Cache(app.server, config={'CACHE_TYPE': 'simple'})

    app.layout = html.Div(children=[
        html.H1(children='Crypto Prices Dashboard by Azad', style={'textAlign': 'center'}),

        dcc.Interval(
            id='interval-component',
            interval=1*1000,  # in milliseconds (10 seconds)
            n_intervals=0
        ),

        html.Div([
            html.Div([
                html.Label('Solde:'),
                html.Div(id='solde', children=f'{solde:.2f} USD', style={'fontSize': '24px', 'marginBottom': '20px'})
            ], style={'textAlign': 'left', 'width': '30%'}),

            html.Div([
                html.Table([
                    html.Tr([html.Th('Frais %'), html.Td(dcc.Input(id='frais-input', type='number', value=frais, step=0.1, style={'width': '100%'}))]),
                    html.Tr([html.Th('Spread %'), html.Td(dcc.Input(id='spread-input', type='number', value=spread, step=0.1, style={'width': '100%'}))]),
                    html.Tr([html.Th('Investissement'), html.Td(dcc.Input(id='investissement-input', type='number', value=investissement, step=10, style={'width': '100%'}))]),
                ], style={'border': '1px solid black', 'borderCollapse': 'collapse', 'width': '90%', 'marginBottom': '10px', 'textAlign': 'center'}),
                html.Button('Valider', id='valider-button', n_clicks=0, style={'width': '50%', 'marginTop': '10px'}),
                html.Div(id='confirmation-message', style={'marginTop': '20px', 'color': 'green'})
            ], style={'textAlign': 'center', 'width': '50%'}),
        ], style={'width': '100%', 'display': 'flex', 'justifyContent': 'space-between', 'padding': '10px'}),

        html.Div(id='table-container', style={'width': '100%', 'display': 'flex', 'justifyContent': 'center', 'marginBottom': '20px'}),

        html.Div(id='graphs-container', style={'display': 'block', 'width': '100%'}),

        html.H2('Historique des Positions', style={'textAlign': 'center', 'marginTop': '50px'}),
        html.Div(id='historique-container', style={'width': '100%', 'display': 'flex', 'justifyContent': 'center', 'marginTop': '20px'})
    ])

    @app.callback(
        [Output('graphs-container', 'children'),
         Output('table-container', 'children'),
         Output('solde', 'children'),
         Output('historique-container', 'children')],
        [Input('interval-component', 'n_intervals')],
        [State('frais-input', 'value'),
         State('spread-input', 'value'),
         State('investissement-input', 'value')]
    )
    def update_graphs_and_table(n, frais_percent, spread_percent, investissement_amount):
        global solde, frais, spread, investissement, historique
        try:
            frais = frais_percent
            spread = spread_percent
            investissement = investissement_amount
            global prices_df
            with data_lock:
                graphs = []
                for symbol in ['BTC', 'ETH', 'SOL', 'BNB', 'XRP']:
                    symbol_df = prices_df[prices_df['symbol'] == symbol]
                    if not symbol_df.empty:
                        fig = px.line(symbol_df, x='timestamp', y='price', color='broker', title=f"Prices for {symbol}/USD across Brokers")
                        graphs.append(html.Div([
                            dcc.Graph(figure=fig)
                        ], style={'width': '100%', 'padding': '10px'}))
                
                # Calcul du tableau des prix actuels et des écarts
                latest_prices = prices_df.groupby(['symbol', 'broker']).last().reset_index()
                max_spreads = calculate_max_spread(prices_df)

                table_header = [
                    html.Thead(html.Tr([html.Th("Symbol"), html.Th("Binance"), html.Th("Coinbase Pro"), html.Th("Bitfinex"), html.Th("Max Spread (%)")]))
                ]
                table_body = []
                for symbol in ['BTC', 'ETH', 'SOL', 'BNB', 'XRP']:
                    row = [html.Td(symbol)]
                    for broker in ['Binance', 'Coinbase Pro', 'Bitfinex']:
                        price = latest_prices[(latest_prices['symbol'] == symbol) & (latest_prices['broker'] == broker)]['price'].values
                        row.append(html.Td(f"{price[0]:.2f}" if len(price) > 0 else "N/A"))
                    max_spread, brokers = max_spreads[symbol]
                    row.append(html.Td(f"{max_spread:.2f}"))
                    table_body.append(html.Tr(row))

                    # Mise à jour du solde et historique si le spread est suffisant
                    if max_spread >= spread:
                        profit = calculate_profit(investissement, max_spread, frais)
                        solde += profit
                        historique.append({
                            'frais': frais,
                            'spread': max_spread,
                            'investissement': investissement,
                            'brokers': brokers,
                            'profit': profit,
                            'timestamp': datetime.now()
                        })

                table = html.Table(table_header + [html.Tbody(table_body)], style={'border': '1px solid black', 'borderCollapse': 'collapse', 'width': '80%', 'textAlign': 'center'})
                
                for row in table_body:
                    for cell in row.children:
                        cell.style = {'border': '1px solid black', 'padding': '5px'}

                # Création de l'historique des positions
                historique_header = [
                    html.Thead(html.Tr([html.Th("Timestamp"), html.Th("Frais %"), html.Th("Spread %"), html.Th("Investissement"), html.Th("Brokers"), html.Th("Profit")]))
                ]
                historique_body = [
                    html.Tr([html.Td(position['timestamp']), html.Td(position['frais']), html.Td(position['spread']),
                             html.Td(position['investissement']), html.Td(f"{position['brokers'][0]} / {position['brokers'][1]}"),
                             html.Td(f"{position['profit']:.2f}")]) for position in historique
                ]
                historique_table = html.Table(historique_header + [html.Tbody(historique_body)], style={'border': '1px solid black', 'borderCollapse': 'collapse', 'width': '80%', 'textAlign': 'center', 'marginTop': '20px'})
                
                for row in historique_body:
                    for cell in row.children:
                        cell.style = {'border': '1px solid black', 'padding': '5px'}

                solde_color = 'green' if solde >= 0 else 'red'
                return graphs, table, html.Div(f'{solde:.2f} USD', style={'color': solde_color}), historique_table
        except Exception as e:
            print(f"Error in update_graphs_and_table callback: {e}")
            return html.Div('Error updating graphs', style={'color': 'red'}), html.Div('Error updating table', style={'color': 'red'}), f'{solde:.2f} USD', html.Div()

    @app.callback(
        Output('confirmation-message', 'children'),
        [Input('valider-button', 'n_clicks')],
        [State('frais-input', 'value'),
         State('spread-input', 'value'),
         State('investissement-input', 'value')]
    )
    def update_confirmation_message(n_clicks, frais_percent, spread_percent, investissement_amount):
        if n_clicks > 0:
            return f"Valeurs prises en compte: Frais = {frais_percent}%, Spread = {spread_percent}%, Investissement = {investissement_amount} USD"
        return ""

    return app

# Démarrer la mise à jour des données en arrière-plan
data_thread = threading.Thread(target=update_data)
data_thread.start()

# Lancer le serveur Dash
if __name__ == '__main__':
    app = create_dashboard()
    app.run_server(debug=True, host='0.0.0.0', port=8050)
