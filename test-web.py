import requests
import pandas as pd
import dash
from dash import dcc, html
from dash.dependencies import Input, Output, State
import plotly.express as px
import threading
import time
import io
from datetime import datetime, timedelta
from flask_caching import Cache

# Initialisation de la variable globale en haut du fichier
last_transaction_time = datetime.min
data_lock = threading.Lock()

# URLs pour les APIs des brokers
APIS = {
    "Binance": "https://api.binance.com/api/v3/ticker/24hr",
    "Coinbase": "https://api.coinbase.com/v2/prices/",
    "Bitfinex": "https://api-pub.bitfinex.com/v2/ticker/",
    "Bittrex": "https://api.bittrex.com/v3/markets/tickers",
    "Huobi": "https://api.huobi.pro/market/tickers"
}

# Frais de transaction par broker (ajusté à 0.3%)
FEES = {
    "Binance": 0.15,  # 0.3%
    "Coinbase": 0.15,  # 0.3%
    "Bitfinex": 0.15,  # 0.3%
    "Bittrex": 0.15,  # 0.3%
    "Huobi": 0.15  # 0.3%
}

# Variables globales pour stocker les données mises à jour
prices_df = pd.DataFrame()
total_gain = 0
transaction_history = []
custom_fees = 0.15
capital_invested = 100
time_between_ops = 30
min_spread_percent = 0.4

# Collecte des données de prix depuis les APIs des brokers
def get_prices(broker):
    try:
        if broker == "Binance":
            response = requests.get(APIS["Binance"])
            data = response.json()
            df = pd.DataFrame(data)
            df = df[df['symbol'].isin(['BTCUSDT', 'ETHUSDT', 'LTCUSDT', 'XRPUSDT', 'BCHUSDT'])]
            df['price'] = df['lastPrice'].astype(float)
            df['symbol'] = df['symbol'].str.replace('USDT', 'USD')
        elif broker == "Coinbase":
            symbols = ['BTC-USD', 'ETH-USD', 'LTC-USD', 'XRP-USD', 'BCH-USD']
            data = []
            for symbol in symbols:
                response = requests.get(f"https://api.coinbase.com/v2/prices/{symbol}/spot")
                price = float(response.json()['data']['amount'])
                data.append({"symbol": symbol.replace('-', ''), "price": price})
            df = pd.DataFrame(data)
        elif broker == "Bitfinex":
            symbols = ['tBTCUSD', 'tETHUSD', 'tLTCUSD', 'tXRPUSD', 'tBCHUSD']
            data = []
            for symbol in symbols:
                response = requests.get(APIS["Bitfinex"] + symbol)
                price = float(response.json()[6])
                data.append({"symbol": symbol[1:], "price": price})
            df = pd.DataFrame(data)
        elif broker == "Bittrex":
            response = requests.get(APIS["Bittrex"])
            data = pd.read_json(io.StringIO(response.content.decode('utf-8-sig')))
            df = data[data['symbol'].isin(['BTC-USD', 'ETH-USD', 'LTC-USD', 'XRP-USD', 'BCH-USD'])]
            df['symbol'] = df['symbol'].str.replace('-', '')
        elif broker == "Huobi":
            response = requests.get(APIS["Huobi"])
            data = response.json()
            df = pd.DataFrame(data['data'])
            df = df[df['symbol'].isin(['btcusdt', 'ethusdt', 'ltcusdt', 'xrpusdt', 'bchusdt'])]
            df['symbol'] = df['symbol'].str.replace('usdt', 'usd').str.upper()
            df['price'] = df['close'].astype(float)
        df['broker'] = broker
        df['timestamp'] = datetime.now()
        print(f"Data fetched for {broker}: {df}")  # Log pour vérifier les données récupérées
        return df[['symbol', 'price', 'broker', 'timestamp']]
    except Exception as e:
        print(f"Error fetching {broker} prices: {e}")
        return pd.DataFrame()

def collect_all_prices():
    brokers = ["Binance", "Coinbase", "Bitfinex", "Bittrex", "Huobi"]
    prices = pd.concat([get_prices(broker) for broker in brokers], ignore_index=True)
    print(f"Collected all prices: {prices}")  # Log pour vérifier les données combinées
    return prices

def find_arbitrage_opportunities(prices_df):
    opportunities = []
    symbols = prices_df['symbol'].unique()

    for symbol in symbols:
        symbol_prices = prices_df[prices_df['symbol'] == symbol]

        for i, row in symbol_prices.iterrows():
            for j, other_row in symbol_prices.iterrows():
                if row['broker'] != other_row['broker']:
                    buy_broker = row['broker']
                    sell_broker = other_row['broker']

                    buy_price = row['price']
                    sell_price = other_row['price']
                    spread_percent = (sell_price - buy_price) / buy_price * 100

                    # Prendre position si le spread brut est supérieur ou égal au spread minimum défini par l'utilisateur
                    if spread_percent >= min_spread_percent:
                        buy_price_with_fees = buy_price * (1 + custom_fees / 100)
                        sell_price_with_fees = sell_price * (1 - custom_fees / 100)
                        profit = sell_price_with_fees - buy_price_with_fees

                        opportunities.append({
                            "symbol": symbol,
                            "buy_broker": buy_broker,
                            "sell_broker": sell_broker,
                            "buy_price": buy_price,
                            "sell_price": sell_price,
                            "profit": profit,
                            "timestamp": datetime.now()
                        })

    print(f"Arbitrage opportunities found: {opportunities}")  # Log pour vérifier les opportunités trouvées
    return pd.DataFrame(opportunities)


# Fonction pour exécuter les transactions d'arbitrage
def execute_arbitrage_opportunities(opportunities_df):
    global total_gain, transaction_history, last_transaction_time
    for i, opportunity in opportunities_df.iterrows():
        current_time = datetime.now()
        if (current_time - last_transaction_time).total_seconds() >= time_between_ops:
            net_profit = opportunity['profit']
            with data_lock:
                total_gain += net_profit
                transaction_history.append({
                    "symbol": opportunity['symbol'],
                    "buy_broker": opportunity['buy_broker'],
                    "sell_broker": opportunity['sell_broker'],
                    "profit": net_profit,
                    "timestamp": datetime.now()
                })
            print(f"Executed arbitrage: Bought {opportunity['symbol']} on {opportunity['buy_broker']} and sold on {opportunity['sell_broker']} for a net profit of {net_profit:.2f} USD")
            last_transaction_time = current_time

# Fonction pour mettre à jour les données globales
def update_data():
    global prices_df
    while True:
        new_data = collect_all_prices()
        with data_lock:
            prices_df = pd.concat([prices_df, new_data], ignore_index=True)
        print(f"Updated prices data: {prices_df}")  # Log pour vérifier les données mises à jour
        opportunities_df = find_arbitrage_opportunities(prices_df)
        execute_arbitrage_opportunities(opportunities_df)
        time.sleep(1)  # Pause de 1 seconde entre chaque mise à jour

# Fonction pour calculer l'écart maximum en pourcentage entre deux brokers
def calculate_max_spread(symbol_df):
    max_spread_info = {"symbol": "", "buy_broker": "", "sell_broker": "", "spread": 0}

    for i, row in symbol_df.iterrows():
        for j, other_row in symbol_df.iterrows():
            if row['broker'] != other_row['broker']:
                spread = (other_row['price'] - row['price']) / row['price'] * 100
                if spread > max_spread_info["spread"]:
                    max_spread_info = {
                        "symbol": row['symbol'],
                        "buy_broker": row['broker'],
                        "sell_broker": other_row['broker'],
                        "spread": spread
                    }

    print(f"Max spread for {symbol_df['symbol'].iloc[0]}: {max_spread_info}")  # Log pour vérifier le spread maximum
    return max_spread_info

# Création du dashboard avec Dash
def create_dashboard():
    app = dash.Dash(__name__)
    cache = Cache(app.server, config={'CACHE_TYPE': 'simple'})

    app.layout = html.Div(children=[
        html.H1(children='Crypto Prices and Arbitrage Dashboard'),

        html.Div([
            html.Div([
                html.Label('Transaction Fees (%)'),
                dcc.Input(id='fees-input', type='number', value=custom_fees, step=0.01, style={'width': '100%'})
            ], style={'padding': '5px'}),
            html.Div([
                html.Label('Capital Invested (USD)'),
                dcc.Input(id='capital-input', type='number', value=capital_invested, step=1, style={'width': '100%'})
            ], style={'padding': '5px'}),
            html.Div([
                html.Label('Time Between Operations (seconds)'),
                dcc.Input(id='time-input', type='number', value=time_between_ops, step=1, style={'width': '100%'})
            ], style={'padding': '5px'}),
            html.Div([
                html.Label('Minimum Spread (%)'),
                dcc.Input(id='spread-input', type='number', value=min_spread_percent, step=0.01, style={'width': '100%'})
            ], style={'padding': '5px'}),
            html.Button('Update Parameters', id='update-button', n_clicks=0, style={'marginTop': '10px'}),
            html.Div(id='update-notification', style={'marginTop': '10px', 'color': 'green'})
        ], style={'position': 'relative', 'top': '20px', 'left': '10px', 'width': '300px', 'padding': '10px', 'border': '1px solid #ccc', 'backgroundColor': '#f9f9f9'}),

        dcc.Interval(
            id='interval-component',
            interval=5*1000,  # in milliseconds (5 seconds)
            n_intervals=0
        ),

        html.Div(id='total-gain', style={'position': 'absolute', 'top': '10px', 'right': '10px', 'fontSize': 24, 'marginBottom': 20}),

        html.Div(id='graphs-container'),

        html.Div(children=[
            html.H2("Historique des Transactions"),
            html.Div(id='transaction-history')
        ]),

        # Ajout d'un div pour afficher les données brutes pour débogage
        html.Div(id='raw-data', style={'display': 'none'})
    ])

    @app.callback(
        [Output('total-gain', 'children'), Output('transaction-history', 'children'), Output('raw-data', 'children')],
        [Input('interval-component', 'n_intervals')]
    )
    @cache.memoize()
    def update_total_gain_and_history(n):
        try:
            global total_gain, transaction_history
            with data_lock:
                transactions = [html.Div([
                    html.P(f"{tx['timestamp']} - Bought {tx['symbol']} on {tx['buy_broker']} and sold on {tx['sell_broker']} for a net profit of {tx['profit']} USD")
                ]) for tx in transaction_history]
            print(f"Updating total gain and history: {total_gain}, {transaction_history}")  # Log pour vérifier la mise à jour du gain total et de l'historique
            raw_data_text = f"Total Gain: {total_gain}, Transactions: {transaction_history}"
            return html.H2(f'Total Net Gain: {total_gain:.2f} USD', style={'color': 'green' if total_gain > 0 else 'red'}), transactions, raw_data_text
        except Exception as e:
            print(f"Error in update_total_gain_and_history callback: {e}")
            return html.H2('Error updating data', style={'color': 'red'}), [], 'Error'

    @app.callback(
        Output('graphs-container', 'children'),
        [Input('interval-component', 'n_intervals')]
    )
    @cache.memoize()
    def update_graphs(n):
        try:
            global prices_df
            graphs = []
            with data_lock:
                print(f"Updating graphs with prices_df: {prices_df}")  # Log pour vérifier les données passées aux graphiques
                for symbol in prices_df['symbol'].unique():
                    symbol_df = prices_df[prices_df['symbol'] == symbol]
                    fig = px.line(symbol_df, x='timestamp', y='price', color='broker', title=f"Prices for {symbol}")

                    # Calculer l'écart maximum en pourcentage pour ce symbole
                    max_spread_info = calculate_max_spread(symbol_df)
                    spread_style = {'fontSize': 16}
                    if max_spread_info['spread'] >= 0.6:
                        spread_style.update({'color': 'green', 'fontWeight': 'bold'})
                    max_spread_text = f"Max Spread: {max_spread_info['spread']:.2f}% (Buy on {max_spread_info['buy_broker']}, Sell on {max_spread_info['sell_broker']})"

                    graphs.append(html.Div([
                        html.H2(f"{symbol} Prices"),
                        dcc.Graph(figure=fig),
                        html.Div(max_spread_text, style=spread_style)
                    ], style={'position': 'relative', 'display': 'inline-block', 'width': '45%', 'verticalAlign': 'top', 'margin': '10px'}))
            print(f"Graphs updated: {graphs}")  # Log pour vérifier les graphiques mis à jour
            return graphs
        except Exception as e:
            print(f"Error in update_graphs callback: {e}")
            return html.Div('Error updating graphs', style={'color': 'red'})

    @app.callback(
        [Output('update-button', 'n_clicks'), Output('update-notification', 'children')],
        [Input('update-button', 'n_clicks')],
        [State('fees-input', 'value'),
         State('capital-input', 'value'),
         State('time-input', 'value'),
         State('spread-input', 'value')]
    )
    def update_parameters(n_clicks, fees, capital, time, spread):
        try:
            global custom_fees, capital_invested, time_between_ops, min_spread_percent
            with data_lock:
                custom_fees = fees
                capital_invested = capital
                time_between_ops = time
                min_spread_percent = spread
            print(f"Parameters updated: Fees = {fees}%, Capital = {capital} USD, Time = {time} seconds, Spread = {spread}%")  # Log pour vérifier les paramètres mis à jour
            return 0, f'Parameters updated: Fees = {fees}%, Capital = {capital} USD, Time = {time} seconds, Spread = {spread}%'
        except Exception as e:
            print(f"Error in update_parameters callback: {e}")
            return n_clicks, 'Error updating parameters'

    return app

# Démarrer la mise à jour des données en arrière-plan
data_thread = threading.Thread(target=update_data)
data_thread.start()

# Lancer le serveur Dash
if __name__ == '__main__':
    prices_df = collect_all_prices()
    print(f"Initial prices data: {prices_df}")  # Log pour vérifier les données initiales
    app = create_dashboard()
    app.run_server(debug=True, host='0.0.0.0', port=8050)
