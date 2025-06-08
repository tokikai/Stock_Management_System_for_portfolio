# -*- coding: utf-8 -*-
"""
DB初期化用スクリプト
このスクリプトを実行すると、DBに必要なテーブルが作成されます。
"""

from app import app
from models import db

# アプリケーションコンテキスト内でDB初期化を実行
with app.app_context():
  db.create_all()
  print("データベースの初期化が完了しました。")