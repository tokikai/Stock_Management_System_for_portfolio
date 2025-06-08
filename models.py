# DBモデル定義（SQLAlchemyなど）# 
# -*- coding: utf-8 -*-
"""
商品管理アプリ用のDBモデル定義
"""

from flask_sqlalchemy import SQLAlchemy
import uuid
from sqlalchemy.dialects.postgresql import UUID

db = SQLAlchemy()

# ... 既存のインポート ...

class StockHistory(db.Model):
  """
  在庫変動履歴テーブルのモデルクラス
  """
  __tablename__ = '在庫変動履歴'
  id = db.Column(db.Integer, primary_key=True)
  product_id = db.Column(UUID(as_uuid=True), db.ForeignKey('商品.product_id'), nullable=False)
  date = db.Column(db.Date, nullable=False)
  quantity = db.Column(db.Integer, nullable=False)
  revenue = db.Column(db.Numeric(8, 2), nullable=False)  # 変動後の在庫数
  memo = db.Column(db.Text)

class Product(db.Model):
  """
  商品テーブルのモデルクラス
  """
  __tablename__ = '商品'
  product_id = db.Column(UUID(as_uuid=True), primary_key=True, server_default=db.text("gen_random_uuid()"), unique=True, nullable=False)
  category = db.Column(db.String(100), nullable=False)
  name = db.Column(db.String(100), nullable=False)
  price = db.Column(db.Integer, nullable=False)
  reorder_point = db.Column(db.Integer, nullable=False)
  memo = db.Column(db.Text)

  @property
  def current_stock(self):
    """
    現在の在庫数を計算（履歴のquantity合計）
    """
    from models import StockHistory  # 循環インポート対策
    total = db.session.query(db.func.sum(StockHistory.quantity)).filter_by(product_id=self.product_id).scalar()
    return total if total is not None else 0