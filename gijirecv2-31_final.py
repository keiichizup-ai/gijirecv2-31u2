import streamlit as st
import openai
import tempfile
import os  # os モジュールをインポート
from pydub import AudioSegment
from googletrans import Translator
from langdetect import detect
from dotenv import load_dotenv

# APIキーの設定
load_dotenv()  # .env ファイルを読み込む
openai.api_key = os.environ.get('OPENAI_API_KEY')

def transcribe_audio(file, format):
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
        if format == "mp3":
            sound = AudioSegment.from_mp3(file)
            sound.export(temp_file.name, format="wav")
        else:
            temp_file.write(file.getvalue())
        temp_file_path = temp_file.name

    with open(temp_file_path, "rb") as audio_file:
        transcript = openai.Audio.transcribe(
            model="whisper-1",
            file=audio_file
        )
    return transcript['text']

def summarize_text(text, description):
    max_lines = 1 if description == "エグゼクティブサマリ" else 3 if description == "3行サマリ" else 10 if description == "長めのサマリ" else 1
    prompt_text = f"以下の文章を箇条書きで{description}として要約してください。" if detect(text) == 'ja' else f"Please summarize the following text in bullet points as a {description}:"
    summary = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": prompt_text},
            {"role": "user", "content": text}
        ],
        max_tokens=150 * max_lines,
        temperature=0.7
    )
    return summary['choices'][0]['message']['content']

def translate_text(text):
    translator = Translator()
    dest_language = 'ja' if detect(text) == 'en' else 'en'
    translation = translator.translate(text, dest=dest_language)
    return translation.text

def punctuate_and_paragraph(text):
    prompt = f"""以下の文章に句読点と段落を追加して、読みやすく整形してください。

    {text}
    """
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": prompt},
        ],
        max_tokens=2000,  # 必要に応じて調整
        temperature=0.5
    )
    return response['choices'][0]['message']['content']

def main():
    st.title('議事Rec Ver.2.31')
    uploaded_file = st.file_uploader("音声ファイルをアップロードしてください (.wav, .mp3)", type=["wav", "mp3"])

    if uploaded_file is not None:
        full_transcription = st.checkbox('全文文字起こし')
        executive_summary = st.checkbox('エグゼクティブサマリ')
        three_line_summary = st.checkbox('3行サマリ')
        extended_summary = st.checkbox('長めのサマリ')

        if st.button('実行'):
            with st.spinner('音声をテキストに変換中...'):
                transcript = transcribe_audio(uploaded_file, uploaded_file.type.split('/')[1])
                st.session_state.original_text = transcript
                st.session_state.translated_text = translate_text(transcript)
                display_text = ""

                if full_transcription:
                  punctuated_transcript = punctuate_and_paragraph(transcript)  # ここで整形
                  display_text += "**Full Transcription:**\n" + punctuated_transcript + "\n\n"  # 整形結果を使用

                if executive_summary:
                    summary_text = summarize_text(transcript, "Executive Summary")
                    st.session_state.summary_text = summary_text
                    display_text += "**Executive Summary:**\n" + summary_text + "\n\n"

                if three_line_summary:
                    summary_text = summarize_text(transcript, "Three Line Summary")
                    st.session_state.summary_text = summary_text
                    display_text += "**Three Line Summary:**\n" + summary_text + "\n\n"

                if extended_summary:
                    summary_text = summarize_text(transcript, "Extended Summary")
                    st.session_state.summary_text = summary_text
                    display_text += "**Extended Summary:**\n" + summary_text + "\n\n"

                st.markdown(display_text)

        if st.button('日本語/English'):
            if 'original_text' in st.session_state:
                st.session_state.translated_text = translate_text(st.session_state.original_text)
                st.markdown("**Translated Full Text:**\n" + st.session_state.translated_text)
            if 'summary_text' in st.session_state:
                translated_summary = translate_text(st.session_state.summary_text)
                st.markdown("**Translated Summary:**\n" + translated_summary)

if __name__ == "__main__":
    main()

