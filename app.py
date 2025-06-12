"""
pip install -r requirement.txt
python app.py
"""
"""
Flaskによる商品一覧・登録・削除サンプルアプリ
"""

from flask import Flask, render_template, request, redirect, url_for, flash
from models import db, Product, StockHistory
import sqlalchemy
import os
import pandas as pd
from statsmodels.tsa.statespace.sarimax import SARIMAX  # SARIMAモデルをインポート
import time
from ChatGPTManager import get_chatgpt_comment
from dotenv import load_dotenv


load_dotenv()

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('SQLALCHEMY_DATABASE_URI')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'your_secret_key'

chatgpt_cache = {"comment": None, "timestamp": 0}
CACHE_SECONDS = 3600

# DB初期化
db.init_app(app)


@app.route('/')
def product_list():
  """
  商品一覧画面を表示する
  在庫数が発注点未満の商品をアラート対象とする
  """
  products = Product.query.all()
  products_with_stock = []
  for product in products:
    total_stock = db.session.query(db.func.sum(StockHistory.quantity)).filter_by(product_id=product.product_id).scalar()
    if total_stock is None:
      total_stock = 0
    products_with_stock.append((product, total_stock))
    alert_products = [p for p in products if p.current_stock <= p.reorder_point]

    now = time.time()
    if chatgpt_cache["comment"] is None or now - chatgpt_cache["timestamp"] > CACHE_SECONDS:
      chatgpt_cache["comment"] = get_chatgpt_comment()
      chatgpt_cache["timestamp"] = now
    chatgpt_comment = chatgpt_cache["comment"]
  return render_template(
    'product_list.html',
    products_with_stock=products_with_stock, 
    products=products,
    alert_products=alert_products,
    response=chatgpt_comment
    )


@app.route('/add', methods=['GET', 'POST'])
def add_product():
  """
  新規商品登録画面と登録処理
  """
  if request.method == 'POST':
    # フォームからデータ取得
    category = request.form['category']
    name = request.form['name']
    price = request.form['price']
    reorder_point = request.form['reorder_point']
    memo = request.form['memo']
    # 商品登録
    new_product = Product(
      category=category,
      name=name,
      price=int(price),
      reorder_point=int(reorder_point),
      memo=memo
    )
    db.session.add(new_product)
    try:
      db.session.commit()
      flash('商品を登録しました。')
    except sqlalchemy.exc.DataError:
      db.session.rollback()
      flash('数値が多きすぎます。')
    return redirect(url_for('product_list'))
  return render_template('product_form.html')


@app.route('/delete/<uuid:product_id>', methods=['POST'])
def delete_product(product_id):
  """
  商品を削除する
  """
  product = Product.query.get(product_id)
  if product:
    db.session.delete(product)
    db.session.commit()
    flash('商品を削除しました。')
  else:
    flash('商品が見つかりません。')
  return redirect(url_for('product_list'))


@app.route('/stock_history')
def stock_history():
  """
  在庫変動履歴を表示する
  """
  products = {p.product_id: p.name for p in Product.query.all()}
  histories = StockHistory.query.order_by(StockHistory.date.desc(), StockHistory.id).all()
  stock_with_products = []

  # 各商品ごとに累積在庫数を計算
  stock_totals = {}
  for history in histories:
    pid = history.product_id
    # 累積加算
    prev_total = stock_totals.get(pid, 0)
    new_total = prev_total + history.quantity
    stock_totals[pid] = new_total
    product_name = products.get(pid, "商品名不明")
    stock_with_products.append((history, product_name, new_total))

  return render_template('stock_history.html', stock_with_products=stock_with_products)

@app.route('/stock_mng', methods=['GET', 'POST'])
def stock_mng():
  """
  在庫の入庫・出庫処理
  """
  products = Product.query.all()
  
  if request.method == 'POST':
    product_id = request.form['product_id']
    quantity = request.form['quantity']
    revenue = request.form['revenue']
    date = request.form['date']
    movement_type = request.form['movement_type']
    memo = request.form['memo']

     # バリデーションチェック
    if not product_id:
      flash('商品を選択してください。')
      return redirect(url_for('stock_movement'))
    
    if not quantity.isdigit() or int(quantity) <= 0:
      flash('数量は正の整数でなければなりません。')
      return redirect(url_for('stock_movement'))
    
    if float(revenue) < 0:
      flash('販売収益額は正の値でなければなりません。')
      return redirect(url_for('stock_movement'))
    
    prev_quantity = db.session.query(db.func.sum(StockHistory.quantity)).filter_by(product_id=product_id).scalar()
    if prev_quantity is None:
      prev_quantity = 0

    # 入庫なら正、出庫なら負の値を記録
    if movement_type == '入庫':
      delta_quantity = int(quantity)
    else:
      delta_quantity = -int(quantity)
      if prev_quantity + delta_quantity < 0:
        flash('在庫数が不足しています。')
        return redirect(url_for('stock_movement'))

    # 履歴に「増減量」を記録
    new_stock_history = StockHistory(
      product_id=product_id,
      date=date,
      quantity=delta_quantity,  # 増減量
      revenue=float(revenue),
      memo=memo
    )

    db.session.add(new_stock_history)
    db.session.commit()
    flash('在庫の入庫・出庫が登録されました。')
    
    return redirect(url_for('product_list'))
  
  return render_template('stock_mng_form.html', products=products)

@app.route('/forecast/<uuid:product_id>', methods=['GET'])
def forecast(product_id):
  """
  在庫状況をARIMA/SARIMAモデルで予測する
  """
  stock_history = StockHistory.query.filter_by(product_id=product_id).order_by(StockHistory.date).all()
  
  # データフレームの作成
  data = {
    'ds': [],
    'y': []
  }
  for record in stock_history:
    data['ds'].append(record.date)
    data['y'].append(record.quantity)
  df = pd.DataFrame(data)
  
  # データが十分にあるかチェック
  if len(df) < 3:
    flash('予測に十分なデータがありません。')
    return redirect(url_for('product_list'))

  df = df.groupby('ds').sum() # 日付ごとにデータを集約
  df.index = pd.to_datetime(df.index)

  df = df.asfreq('D')  # 日付の欠損を補完（在庫履歴が毎日でない場合）

  # 欠損値は直前値で補完
  df['y'].fillna(method='ffill', inplace=True)
  df['y'].fillna(0, inplace=True)

  # SARIMAモデルの定義と学習
  model = SARIMAX(df['y'], order=(1,1,1), seasonal_order=(0,1,1,7))
  model_fit = model.fit(disp=False)

  # 未来30日を予測
  forecast_steps = 30
  pred = model_fit.get_forecast(steps=forecast_steps)
  pred_index = pd.date_range(df.index[-1] + pd.Timedelta(days=1), periods=forecast_steps, freq='D')
  forecast_df = pd.DataFrame({
    'ds': pred_index,
    'yhat': pred.predicted_mean,
    'yhat_lower': pred.conf_int()['lower y'],
    'yhat_upper': pred.conf_int()['upper y']
  })

  forecast_df['ds'] = forecast_df['ds'].dt.strftime('%Y-%m-%d')

  return render_template('forecast.html', forecast=forecast_df)


if __name__ == '__main__':
  app.run(debug=True)