import streamlit as st
import openai
import tempfile
import os
from pydub import AudioSegment
from deep_translator import GoogleTranslator  # googletrans を deep_translator に変更
from langdetect import detect, detect_langs  # detect_langs をインポート
from dotenv import load_dotenv
import PyPDF2
from docx import Document
import requests
from bs4 import BeautifulSoup
import time  # time モジュールを追加
import json  # json モジュールをインポート

# APIキーの設定
load_dotenv()
openai.api_key = os.getenv('OPENAI_API_KEY')

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

    while True:  # リトライ処理を追加
        try:
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
        except openai.error.RateLimitError:
            st.warning("APIのレート制限を超えました。10秒待機してから再試行します。")
            time.sleep(10)

def summarize_document(text, description, max_chunk_size=4000):  # 文書分割関数
    summaries = []
    chunks = [text[i:i+max_chunk_size] for i in range(0, len(text), max_chunk_size)]
    for chunk in chunks:
        summary = summarize_text(chunk, description)
        summaries.append(summary)
    return "\n\n".join(summaries)

def translate_text(text):
    if not text:
        return text

    translator = GoogleTranslator(source='auto', target='ja' if detect(text) == 'en' else 'en')

    try:
        if text.startswith('-'):  # 箇条書きの場合
            lines = text.splitlines()
            translated_lines = []
            for line in lines:
                # 箇条書きのハイフンを維持したまま翻訳
                translated_line = translator.translate(line)
                translated_lines.append(translated_line)
            return '\n'.join(translated_lines)
        else:
            return translator.translate(text)
    except Exception as e:  # 例外をキャッチ
        st.error(f"翻訳中にエラーが発生しました。エラー詳細: {e}")
        return "Translation Failed"

def punctuate_and_paragraph(text):
    prompt = f"""以下の文章に句読点と段落を追加して、読みやすく整形してください。

    {text}
    """
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": prompt},
        ],
        max_tokens=2000,
        temperature=0.5
    )
    return response['choices'][0]['message']['content']

# テキスト抽出関数
def extract_text_from_pdf(file):
    pdf_reader = PyPDF2.PdfReader(file)
    text = ""
    for page in pdf_reader.pages:
        text += page.extract_text()
    return text

def extract_text_from_docx(file):
    doc = Document(file)
    text = ""
    for para in doc.paragraphs:
        text += para.text + "\n"
    return text

def extract_text_from_url(url):
    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'html.parser')

    # 不要なタグを削除 (例: script, style)
    for script in soup(["script", "style"]):
        script.extract()

    text = soup.get_text(separator=' ', strip=True)

    # 言語判定を Content-Language から行う
    content_language = response.headers.get('Content-Language', None)  # デフォルトを None に変更
    language = content_language.split('-')[0] if content_language else None

    return text, language

def summarize_text(text, description, language=None):
    max_lines = 1 if description == "エグゼクティブサマリ" else 3 if description == "3行サマリ" else 10 if description == "長めのサマリ" else 1

    if language is None:
        langs = detect_langs(text)
        if langs:
            language = langs[0].lang
        else:
            language = 'ja'

    prompt_text = f"以下の文章を箇条書きで{description}として要約してください。" if language == 'ja' else f"Please summarize the following text in bullet points as a {description}:"

    while True:
        try:
            summary = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": prompt_text},
                    {"role": "user", "content": text}
                ],
                max_tokens=150 * max_lines,
                temperature=0.7
            )
            summary_text = summary['choices'][0]['message']['content']
            if summary_text is None:  # summary_text が None の場合の処理を追加
                raise ValueError("Summary text is None")
            return summary_text
        except (openai.error.RateLimitError, ValueError) as e:  # ValueError の例外処理を追加
            if isinstance(e, openai.error.RateLimitError):
                st.warning("APIのレート制限を超えました。10秒待機してから再試行します。")
                time.sleep(10)
            else:
                st.error(f"要約中にエラーが発生しました。エラー詳細: {e}")
                return ""  # エラー時は空文字列を返す

def main():
    st.title('議事録作成アプリ Ver.2.5')

    # タブの作成
    tab1, tab2, tab3 = st.tabs(["音声ファイル", "文書ファイル", "Webサイト"])

    # full_transcription を st.form の外で定義
    full_transcription = False

    with tab1:  # 音声ファイルタブ
        st.subheader("音声ファイルからの文字起こし")
        uploaded_file = st.file_uploader("音声ファイルをアップロードしてください (.wav, .mp3)", type=["wav", "mp3"])

        if uploaded_file is not None:  # ファイルがアップロードされた場合のみチェックボックスを表示
            full_transcription = st.checkbox('全文文字起こし', key="audio_full_transcription")
            executive_summary = st.checkbox('エグゼクティブサマリ', key="audio_executive_summary")
            three_line_summary = st.checkbox('3行サマリ', key="audio_three_line_summary")
            extended_summary = st.checkbox('長めのサマリ', key="audio_extended_summary")

            if st.button('実行', key="audio_submit"):
                with st.spinner('音声をテキストに変換中...'):
                    transcript = transcribe_audio(uploaded_file, uploaded_file.type.split('/')[1])
                    text = transcript  # 音声文字起こし結果を text に代入

                    # session_state 変数の初期化
                    st.session_state.original_text = text
                    st.session_state.translated_text = ""
                    st.session_state.summary_text = ""

                    display_text = ""

                    if full_transcription:
                        punctuated_transcript = punctuate_and_paragraph(transcript)
                        display_text += "**Full Transcription:**\n" + punctuated_transcript + "\n\n"

                    if executive_summary:
                        summary_text = summarize_text(transcript, "エグゼクティブサマリ", detect(transcript))
                        st.session_state.summary_text = summary_text
                        display_text += "**Executive Summary:**\n" + summary_text + "\n\n"

                    if three_line_summary:
                        summary_text = summarize_text(transcript, "3行サマリ", detect(transcript))
                        st.session_state.summary_text = summary_text
                        display_text += "**Three Line Summary:**\n" + summary_text + "\n\n"

                    if extended_summary:
                        summary_text = summarize_text(transcript, "長めのサマリ", detect(transcript))
                        st.session_state.summary_text = summary_text
                        display_text += "**Extended Summary:**\n" + summary_text + "\n\n"

                    st.markdown(display_text)

            # インデントを修正
            if st.button('日本語/English', key="audio_translate_button"):
                if 'original_text' in st.session_state:
                    st.session_state.translated_text = translate_text(st.session_state.original_text)
                    if st.session_state.translated_text != "Translation Failed":
                        if full_transcription:  # full_transcription がTrueの場合のみ全文を表示
                            st.markdown("**Translated Full Text:**\n" + st.session_state.translated_text)
                if 'summary_text' in st.session_state:
                    translated_summary = translate_text(st.session_state.summary_text)
                    if translated_summary != "Translation Failed":
                        st.markdown("**Translated Summary:**\n" + translated_summary)

    with tab2:  # 文書ファイルタブ
        st.subheader("文書ファイルからの要約")
        uploaded_file = st.file_uploader("PDFまたはWordファイルをアップロード", type=["pdf", "docx"])

        if uploaded_file is not None:
            file_type = uploaded_file.type.split('/')[1]
            if file_type == "pdf":
                text = extract_text_from_pdf(uploaded_file)
            elif file_type == "docx":
                text = extract_text_from_docx(uploaded_file)
            else:
                st.error("サポートされていないファイル形式です。")
                text = None

            if text is not None:
                # 言語判定
                langs = detect_langs(text)
                if langs:
                    language = langs[0].lang
                else:
                    language = 'ja'  # 判定できない場合は日本語をデフォルトとする

                st.session_state.original_text = text
                st.session_state.translated_text = ""  # 初期化を移動
                st.session_state.summary_text = ""  # 初期化を移動

                executive_summary = st.checkbox('エグゼクティブサマリ', key="doc_executive_summary")
                three_line_summary = st.checkbox('3行サマリ', key="doc_three_line_summary")
                extended_summary = st.checkbox('長めのサマリ', key="doc_extended_summary")

                if st.button('実行', key="doc_submit"):
                    with st.spinner('処理中...'):
                        display_text = ""

                        if executive_summary:
                            summary_text = summarize_document(text, "エグゼクティブサマリ", language)
                            st.session_state.summary_text = summary_text
                            display_text += "**Executive Summary:**\n" + summary_text + "\n\n"

                        if three_line_summary:
                            summary_text = summarize_text(text, "3行サマリ", language)
                            st.session_state.summary_text = summary_text
                            display_text += "**Three Line Summary:**\n" + summary_text + "\n\n"

                        if extended_summary:
                            summary_text = summarize_text(text, "長めのサマリ", language)
                            st.session_state.summary_text = summary_text
                            display_text += "**Extended Summary:**\n" + summary_text + "\n\n"

                        st.markdown(display_text)

                # インデントを修正
                if st.button('日本語/English', key="doc_translate_button"):
                    if 'original_text' in st.session_state:
                        st.session_state.translated_text = translate_text(st.session_state.original_text)
                        if st.session_state.translated_text != "Translation Failed":
                            st.markdown("**Translated Text:**\n" + st.session_state.translated_text)
                    if 'summary_text' in st.session_state:
                        translated_summary = translate_text(st.session_state.summary_text)
                        if translated_summary != "Translation Failed":
                            st.markdown("**Translated Summary:**\n" + translated_summary)

    with tab3:  # Webサイトタブ
        st.subheader("Webサイトからの要約")

        with st.form(key='web_form'):
            url = st.text_input("WebサイトのURLを入力")

            # チェックボックスはフォーム内で定義
            executive_summary = st.checkbox('エグゼクティブサマリ', key="web_executive_summary")
            three_line_summary = st.checkbox('3行サマリ', key="web_three_line_summary")
            extended_summary = st.checkbox('長めのサマリ', key="web_extended_summary")

            submitted = st.form_submit_button('Webサイト処理実行')

            if submitted and url:
                text, language = extract_text_from_url(url)
                if text is not None:
                    with st.spinner('処理中...'):
                        st.session_state.original_text = text
                        st.session_state.translated_text = translate_text(text)
                        display_text = ""

                    if executive_summary:
                        summary_text = summarize_document(text, "エグゼクティブサマリ", language)
                        st.session_state.summary_text = summary_text
                        display_text += "**Executive Summary:**\n" + summary_text + "\n\n"

                    if three_line_summary:
                        summary_text = summarize_text(text, "3行サマリ", language)
                        st.session_state.summary_text = summary_text
                        display_text += "**Three Line Summary:**\n" + summary_text + "\n\n"

                    if extended_summary:
                        summary_text = summarize_text(text, "長めのサマリ", language)
                        st.session_state.summary_text = summary_text
                        display_text += "**Extended Summary:**\n" + summary_text + "\n\n"

                        st.markdown(display_text)

                # 以下をインデント
                if st.button('日本語/English', key="web_translate_button"):
                    if 'original_text' in st.session_state:
                        st.session_state.translated_text = translate_text(st.session_state.original_text)
                        if st.session_state.translated_text != "Translation Failed":
                            st.markdown("**Translated Full Text:**\n" + st.session_state.translated_text)
                    if 'summary_text' in st.session_state:
                        translated_summary = translate_text(st.session_state.summary_text)
                        if translated_summary != "Translation Failed":
                            st.markdown("**Translated Summary:**\n" + translated_summary)

if __name__ == "__main__":
    main()





