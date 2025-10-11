import datetime
from typing import List, Dict, Optional

# チャット履歴を保存するリスト
chat_history: List[Dict[str, str]] = []

# フォーカス中のタスクID
focused_task_id: Optional[int] = None

# メッセージIDカウンター
message_id_counter = 0

# モックnotificationデータ
mock_notifications: List[Dict] = [
    {
        "id": 1,
        "title": "米の買い物を済ませましたか？",
        "user_id": "user_123",
        "content": "明日までに米を購入する必要があります。近所のスーパーで魚沼産コシヒカリ5kgを購入しましょう。無洗米があれば便利です。",
        "due_date": "2024-10-05T10:00:00Z",
        "createdAt": "2024-10-04T10:00:00Z",
        "updatedAt": "2024-10-04T10:00:00Z",
        "status": "scheduled",
        "task_id": 1,
        "suggestions": ["今すぐスーパーに行く", "無洗米を確認する", "後で買いに行く"]
    },
    {
        "id": 2,
        "title": "米の買い物 - 今日が締切です",
        "user_id": "user_123",
        "content": "今日中に米を買いに行きましょう。家族の食事に必要不可欠です。スーパーの営業時間を確認して出かけましょう。",
        "due_date": "2024-10-06T08:00:00Z",
        "createdAt": "2024-10-04T10:00:00Z",
        "updatedAt": "2024-10-04T10:00:00Z",
        "status": "scheduled",
        "task_id": 1,
        "suggestions": ["今すぐ買いに行く", "スーパーの営業時間を確認", "完了しました"]
    },
    {
        "id": 3,
        "title": "魚の買い物計画を立てましょう",
        "user_id": "user_123",
        "content": "週末のパーティーに向けて、新鮮な鯛か鮭を遠くのデパートで購入予定。鮮度を優先して選びましょう。",
        "due_date": "2024-10-07T10:00:00Z",
        "createdAt": "2024-10-04T10:00:00Z",
        "updatedAt": "2024-10-04T10:00:00Z",
        "status": "scheduled",
        "task_id": 2,
        "suggestions": ["デパートの営業時間を確認", "魚の種類を決める", "後で計画を立てる"]
    },
    {
        "id": 4,
        "title": "魚の買い物を実行しましょう",
        "user_id": "user_123",
        "content": "明日は魚を買いに行きましょう。週末のパーティーで使うため、新鮮な魚で料理の質を上げたいですね。",
        "due_date": "2024-10-09T10:00:00Z",
        "createdAt": "2024-10-04T10:00:00Z",
        "updatedAt": "2024-10-04T10:00:00Z",
        "status": "scheduled",
        "task_id": 2,
        "suggestions": ["今すぐ魚を買いに行く", "鮮魚売り場を確認", "完了しました"]
    },
    {
        "id": 5,
        "title": "誕生日ケーキの準備をしましたか？",
        "user_id": "user_123",
        "content": "妹の誕生日祝いのため、都心の有名パティスリーでチーズケーキを購入予定。予約が必要か確認しましょう。",
        "due_date": "2024-10-07T10:00:00Z",
        "createdAt": "2024-10-04T10:00:00Z",
        "updatedAt": "2024-10-04T10:00:00Z",
        "status": "scheduled",
        "task_id": 3,
        "suggestions": ["パティスリーに予約を入れる", "チーズケーキの種類を選ぶ", "後で確認する"]
    },
    {
        "id": 6,
        "title": "iPhone選びの準備をしましょう",
        "user_id": "user_123",
        "content": "新しいスマホが必要ですね。Apple公式サイトや家電量販店で最新モデルを比較してみましょう。カメラ性能を重視してProモデルを検討してください。",
        "due_date": "2024-10-12T10:00:00Z",
        "createdAt": "2024-10-04T10:00:00Z",
        "updatedAt": "2024-10-04T10:00:00Z",
        "status": "scheduled",
        "task_id": 4,
        "suggestions": ["Apple公式サイトを確認", "Proモデルを比較", "予算を確認"]
    }
]

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

In contrast, the aneroid barometer, sometimes called a "rubber" or capsule gauge, uses no liquid at all. Instead, it contains a small metallic chamber with flexible walls. When external air pressure increases, the chamber is compressed; when the pressure decreases, it expands slightly. This delicate movement is transmitted to a pointer on a dial. In this way, atmospheric pressure is converted into mechanical displacement, much like a spring resists stretching by its own elasticity.

These instruments are more than technical curiosities. They provide vital information for meteorology, where falling pressure can signal an approaching storm. They serve as altimeters for pilots and mountaineers, who rely on pressure differences to estimate height above sea level. Even in everyday life, the barometer embodies a deeper truth: what seems intangible can be observed, recorded, and interpreted through careful design. The act of measuring the atmosphere itself reminds us that science often begins with turning the invisible into the visible.""",
        "reason": "科学的英文を読解し要点を説明できるようにする。試験の英語対策。"
    }
]

