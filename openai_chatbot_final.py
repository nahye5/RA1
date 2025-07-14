import streamlit as st
import openai
import time
import json
import os
from datetime import datetime
import zipfile
import tempfile
from io import BytesIO

# 페이지 설정
st.set_page_config(
    page_title="문서 기반 AI 챗봇",
    page_icon="📚",
    layout="wide"
)

# API 키 설정 (환경변수 또는 직접 입력)
# 방법 1: 환경변수에서 가져오기
api_key = os.getenv("OPENAI_API_KEY")

# 방법 2: 직접 코드에 입력 (보안상 권장하지 않음)
api_key = "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"  # 이 줄의 주석을 해제하고 실제 API 키를 입력

# 기존 Assistant ID 설정 (선택사항)
EXISTING_ASSISTANT_ID = "asst_nPcXHjfN0G8nFcpWPxo08byE"  # 기존 Assistant 사용 시

# 지원하는 파일 확장자
SUPPORTED_EXTENSIONS = ['md', 'txt', 'pdf', 'docx', 'json', 'csv', 'py', 'js', 'html', 'css']

# 사이드바 설정
with st.sidebar:
    st.title("📚 문서 기반 AI 챗봇")
    
    # API 키 상태 표시
    if api_key and api_key != "여기에_실제_API_키를_입력하세요":
        st.success("✅ API 키가 설정되었습니다")
    else:
        st.error("❌ API 키를 설정해주세요")
        st.markdown("""
        **API 키 설정 방법:**
        1. 환경변수로 설정: `OPENAI_API_KEY=your-key`
        2. 코드 19번째 줄에서 직접 설정
        """)
    
    st.markdown("---")
    
    # 파일 업로드 섹션
    st.subheader("📄 문서 업로드")
    
    # 업로드 방식 선택
    upload_mode = st.radio(
        "업로드 방식 선택",
        ["개별 파일", "다중 파일", "ZIP 파일"],
        help="개별 파일, 여러 파일 동시 업로드, 또는 ZIP 파일 업로드"
    )
    
    uploaded_files = []
    
    if upload_mode == "개별 파일":
        uploaded_file = st.file_uploader(
            "단일 파일 업로드",
            type=SUPPORTED_EXTENSIONS,
            help="지원 형식: " + ", ".join(SUPPORTED_EXTENSIONS)
        )
        if uploaded_file:
            uploaded_files = [uploaded_file]
    
    elif upload_mode == "다중 파일":
        uploaded_files = st.file_uploader(
            "여러 파일 동시 업로드",
            type=SUPPORTED_EXTENSIONS,
            accept_multiple_files=True,
            help="지원 형식: " + ", ".join(SUPPORTED_EXTENSIONS)
        )
    
    elif upload_mode == "ZIP 파일":
        zip_file = st.file_uploader(
            "ZIP 파일 업로드",
            type=['zip'],
            help="ZIP 파일 내의 모든 지원 파일을 추출합니다"
        )
        if zip_file:
            try:
                with zipfile.ZipFile(zip_file, 'r') as zip_ref:
                    extracted_files = []
                    for file_info in zip_ref.filelist:
                        if not file_info.is_dir():
                            file_ext = file_info.filename.split('.')[-1].lower()
                            if file_ext in SUPPORTED_EXTENSIONS:
                                file_content = zip_ref.read(file_info.filename)
                                # BytesIO 객체로 변환하여 uploaded_file과 같은 인터페이스 제공
                                file_obj = BytesIO(file_content)
                                file_obj.name = file_info.filename
                                extracted_files.append(file_obj)
                    uploaded_files = extracted_files
                    if extracted_files:
                        st.success(f"✅ ZIP에서 {len(extracted_files)}개 파일 추출 완료")
                    else:
                        st.warning("⚠️ 지원되는 파일이 ZIP에 없습니다")
            except Exception as e:
                st.error(f"ZIP 파일 처리 실패: {e}")
    
    # 업로드된 파일 목록 표시
    if uploaded_files:
        st.subheader("📋 업로드된 파일")
        for i, file in enumerate(uploaded_files):
            file_name = getattr(file, 'name', f'파일_{i+1}')
            st.text(f"📄 {file_name}")
        
        st.info(f"총 {len(uploaded_files)}개 파일이 업로드되었습니다")
    
    st.markdown("---")
    
    # Assistant 모드 선택
    st.subheader("🤖 Assistant 모드")
    assistant_mode = st.radio(
        "Assistant 모드 선택",
        ["기존 Assistant 사용", "새 Assistant 생성"],
        help="기존 Assistant를 사용하거나 새로 생성할 수 있습니다"
    )
    
    if assistant_mode == "기존 Assistant 사용":
        st.info(f"🔗 기존 Assistant ID: `{EXISTING_ASSISTANT_ID}`")
        st.markdown(f"[Dashboard에서 확인](https://platform.openai.com/assistants/{EXISTING_ASSISTANT_ID})")
    else:
        # Assistant 설정 (새 생성 시에만)
        st.subheader("🤖 새 Assistant 설정")
        assistant_name = st.text_input("Assistant 이름", value="문서 전문가")
        
        # 모델 선택
        model_choice = st.selectbox(
            "모델 선택",
            ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"]
        )
    
    # 새 대화 시작
    if st.button("새 대화 시작"):
        # 새 Assistant 생성 모드에서만 기존 assistant 삭제
        if (assistant_mode == "새 Assistant 생성" and 
            hasattr(st.session_state, 'assistant_id') and 
            st.session_state.assistant_id and 
            st.session_state.assistant_id != EXISTING_ASSISTANT_ID):
            try:
                client = openai.OpenAI(api_key=api_key)
                client.beta.assistants.delete(st.session_state.assistant_id)
            except:
                pass
        
        # 세션 상태 초기화
        for key in list(st.session_state.keys()):
            if key not in ['uploaded_files_content']:
                del st.session_state[key]
        st.rerun()

# 메인 페이지
st.title("📚 문서 기반 AI 챗봇")
st.markdown("업로드된 문서들을 기반으로만 답변하는 AI 챗봇입니다.")

# API 키 확인
if not api_key or api_key == "여기에_실제_API_키를_입력하세요":
    st.error("❌ OpenAI API 키가 설정되지 않았습니다.")
    st.markdown("""
    **API 키 설정 방법:**
    
    **방법 1: 환경변수 사용 (권장)**
    ```bash
    export OPENAI_API_KEY="your-api-key-here"
    streamlit run openai_chatbot.py
    ```
    
    **방법 2: 코드에서 직접 설정**
    ```python
    # 코드 19번째 줄에서 설정
    api_key = "your-api-key-here"
    ```
    """)
    st.stop()

# OpenAI 클라이언트 초기화
try:
    client = openai.OpenAI(api_key=api_key)
except Exception as e:
    st.error(f"OpenAI 클라이언트 초기화 실패: {e}")
    st.stop()

# 파일 업로드 확인
if not uploaded_files:
    st.warning("⚠️ 사이드바에서 문서를 업로드해주세요.")
    st.info("📝 업로드된 문서만을 기반으로 답변합니다.")
    st.stop()

# 세션 상태 초기화
if "messages" not in st.session_state:
    st.session_state.messages = []
if "assistant_id" not in st.session_state:
    st.session_state.assistant_id = None
if "thread_id" not in st.session_state:
    st.session_state.thread_id = None
if "file_ids" not in st.session_state:
    st.session_state.file_ids = []

# 다중 파일 업로드 및 Assistant 설정
def setup_assistant():
    # 기존 Assistant 사용 모드
    if assistant_mode == "기존 Assistant 사용":
        try:
            # 기존 Assistant 정보 확인
            with st.spinner("기존 Assistant 정보를 확인하는 중..."):
                assistant = client.beta.assistants.retrieve(EXISTING_ASSISTANT_ID)
                st.session_state.assistant_id = EXISTING_ASSISTANT_ID
                st.success(f"✅ 기존 Assistant '{assistant.name}' 연결 완료!")
                
                # 파일들이 업로드된 경우 새 vector store 생성
                if uploaded_files:
                    return upload_files_to_existing_assistant()
                else:
                    return True
                    
        except Exception as e:
            st.error(f"기존 Assistant 연결 실패: {e}")
            return False
    
    # 새 Assistant 생성 모드
    else:
        return upload_files_and_create_assistant()

def upload_files_to_existing_assistant():
    """기존 Assistant에 다중 파일 업로드"""
    try:
        uploaded_file_ids = []
        
        # 각 파일을 OpenAI에 업로드
        with st.spinner(f"파일들을 업로드하는 중... (0/{len(uploaded_files)})"):
            for i, file in enumerate(uploaded_files):
                # 파일 내용 읽기
                file_content = file.read()
                file_name = getattr(file, 'name', f'파일_{i+1}')
                
                # 진행률 업데이트
                st.spinner(f"파일들을 업로드하는 중... ({i+1}/{len(uploaded_files)}) - {file_name}")
                
                # OpenAI에 파일 업로드
                uploaded_openai_file = client.files.create(
                    file=(file_name, file_content),
                    purpose='assistants'
                )
                uploaded_file_ids.append(uploaded_openai_file.id)
        
        st.session_state.file_ids = uploaded_file_ids
        
        # 기존 Assistant 업데이트 (새 파일들 추가)
        with st.spinner("Assistant에 파일들을 추가하는 중..."):
            client.beta.assistants.update(
                assistant_id=EXISTING_ASSISTANT_ID,
                tool_resources={
                    "file_search": {
                        "vector_stores": [
                            {
                                "file_ids": uploaded_file_ids
                            }
                        ]
                    }
                }
            )
        
        st.success(f"✅ 기존 Assistant에 {len(uploaded_files)}개 파일 추가 완료!")
        return True
        
    except Exception as e:
        st.error(f"파일 업로드 실패: {e}")
        return False

def upload_files_and_create_assistant():
    """다중 파일 업로드 및 새 Assistant 생성"""
    try:
        uploaded_file_ids = []
        
        # 각 파일을 OpenAI에 업로드
        with st.spinner(f"파일들을 업로드하는 중... (0/{len(uploaded_files)})"):
            for i, file in enumerate(uploaded_files):
                # 파일 내용 읽기
                file_content = file.read()
                file_name = getattr(file, 'name', f'파일_{i+1}')
                
                # 진행률 업데이트
                st.spinner(f"파일들을 업로드하는 중... ({i+1}/{len(uploaded_files)}) - {file_name}")
                
                # OpenAI에 파일 업로드
                uploaded_openai_file = client.files.create(
                    file=(file_name, file_content),
                    purpose='assistants'
                )
                uploaded_file_ids.append(uploaded_openai_file.id)
        
        st.session_state.file_ids = uploaded_file_ids
        
        # 파일 목록 생성
        file_list = [getattr(file, 'name', f'파일_{i+1}') for i, file in enumerate(uploaded_files)]
        
        # Assistant 생성 시 사용할 지시사항
        instructions = f"""
        당신은 업로드된 문서들의 전문가입니다. 다음 규칙을 엄격히 따라주세요:

        1. 오직 업로드된 문서들의 내용만을 기반으로 답변하세요.
        2. 문서에 없는 내용에 대해서는 "해당 내용은 업로드된 문서들에서 찾을 수 없습니다"라고 답변하세요.
        3. 문서의 내용을 정확히 인용하고, 가능하면 해당 파일명과 섹션을 명시하세요.
        4. 문서 외의 일반적인 지식을 사용하지 마세요.
        5. 답변할 때는 문서에서 관련된 부분을 먼저 찾아 확인한 후 답변하세요.
        6. 불확실한 경우 문서를 다시 확인하세요.
        7. 여러 문서에서 관련 정보를 찾은 경우, 각 문서의 정보를 종합하여 답변하세요.
        
        업로드된 문서 파일들: {', '.join(file_list)}
        총 {len(uploaded_files)}개의 문서가 업로드되었습니다.
        """
        
        # Assistant 생성
        with st.spinner("Assistant를 생성하는 중..."):
            assistant = client.beta.assistants.create(
                name=assistant_name,
                instructions=instructions,
                model=model_choice,
                tools=[{"type": "file_search"}],
                tool_resources={
                    "file_search": {
                        "vector_stores": [
                            {
                                "file_ids": uploaded_file_ids
                            }
                        ]
                    }
                }
            )
            st.session_state.assistant_id = assistant.id
        
        st.success(f"✅ {len(uploaded_files)}개 파일 업로드 및 Assistant 생성 완료!")
        
    except Exception as e:
        st.error(f"파일 업로드 또는 Assistant 생성 실패: {e}")
        return False
    
    return True

# Thread 생성
def create_thread():
    try:
        thread = client.beta.threads.create()
        st.session_state.thread_id = thread.id
        return True
    except Exception as e:
        st.error(f"Thread 생성 실패: {e}")
        return False

# 메시지 전송 및 응답 받기
def send_message(message):
    try:
        # 메시지 추가
        client.beta.threads.messages.create(
            thread_id=st.session_state.thread_id,
            role="user",
            content=message
        )
        
        # Run 생성
        run = client.beta.threads.runs.create(
            thread_id=st.session_state.thread_id,
            assistant_id=st.session_state.assistant_id
        )
        
        # Run 완료 대기
        with st.spinner("문서들을 검색하고 답변을 생성하는 중..."):
            while True:
                run_status = client.beta.threads.runs.retrieve(
                    thread_id=st.session_state.thread_id,
                    run_id=run.id
                )
                
                if run_status.status == "completed":
                    break
                elif run_status.status == "failed":
                    st.error("답변 생성에 실패했습니다.")
                    return None
                elif run_status.status == "requires_action":
                    st.error("추가 작업이 필요합니다.")
                    return None
                
                time.sleep(1)
        
        # 응답 메시지 가져오기
        messages = client.beta.threads.messages.list(thread_id=st.session_state.thread_id)
        latest_message = messages.data[0]
        
        if latest_message.role == "assistant":
            return latest_message.content[0].text.value
        
    except Exception as e:
        st.error(f"메시지 전송 실패: {e}")
        return None

# Assistant 및 Thread 초기화
if st.session_state.assistant_id is None:
    if not setup_assistant():
        st.stop()
else:
    # 파일들이 새로 업로드된 경우 파일 추가
    if uploaded_files and not st.session_state.file_ids:
        if assistant_mode == "기존 Assistant 사용":
            if not upload_files_to_existing_assistant():
                st.stop()
        else:
            if not upload_files_and_create_assistant():
                st.stop()

if st.session_state.thread_id is None:
    if not create_thread():
        st.stop()

# 파일 정보 표시
if st.session_state.assistant_id == EXISTING_ASSISTANT_ID:
    st.info(f"🔗 **기존 Assistant 사용 중**: `{EXISTING_ASSISTANT_ID}`")
    if uploaded_files:
        st.info(f"📄 **추가된 문서 수**: {len(uploaded_files)}개")
else:
    if st.session_state.file_ids:
        st.info(f"📄 **현재 사용 중인 문서 수**: {len(uploaded_files)}개")
        
        # 업로드된 파일 목록 표시
        with st.expander("📋 업로드된 파일 목록"):
            for i, file in enumerate(uploaded_files):
                file_name = getattr(file, 'name', f'파일_{i+1}')
                st.text(f"📄 {file_name}")
    
# Assistant 정보 표시 링크
if st.session_state.assistant_id:
    st.markdown(f"[📊 Dashboard에서 Assistant 확인](https://platform.openai.com/assistants/{st.session_state.assistant_id})")

# 채팅 히스토리 표시
chat_container = st.container()

with chat_container:
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if "timestamp" in message:
                st.caption(f"🕐 {message['timestamp']}")

# 사용자 입력
if prompt := st.chat_input("문서들에 대해 질문해보세요..."):
    # 사용자 메시지 추가
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    st.session_state.messages.append({
        "role": "user", 
        "content": prompt,
        "timestamp": timestamp
    })
    
    # 사용자 메시지 표시
    with st.chat_message("user"):
        st.markdown(prompt)
        st.caption(f"🕐 {timestamp}")
    
    # Assistant 응답 받기
    response = send_message(prompt)
    
    if response:
        # Assistant 응답 추가
        response_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        st.session_state.messages.append({
            "role": "assistant", 
            "content": response,
            "timestamp": response_timestamp
        })
        
        # Assistant 응답 표시
        with st.chat_message("assistant"):
            st.markdown(response)
            st.caption(f"🕐 {response_timestamp}")

# 하단 정보
st.markdown("---")
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("총 메시지", len(st.session_state.messages))

with col2:
    if st.session_state.assistant_id:
        st.success("Assistant 활성화")
    else:
        st.error("Assistant 비활성화")

with col3:
    if st.session_state.thread_id:
        st.success("Thread 활성화")
    else:
        st.error("Thread 비활성화")

with col4:
    if st.session_state.file_ids:
        st.success(f"문서 {len(st.session_state.file_ids)}개 업로드됨")
    else:
        st.error("문서 없음")

# 사용법 안내
with st.expander("📖 사용법"):
    st.markdown("""
    **대량 문서 지원 챗봇 사용법:**
    
    1. **API 키 설정**: 환경변수 또는 코드 19번째 줄에서 직접 설정
    2. **문서 업로드 방식 선택**: 
       - **개별 파일**: 단일 파일 업로드
       - **다중 파일**: 여러 파일 동시 선택 업로드
       - **ZIP 파일**: ZIP 파일 업로드 후 자동 추출
    3. **Assistant 모드 선택**: 
       - 기존 Assistant 사용: `asst_nPcXHjfN0G8nFcpWPxo08byE`
       - 새 Assistant 생성: 커스텀 설정으로 새로 생성
    4. **질문하기**: 업로드된 모든 문서를 기반으로 답변
    5. **새 문서**: 새 문서 사용 시 "새 대화 시작" 클릭
    
    **지원 파일 형식:**
    - 텍스트: md, txt, csv, json
    - 코드: py, js, html, css
    - 문서: pdf, docx
    
    **특징:**
    - 대량 문서 동시 업로드 지원
    - ZIP 파일 자동 추출
    - 여러 문서 통합 검색
    - 파일별 답변 출처 표시
    - 진행률 표시
    
    **주의사항:**
    - 파일 수가 많을수록 처리 시간이 오래 걸림
    - 대용량 파일은 업로드 시간이 오래 걸릴 수 있음
    - OpenAI API 사용량에 따라 요금이 발생할 수 있음
    """)

# 디버깅 정보
if st.checkbox("디버그 정보 표시"):
    st.json({
        "assistant_id": st.session_state.assistant_id,
        "thread_id": st.session_state.thread_id,
        "file_ids": st.session_state.file_ids,
        "file_count": len(st.session_state.file_ids),
        "message_count": len(st.session_state.messages),
        "uploaded_files": [getattr(file, 'name', f'파일_{i+1}') for i, file in enumerate(uploaded_files)] if uploaded_files else None,
        "api_key_set": bool(api_key and api_key != "여기에_실제_API_키를_입력하세요")
    })