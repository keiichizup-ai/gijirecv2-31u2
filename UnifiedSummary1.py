import streamlit as st
import openai
import tempfile
import os
from pydub import AudioSegment
from googletrans import Translator
from langdetect import detect
from dotenv import load_dotenv
import re
from PyPDF2 import PdfReader
from docx import Document
from langchain.text_splitter import CharacterTextSplitter
from streamlit_player import st_player
from youtube_transcript_api import YouTubeTranscriptApi

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

def summarize_text(text, max_tokens=800):
    text_splitter = CharacterTextSplitter(        
        separator = "\n",
        chunk_size = 3000,
        chunk_overlap  = 200,
        length_function = len,
    )
    texts = text_splitter.split_text(text)
    prompt_text = f"以下の文章を5行以内で要約してください。" if detect(text) == 'ja' else f"Please summarize the following text in 5 lines or less:"
    if max_tokens == 450:
        prompt_text = f"以下の文章を3つの箇条書きで要約してください。" if detect(text) == 'ja' else f"Please summarize the following text in 3 bullet points:"
    
    summaries = []
    for text in texts:
        summary = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": prompt_text},
                {"role": "user", "content": text}
            ],
            max_tokens=max_tokens,
            temperature=0.7
        )
        summaries.append(summary['choices'][0]['message']['content'])

    return "\n\n".join(summaries)

def translate_text(text, is_summary=False):
    translator = Translator()
    dest_language = 'ja' if detect(text) == 'en' else 'en'
    translation = translator.translate(text, dest=dest_language)

    # 3行サマリの場合、箇条書きの形式を変換
    if is_summary:
        if dest_language == 'en':
            # 英語への翻訳時は、日本語の箇条書き記号（- 、・）と全角スペースを「- 」に、読点「、」を「,」に変換
            translation.text = translation.text.replace('・', '-').replace('、', ',')
            # 不要なハイフンを削除
            translation.text = re.sub(r'-{2,}', '-', translation.text)
            translation.text = translation.text.replace('- ', '- ')
        else:
            # 日本語への翻訳時は、英語の箇条書き記号（-）とスペースを「・」に、コンマ「,」を「、」に変換
            translation.text = translation.text.replace('- ', '・').replace(',', '、')
        # 翻訳後のテキストから行頭の不要なハイフンを削除
        translation.text = re.sub(r'^- ', '', translation.text, flags=re.MULTILINE)

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
        max_tokens=2000,
        temperature=0.5
    )
    return response['choices'][0]['message']['content']

def extract_text_from_file(file):
    if file.type == "application/pdf":
        pdf_reader = PdfReader(file)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text()
    elif file.type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        doc = Document(file)
        text = ""
        for para in doc.paragraphs:
            text += para.text
    else:
        raise ValueError("Unsupported file type")
    return text

def summarize_youtube_video(url):
    # 動画IDを抽出
    video_id = re.findall(r"v=(\w+)", url)  # v=の後の文字列を抽出
    if not video_id:
        st.error("無効なYouTube動画URLです。")
        return None
    video_id = video_id[0]  # 最初の動画IDを使用

    try:
        # 字幕の取得 (video_id を使用)
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        transcript = transcript_list.find_generated_transcript(['en', 'ja'])
        text = ' '.join([t['text'] for t in transcript.fetch()])
        return summarize_text(text)
    except Exception as e:
        st.error(f"Error processing YouTube video: {e}")
        return None

def main():
    st.title('ユニファイドサマリー Ver.1')

    tab1, tab2, tab3 = st.tabs(["音声ファイル", "PDF/Wordファイル", "YouTube動画"])

    with tab1:
        uploaded_file = st.file_uploader("音声ファイルをアップロードしてください (.wav, .mp3)", type=["wav", "mp3"])

        if uploaded_file is not None:
            full_transcription = st.checkbox('全文文字起こし')
            executive_summary = st.checkbox('エグゼクティブサマリ')
            three_line_summary = st.checkbox('3行サマリ')
            extended_summary = st.checkbox('長めのサマリ')

            if st.button('実行', key="execute_audio_button"):
                with st.spinner('音声をテキストに変換中...'):
                    transcript = transcribe_audio(uploaded_file, uploaded_file.type.split('/')[1])
                    st.session_state.original_text = transcript
                    st.session_state.translated_text = translate_text(transcript)
                    display_text = ""

                    if full_transcription:
                        punctuated_transcript = punctuate_and_paragraph(transcript)
                        display_text += "**Full Transcription:**\n" + punctuated_transcript + "\n\n"

                    if executive_summary:
                        summary_text = summarize_text(transcript, 150)  # max_tokensを150に設定
                        st.session_state.summary_text = summary_text
                        display_text += "**エグゼクティブサマリ:**\n" + summary_text + "\n\n"

                    if three_line_summary:
                        summary_text = summarize_text(transcript, 450)  # max_tokensを450に設定
                        st.session_state.summary_text = summary_text
                        # 2行目以降の行頭の不要な文字を削除
                        summary_text = re.sub(r'^\s*[-・⚪︎●■]\s*', '- ', summary_text, flags=re.MULTILINE)
                        display_text += "**3行サマリ:**\n" + summary_text + "\n\n"

                    if extended_summary:
                        summary_text = summarize_text(transcript, 1500)  # max_tokensを1500に設定
                        st.session_state.summary_text = summary_text
                        display_text += "**長めのサマリ:**\n" + summary_text + "\n\n"

                    st.markdown(display_text)

        if st.button('日本語/English', key="translate_audio_button"):  # key引数を追加
            if 'original_text' in st.session_state:
                st.session_state.translated_text = translate_text(st.session_state.original_text)
                st.markdown("**Translated Full Text:**\n" + st.session_state.translated_text)
            if 'summary_text' in st.session_state:
                translated_summary = translate_text(st.session_state.summary_text, is_summary=True)
                st.markdown("**Translated Summary:**\n" + translated_summary)

    with tab2:
        uploaded_file = st.file_uploader("PDF/Wordファイルをアップロードしてください (.pdf, .docx)", type=["pdf", "docx"])

        if uploaded_file is not None:
            if st.button('実行'):
                with st.spinner('ファイルを読み込み中...'):
                    text = extract_text_from_file(uploaded_file)
                    summary_text = summarize_text(text)
                    st.session_state['pdf_word_summary'] = summary_text  # サマリの原文をセッションステートに保存
                    st.markdown("**サマリ:**\n" + summary_text)

        if st.button('日本語/English', key="translate_pdf_word_button"):  # key引数を追加
            if 'pdf_word_summary' in st.session_state:
                translated_summary = translate_text(st.session_state['pdf_word_summary'])
                st.markdown("**Translated Summary:**\n" + translated_summary)

    with tab3:
        url = st.text_input("YouTube動画のURLを入力してください")
        if url:
            if st.button('実行', key="execute_youtube_button"):
                with st.spinner('動画を処理中...'):
                    summary = summarize_youtube_video(url)
                    if summary:
                        st.session_state['youtube_summary'] = summary
                        st.session_state['show_youtube_summary'] = True  # サマリ表示状態をTrueに
                        st.session_state['show_youtube_player'] = True  # プレイヤー表示状態をTrueに

        # サマリと動画プレイヤーの表示
        if st.session_state.get('show_youtube_summary'):
            st.markdown("**サマリ:**\n" + st.session_state['youtube_summary'])
        if st.session_state.get('show_youtube_player'):
            st_player(url)

        # 日本語/English ボタン
        if st.button('日本語/English', key="translate_youtube_button"):
            if 'youtube_summary' in st.session_state:
                translated_summary = translate_text(st.session_state['youtube_summary'])
                st.markdown("**Translated Summary:**\n" + translated_summary)

if __name__ == "__main__":
    main()