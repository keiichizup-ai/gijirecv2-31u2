from openai import OpenAI

client = OpenAI()

# ファイルをバイナリ読み込みモードで開く
with open("sample.wav", "rb") as file:
    transcript = client.audio.transcribe(model="whisper-1",
    file=file)

# Whisper APIからのレスポンスを確認
print("Whisper API Response:", transcript)

# トランスクリプトが正しく取得できているか確認
if 'text' in transcript:
    text_to_summarize = transcript.text
else:
    text_to_summarize = "トランスクリプトが利用不可能です"

# ChatGPTで要約する
summary = client.chat.completions.create(model="gpt-4",
messages=[
    {
        "role": "system",
        "content": f"以下の文章を3行の箇条書きで要約してください:\n{text_to_summarize}"
    }
])

# ChatGPT APIからのレスポンスを確認
print("ChatGPT API Response:", summary)

# 正しいキーで結果を表示
if 'choices' in summary and summary.choices:
    print("Summarized Text:", summary.choices[0].message.content)
else:
    print("レスポンスに適切なデータが含まれていません。")
