# ... 既存のインポート ...
from openai import OpenAI
import os
import psycopg2
from dotenv import load_dotenv

# .envファイルから環境変数を読み込む
load_dotenv()

def fetch_ai_prediction_materials():
  """
  PostgreSQLからai予測素材テーブルの内容を取得する関数
  戻り値: レコードのリスト（各要素はdict）
  """
  # DB接続情報（環境変数から取得）
  conn = psycopg2.connect(
    dbname=os.environ.get("POSTGRES_DB"),
    user=os.environ.get("POSTGRES_USER"),
    password=os.environ.get("POSTGRES_PASSWORD"),
    host=os.environ.get("POSTGRES_HOST"),
    port=int(os.environ.get("POSTGRES_PORT", 5432))
  )
  conn.set_client_encoding('UTF8')  # 念のためUTF-8を明示
  cur = conn.cursor()
  # 必要なカラムを取得
  cur.execute("SELECT id, created_at, source_url, content_text, meta_json, memo FROM ai予測素材 ORDER BY created_at DESC LIMIT 5;")
  rows = cur.fetchall()
  materials = []
  for row in rows:
    # psycopg2はtext型をstrで返すため、decodeは不要
    materials.append({
      "id": row[0],
      "created_at": row[1],
      "source_url": row[2],
      "content_text": row[3],  # そのままstrとして利用
      "meta_json": row[4],     # 正しいカラム位置に修正
      "memo": row[5]           # そのままstrとして利用
    })
  cur.close()
  conn.close()
  return materials

def get_chatgpt_comment():
  """
  ai予測素材の内容をChatGPTに渡し、ホテルの混雑予測レベル（5段階）を推論させる関数
  戻り値: ChatGPTの推論結果（str）
  """
  materials = fetch_ai_prediction_materials()
  material_texts = []
  for m in materials:
    material_texts.append(
      f"【素材ID:{m['id']} 日時:{m['created_at']}】\n内容:{m['content_text']}\nメモ:{m['memo']}\nURL:{m['source_url']}\nJSON情報:{m['meta_json']}\n"
    )
  prompt = (
    "以下はホテルの混雑予測に関する素材です。\n"
    + "\n".join(material_texts)
    + "\nこれらの情報をもとに、今後のホテルの混雑予測レベルを5段階（1:非常に空いている〜5:非常に混雑）で推論し、その理由も簡潔に述べてください。"
    + "\n理由を述べる際の条件:①content_textの情報を見て、「?月?日は、???が開催されます。(???の日です。)」のようにイベント内容を明らかにする②金・土・日曜日は基本的にレベル4程度混雑している事も踏まえて考察する。"
  )
  client = OpenAI(
      api_key=os.environ.get("OPENAI_API_KEY"),
  )

  completion = client.chat.completions.create(
      model="gpt-4o",
      messages=[
          {"role": "system", "content": "あなたは別府市のとあるホテルの混雑状況予測アドバイザーです。"},
          {
              "role": "user",
              "content": prompt,
          },
      ],
  )
  return completion.choices[0].message.content
    