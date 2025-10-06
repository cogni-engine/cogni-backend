import os
import json
from fastapi import FastAPI
from supabase import create_client, Client
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv
from typing import List, Dict, Optional
import datetime

load_dotenv(dotenv_path=".env")

api_key = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=api_key)
app = FastAPI()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


# チャット履歴を保存するリスト（最小限）
chat_history: List[Dict[str, str]] = []

focused_task_id: Optional[int] = None

# モックタスクデータ
mock_tasks: List[Dict] = [
    {
        "id": 1,
        "title": "米を買う",
        "deadline": datetime.datetime(2024, 10, 6),
        "importance": 5,
        "urgency": 5,
        "status": "pending",
        "method": "近所のスーパーで魚沼産コシヒカリを5kg購入。できれば無洗米。",
        "reason": "今週中に家族の食事に必要。緊急でかつ日常生活に不可欠。"
    },
    {
        "id": 2,
        "title": "魚を買う",
        "deadline": datetime.datetime(2024, 10, 10),
        "importance": 4,
        "urgency": 3,
        "status": "pending",
        "method": "遠くのデパートの鮮魚売り場で旬の刺身用の鯛か鮭を購入。鮮度を優先。",
        "reason": "週末のパーティーで使うため。新鮮な魚で料理の質を上げたい。"
    },
    {
        "id": 3,
        "title": "ケーキを買う",
        "deadline": datetime.datetime(2024, 10, 10),
        "importance": 4,
        "urgency": 2,
        "status": "pending",
        "method": "都心の有名パティスリーでチーズケーキをホール購入。予約が必要なら事前に電話。",
        "reason": "妹の誕生日祝いで使うため。特別感を出すために高級感あるケーキを選びたい。"
    },
    {
        "id": 4,
        "title": "iPhone 15シリーズを選ぶ",
        "deadline": datetime.datetime(2024, 10, 15),
        "importance": 3,
        "urgency": 2,
        "status": "pending",
        "method": "Apple公式サイトや家電量販店で最新モデルを比較。ストレージは最低128GB以上。カメラ性能を重視してProモデルを検討。",
        "reason": "新しいスマホが必要。特にカメラ品質が重要で、予算は15万円程度。SNSや写真撮影に使う予定。"
    },
    {
        "id": 5,
        "title": "iPhone 15シリーズを購入",
        "deadline": datetime.datetime(2024, 10, 20),
        "importance": 3,
        "urgency": 1,
        "status": "pending",
        "method": "選んだモデルをヨドバシカメラで購入予定。ポイント還元率を確認し、AppleCare+も加入。",
        "reason": "選定したモデルを実際に使うため。支払いはクレジットカード分割で月1万円以内に収めたい。"
    },
    {
        "id": 6,
        "title": "早稲田の2次試験対策 - 水銀圧力計の仕組み理解",
        "deadline": datetime.datetime(2024, 10, 5),
        "importance": 5,
        "urgency": 5,
        "status": "pending",
        "method": """水銀圧力計について理解する。
1. 基本構造
    • U字型のガラス管に水銀を入れる。
    • 一方の管を大気に開けて、もう一方に測りたい気体をつなぐ。
    • 気体の圧力と大気圧の差によって、水銀の高さに差が生まれる。
2. 働き方の原理
    • 圧力は「面積あたりの力」。液体中では深さに比例して圧力が増す。
    • U字管の両端の水銀は互いに押し合いバランスする。
    • 気体側が強く押せば水銀が押し下げられ、高さの差で圧力がわかる。
3. なぜ水銀を使うのか
    • 密度がとても大きい（水の約13.6倍）。→ 圧力を測るのに必要な液柱の高さが短くてすむ。
      （例：1気圧を水で測ると約10mだが、水銀なら76cmでOK）
    • 蒸発しにくい。
    • 温度による体積変化が小さい（精度が高い）。""",
        "reason": "試験で水銀圧力計を説明できる必要がある。わからなければ家庭教師に質問する。"
    },
    {
        "id": 7,
        "title": "早稲田の2次試験対策 - 水銀圧力計の問題演習",
        "deadline": datetime.datetime(2024, 10, 5),
        "importance": 5,
        "urgency": 5,
        "status": "pending",
        "method": """問題演習を解く。
問題: 気体の圧力を測るために水銀柱を用いた。大気開放側の水銀の高さが気体側よりも5.0cm高いことが観測された。大気圧は76.0cmHgとする。
このとき、気体の圧力は何cmHgか。また、それはatmでいくらか？""",
        "reason": "単なる理解だけでなく、数値問題として解答できる能力をつける。"
    },
    {
        "id": 8,
        "title": "早稲田の2次試験対策 - ゴム気圧計の仕組み理解",
        "deadline": datetime.datetime(2024, 10, 5),
        "importance": 5,
        "urgency": 5,
        "status": "pending",
        "method": """ゴム気圧計（アネロイド気圧計）の仕組みを理解する。
1. 基本構造
    • 金属製の薄い円筒（アネロイドカプセル）の中をほぼ真空にしてある。
    • 外の空気圧が変わると、円筒が押しつぶされたり膨らんだりする。
    • 変形をてこやバネで針に伝えて、圧力（気圧）を目盛で読み取る。
つまり「外の空気の力」と「金属やバネの弾性力」が釣り合う位置で止まる。
2. 原理（ゴム膜のイメージ）
    • 外圧が増えると膜は押され潰れる。
    • 外圧が減ると膜は弾性力で外に戻ろうとする。
    • 変形量が圧力に比例する（フックの法則 F = kx）。
    • 圧力の変化と膜の変形量が対応する。""",
        "reason": "仕組みを正確に説明できる必要がある。わからなければ家庭教師に質問する。"
    },
    {
        "id": 9,
        "title": "早稲田の2次試験対策 - ゴム気圧計の問題演習",
        "deadline": datetime.datetime(2024, 10, 5),
        "importance": 5,
        "urgency": 5,
        "status": "pending",
        "method": """問題演習を解く。
問題: あるゴム気圧計で外圧が1.00atmのとき膜が0.20mm潰れて針が目盛りを指した。
この膜はフックの法則に従い、k = 3.8×10^4N/m の弾性係数をもつ。
膜の面積を A = 2.0cm^2 とすると、外圧が0.95atmになったとき膜はどれだけ変形するか？""",
        "reason": "圧力と弾性力の関係を数値計算できるようにする。"
    },
    {
        "id": 10,
        "title": "早稲田の2次試験対策 - 気圧計に関する英文読解",
        "deadline": datetime.datetime(2024, 10, 5),
        "importance": 4,
        "urgency": 4,
        "status": "pending",
        "method": """英文を読み要点を整理する。
Passage Example: Atmospheric Pressure and Instruments of Measurement
本文: 
Atmospheric pressure is one of the most fundamental yet invisible forces that surround our daily lives. It refers to the continuous weight of the air pressing down on the surface of the Earth. Although we rarely notice it, this pressure influences weather patterns, human health, and even the design of buildings and aircraft. To understand and predict such phenomena, scientists have long relied on various instruments that transform this invisible force into measurable data.

The mercury barometer is perhaps the most classical example. Developed in the seventeenth century, it uses a column of mercury that rises or falls according to changes in the surrounding air pressure. Its reliability lies in the high density and stability of mercury, which makes the instrument precise and consistent. However, because mercury is heavy and toxic, the barometer is often restricted to laboratories or observatories.

In contrast, the aneroid barometer, sometimes called a “rubber” or capsule gauge, uses no liquid at all. Instead, it contains a small metallic chamber with flexible walls. When external air pressure increases, the chamber is compressed; when the pressure decreases, it expands slightly. This delicate movement is transmitted to a pointer on a dial. In this way, atmospheric pressure is converted into mechanical displacement, much like a spring resists stretching by its own elasticity.

These instruments are more than technical curiosities. They provide vital information for meteorology, where falling pressure can signal an approaching storm. They serve as altimeters for pilots and mountaineers, who rely on pressure differences to estimate height above sea level. Even in everyday life, the barometer embodies a deeper truth: what seems intangible can be observed, recorded, and interpreted through careful design. The act of measuring the atmosphere itself reminds us that science often begins with turning the invisible into the visible.""",
        "reason": "科学的英文を読解し要点を説明できるようにする。試験の英語対策。"
    }
]

@app.get("/")
def read_root():
    return {"message": "Hello, World!"}

class ChatRequest(BaseModel):
    question: str

class ChatResponse(BaseModel):
    answer: str

class Task(BaseModel):
    id: int
    title: str
    deadline: datetime.datetime
    importance: int
    urgency: int
    status: str
    method: str
    reason: str

# ===== 共通ロジックを関数化 =====
async def run_engine() -> Optional[int]:
    global focused_task_id

    # datetime を文字列に変換してから渡す
    safe_tasks = []
    for t in mock_tasks:
        safe_t = {**t}
        if isinstance(safe_t["deadline"], datetime.datetime):
            safe_t["deadline"] = safe_t["deadline"].isoformat()
        safe_tasks.append(safe_t)

    prompt = """
    以下はユーザーとのチャット履歴とタスク一覧です。
    会話からユーザーが今一番フォーカスすべきタスクを1つ選び、
    JSON形式で { "focused_task_id": <id> } の形で答えてください。
    優先順位としては、
    直近のユーザー発話との意図一致度を最優先にするため、ユーザのチャット履歴に含まれる
    発話と関係の最もありそうなタスクを選んでください。
    ただし、ユーザの最新の発言に最も関係のあるものを選んでください。そのために過去の話を無視しても良いです
    分割されているタスクについては、フォーカスしているものが終わったと判断できる場合に、次のタスクにフォーカスしてください。
    """

    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": f"Chat history: {chat_history}\nTasks: {safe_tasks}"}
    ]

    print("==== AIに投げるmessages ====")
    for m in messages:
        print(m)
    print("================================")

    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "focused_task_schema",
                "schema": {
                    "type": "object",
                    "properties": {
                        "focused_task_id": {"type": "integer"}
                    },
                    "required": ["focused_task_id"],
                    "additionalProperties": False
                }
            }
        }
    )

    result = resp.choices[0].message
    print("==== AIからのレスポンス ====")
    print(result)

    # content を JSON として扱う
    data = json.loads(result.content)
    focused_task_id = data.get("focused_task_id")

    return focused_task_id

@app.post("/engine")
async def engine():
    fid = await run_engine()
    return {"focused_task_id": fid}

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    global focused_task_id

    # ユーザーのメッセージを履歴に追加
    chat_history.append({
        "role": "user", 
        "content": request.question
    })

    await run_engine()

    task_context = ""

    if focused_task_id is not None:
        task = next((t for t in mock_tasks if t["id"] == focused_task_id), None)
        if task:
            # datetime を文字列に変換
            deadline = (
                task["deadline"].isoformat()
                if isinstance(task["deadline"], datetime.datetime)
                else str(task["deadline"])
            )
            task_context = (
                f"現在フォーカスしているタスクは『{task['title']}』です。\n"
                f"- 締切: {deadline}\n"
                f"- 方法: {task['method']}\n"
                f"- 理由: {task['reason']}\n"
            )
    
    messages = []
    if task_context:
        messages.append({
            "role": "system",
            "content": f"ユーザと自然に会話してください。以下のタスク情報は、やらなければならないこととして、マネジメントするような形で必ず考慮に入れて回答してください。特に方法について、ユーザと会話しながらふかぼって実行を助けるようにすると良いかもしれません:\n{task_context}\nただし、一回伝えたことを再度伝えることは、それがマネジメント的に必要でない限り避けてください。最後は、次やらなければならないことを能動的に提示してください"
        })
    messages.extend(chat_history)

    print("==== AIに投げるmessages ====")
    for m in messages:
        print(m)
    print("================================")

    # 履歴を含めてAIに送信
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
    )

    answer = resp.choices[0].message.content
    
    # AIの回答を履歴に追加
    chat_history.append({
        "role": "assistant", 
        "content": answer
    })
    
    return {"answer": answer}

# チャット履歴を取得するエンドポイント
@app.get("/chat/history")
async def get_chat_history():
    return chat_history

# チャット履歴をクリアするエンドポイント
@app.delete("/chat/history")
async def clear_chat_history():
    global chat_history
    chat_history = []
    return {"message": "Chat history cleared"}

# タスク一覧を取得するエンドポイント
@app.get("/tasks")
async def get_tasks():
    return {"tasks": mock_tasks}

# 特定のタスクを取得するエンドポイント
@app.get("/tasks/{task_id}")
async def get_task(task_id: int):
    task = next((task for task in mock_tasks if task["id"] == task_id), None)
    if task is None:
        return {"error": "Task not found"}
    return {"task": task}

# タスクのステータスを更新するエンドポイント
@app.put("/tasks/{task_id}/status")
async def update_task_status(task_id: int, status: str):
    task = next((task for task in mock_tasks if task["id"] == task_id), None)
    if task is None:
        return {"error": "Task not found"}
    
    task["status"] = status
    return {"task": task}

# 新しいタスクを作成するエンドポイント
@app.post("/tasks")
async def create_task(task: Task):
    new_task = task.dict()
    new_task["id"] = max([t["id"] for t in mock_tasks]) + 1
    mock_tasks.append(new_task)
    return {"task": new_task}


@app.get("/notes")
async def get_notes():
    data = supabase.table("notes").select("*").execute()
    return data.data

