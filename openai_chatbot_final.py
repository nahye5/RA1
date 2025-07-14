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

# 지원하는 파일 확장자
SUPPORTED_EXTENSIONS = ['md', 'txt', 'pdf', 'docx', 'json', 'csv', 'py', 'js', 'html', 'css']

# 세션 상태 초기화
if "api_key" not in st.session_state:
    st.session_state.api_key = ""
if "client" not in st.session_state:
    st.session_state.client = None
if "messages" not in st.session_state:
    st.session_state.messages = []
if "assistant_id" not in st.session_state:
    st.session_state.assistant_id = None
if "thread_id" not in st.session_state:
    st.session_state.thread_id = None
if "file_ids" not in st.session_state:
    st.session_state.file_ids = []
if "vector_store_id" not in st.session_state:
    st.session_state.vector_store_id = None

# API 키 입력 함수
def get_api_key():
    """API 키 입력 및 검증"""
    with st.sidebar:
        st.title("🔐 API 키 설정")
        
        # 환경변수에서 API 키 확인
        env_key = os.getenv("OPENAI_API_KEY")
        if env_key:
            st.success("✅ 환경변수에서 API 키 발견")
            if st.button("환경변수 API 키 사용"):
                st.session_state.api_key = env_key
                st.rerun()
        
        # 직접 입력
        api_key_input = st.text_input(
            "OpenAI API 키를 입력하세요:",
            type="password",
            placeholder="sk-...",
            help="OpenAI 플랫폼에서 API 키를 생성하세요"
        )
        
        if st.button("API 키 설정"):
            if api_key_input and api_key_input.startswith("sk-"):
                # API 키 검증
                try:
                    test_client = openai.OpenAI(api_key=api_key_input)
                    # 간단한 API 호출로 키 검증
                    test_client.models.list()
                    st.session_state.api_key = api_key_input
                    st.session_state.client = test_client
                    st.success("✅ API 키 검증 완료!")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ 유효하지 않은 API 키: {str(e)}")
            else:
                st.error("❌ 올바른 API 키를 입력하세요 (sk-로 시작)")
        
        # API 키 상태 표시
        if st.session_state.api_key:
            st.success("✅ API 키 설정 완료")
            masked_key = st.session_state.api_key[:7] + "..." + st.session_state.api_key[-4:]
            st.info(f"🔑 현재 키: {masked_key}")
            
            if st.button("API 키 재설정"):
                st.session_state.api_key = ""
                st.session_state.client = None
                # 기타 세션 상태 초기화
                st.session_state.assistant_id = None
                st.session_state.thread_id = None
                st.session_state.file_ids = []
                st.session_state.vector_store_id = None
                st.rerun()
        else:
            st.error("❌ API 키를 설정해주세요")
            st.markdown("""
            **API 키 획득 방법:**
            1. [OpenAI Platform](https://platform.openai.com/api-keys) 접속
            2. 'Create new secret key' 클릭
            3. 생성된 키를 복사하여 위에 입력
            """)

# API 키 입력 화면
if not st.session_state.api_key:
    get_api_key()
    st.title("📚 문서 기반 AI 챗봇")
    st.warning("⚠️ 먼저 사이드바에서 OpenAI API 키를 설정해주세요.")
    st.markdown("""
    ### 📋 사용법
    1. **API 키 설정**: 사이드바에서 OpenAI API 키 입력
    2. **문서 업로드**: 분석할 문서들을 업로드
    3. **AI 채팅**: 업로드된 문서 기반으로 질문 답변
    """)
    st.stop()

# 클라이언트 초기화
if not st.session_state.client:
    try:
        st.session_state.client = openai.OpenAI(api_key=st.session_state.api_key)
    except Exception as e:
        st.error(f"OpenAI 클라이언트 초기화 실패: {e}")
        st.stop()

client = st.session_state.client

# 사이드바 설정
with st.sidebar:
    get_api_key()
    
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
    
    # Assistant 설정
    st.subheader("🤖 Assistant 설정")
    assistant_name = st.text_input("Assistant 이름", value="문서 전문가")
    
    # 모델 선택
    model_choice = st.selectbox(
        "모델 선택",
        ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"],
        help="gpt-4o-mini가 비용 효율적입니다"
    )
    
    # 새 대화 시작
    if st.button("새 대화 시작"):
        # 기존 리소스 정리
        if st.session_state.assistant_id:
            try:
                client.beta.assistants.delete(st.session_state.assistant_id)
            except:
                pass
        
        # 세션 상태 초기화 (API 키 제외)
        keys_to_preserve = ['api_key', 'client']
        for key in list(st.session_state.keys()):
            if key not in keys_to_preserve:
                del st.session_state[key]
        
        # 필수 키 다시 초기화
        st.session_state.messages = []
        st.session_state.assistant_id = None
        st.session_state.thread_id = None
        st.session_state.file_ids = []
        st.session_state.vector_store_id = None
        
        st.rerun()

# 메인 페이지
st.title("📚 문서 기반 AI 챗봇")
st.markdown("업로드된 문서들을 기반으로 답변하는 AI 챗봇입니다.")

# 파일 업로드 확인
if not uploaded_files:
    st.warning("⚠️ 사이드바에서 문서를 업로드해주세요.")
    st.info("📝 업로드된 문서만을 기반으로 답변합니다.")
    st.stop()

# 파일 업로드 및 Assistant 생성
def upload_files_and_create_assistant():
    """파일 업로드 및 Assistant 생성 (호환 버전)"""
    try:
        # 1. 파일 업로드
        uploaded_file_ids = []
        
        with st.spinner(f"파일들을 업로드하는 중... (0/{len(uploaded_files)})"):
            for i, file in enumerate(uploaded_files):
                file_content = file.read()
                file_name = getattr(file, 'name', f'파일_{i+1}')
                
                # 진행률 표시
                progress = (i + 1) / len(uploaded_files)
                st.progress(progress, text=f"업로드 중: {file_name} ({i+1}/{len(uploaded_files)})")
                
                # OpenAI에 파일 업로드
                uploaded_file = client.files.create(
                    file=(file_name, file_content),
                    purpose='assistants'
                )
                uploaded_file_ids.append(uploaded_file.id)
        
        st.session_state.file_ids = uploaded_file_ids
        
        # 2. Assistant 생성
        file_list = [getattr(file, 'name', f'파일_{i+1}') for i, file in enumerate(uploaded_files)]
        
        instructions = f"""
        당신은 업로드된 문서들의 전문가입니다. 다음 규칙을 엄격히 따라주세요:

        1. 오직 업로드된 문서들의 내용만을 기반으로 답변하세요.
        2. 문서에 없는 내용에 대해서는 "해당 내용은 업로드된 문서들에서 찾을 수 없습니다"라고 답변하세요.
        3. 답변할 때 가능하면 해당 파일명이나 문서 출처를 명시하세요.
        4. 문서 외의 일반적인 지식을 사용하지 마세요.
        5. 여러 문서에서 관련 정보를 찾은 경우, 각 문서의 정보를 종합하여 답변하세요.
        6. 답변의 정확성을 위해 문서 내용을 자세히 검토하세요.
        
        업로드된 문서 파일들: {', '.join(file_list)}
        총 {len(uploaded_files)}개의 문서가 업로드되었습니다.
        """
        
        with st.spinner("Assistant를 생성하는 중..."):
            # Vector Store 지원 여부 확인
            try:
                # Vector Store 방식 시도 (최신 버전)
                vector_store = client.beta.vector_stores.create(
                    name=f"문서 저장소 - {datetime.now().strftime('%Y%m%d_%H%M%S')}"
                )
                st.session_state.vector_store_id = vector_store.id
                
                # Vector Store에 파일 추가
                client.beta.vector_stores.file_batches.create(
                    vector_store_id=vector_store.id,
                    file_ids=uploaded_file_ids
                )
                
                assistant = client.beta.assistants.create(
                    name=assistant_name,
                    instructions=instructions,
                    model=model_choice,
                    tools=[{"type": "file_search"}],
                    tool_resources={
                        "file_search": {
                            "vector_store_ids": [vector_store.id]
                        }
                    }
                )
                st.info("✅ 최신 Vector Store 방식으로 Assistant 생성됨")
                
            except AttributeError:
                # 구 버전 호환 방식 (file_ids 직접 사용)
                assistant = client.beta.assistants.create(
                    name=assistant_name,
                    instructions=instructions,
                    model=model_choice,
                    tools=[{"type": "retrieval"}],  # 구 버전에서는 retrieval 사용
                    file_ids=uploaded_file_ids
                )
                st.info("✅ 호환 모드로 Assistant 생성됨 (구 버전)")
            
            st.session_state.assistant_id = assistant.id
        
        st.success(f"✅ {len(uploaded_files)}개 파일 업로드 및 Assistant 생성 완료!")
        return True
        
    except Exception as e:
        st.error(f"설정 실패: {e}")
        # 상세한 오류 정보 표시
        st.error("💡 해결 방법:")
        st.code("pip install --upgrade openai", language="bash")
        st.markdown("또는 OpenAI Python 라이브러리 버전이 1.14.0 이상인지 확인하세요.")
        return False

# Thread 생성
def create_thread():
    """대화 스레드 생성"""
    try:
        thread = client.beta.threads.create()
        st.session_state.thread_id = thread.id
        return True
    except Exception as e:
        st.error(f"Thread 생성 실패: {e}")
        return False

# 메시지 전송 및 응답
def send_message(message):
    """메시지 전송 및 AI 응답 받기"""
    try:
        # 사용자 메시지 추가
        client.beta.threads.messages.create(
            thread_id=st.session_state.thread_id,
            role="user",
            content=message
        )
        
        # Run 생성 및 실행
        run = client.beta.threads.runs.create(
            thread_id=st.session_state.thread_id,
            assistant_id=st.session_state.assistant_id
        )
        
        # 응답 대기
        with st.spinner("문서를 검색하고 답변을 생성하는 중..."):
            while True:
                run_status = client.beta.threads.runs.retrieve(
                    thread_id=st.session_state.thread_id,
                    run_id=run.id
                )
                
                if run_status.status == "completed":
                    break
                elif run_status.status == "failed":
                    st.error(f"답변 생성 실패: {run_status.last_error}")
                    return None
                elif run_status.status == "requires_action":
                    st.error("추가 작업이 필요합니다.")
                    return None
                elif run_status.status == "expired":
                    st.error("요청 시간이 초과되었습니다.")
                    return None
                
                time.sleep(1)
        
        # 최신 응답 메시지 가져오기
        messages = client.beta.threads.messages.list(
            thread_id=st.session_state.thread_id,
            order="desc",
            limit=1
        )
        
        if messages.data and messages.data[0].role == "assistant":
            return messages.data[0].content[0].text.value
        else:
            st.error("응답을 가져올 수 없습니다.")
            return None
            
    except Exception as e:
        st.error(f"메시지 전송 실패: {e}")
        return None

# Assistant 및 Thread 초기화
if not st.session_state.assistant_id:
    if not upload_files_and_create_assistant():
        st.stop()

if not st.session_state.thread_id:
    if not create_thread():
        st.stop()

# 현재 상태 표시
if st.session_state.file_ids:
    st.info(f"📄 **현재 사용 중인 문서 수**: {len(st.session_state.file_ids)}개")
    
    # 업로드된 파일 목록 표시
    with st.expander("📋 업로드된 파일 목록"):
        for i, file in enumerate(uploaded_files):
            file_name = getattr(file, 'name', f'파일_{i+1}')
            st.text(f"📄 {file_name}")

# 채팅 인터페이스
chat_container = st.container()

with chat_container:
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if "timestamp" in message:
                st.caption(f"🕐 {message['timestamp']}")

# 사용자 입력 처리
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
    
    # AI 응답 받기
    response = send_message(prompt)
    
    if response:
        # AI 응답 추가
        response_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        st.session_state.messages.append({
            "role": "assistant", 
            "content": response,
            "timestamp": response_timestamp
        })
        
        # AI 응답 표시
        with st.chat_message("assistant"):
            st.markdown(response)
            st.caption(f"🕐 {response_timestamp}")

# 하단 상태 표시
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
        st.success(f"문서 {len(st.session_state.file_ids)}개")
    else:
        st.error("문서 없음")

# 사용법 안내
with st.expander("📖 사용법"):
    st.markdown("""
    **현대적인 문서 기반 AI 챗봇 사용법:**
    
    ### 🔧 초기 설정
    1. **OpenAI 라이브러리 업그레이드**: `pip install --upgrade openai`
    2. **API 키 설정**: 사이드바에서 OpenAI API 키 입력 및 검증
    3. **문서 업로드**: 다양한 방식으로 문서 업로드 지원
    4. **Assistant 설정**: 모델 선택 및 이름 설정
    
    ### 📤 문서 업로드 방식
    - **개별 파일**: 단일 파일 업로드
    - **다중 파일**: 여러 파일 동시 선택 업로드  
    - **ZIP 파일**: ZIP 파일 업로드 후 자동 추출
    
    ### 🎯 주요 기능
    - 최신 OpenAI Assistants API v2 사용
    - Vector Store 기반 문서 검색
    - 실시간 파일 업로드 진행률 표시
    - 안전한 API 키 관리
    - 다중 문서 통합 검색
    
    ### 📋 지원 파일 형식
    - **텍스트**: md, txt, csv, json
    - **코드**: py, js, html, css  
    - **문서**: pdf, docx
    
    ### ⚠️ 주의사항
    - 파일 수가 많을수록 처리 시간 증가
    - 대용량 파일은 업로드 시간 오래 소요
    - OpenAI API 사용량에 따른 요금 발생
    - API 키는 안전하게 관리하세요
    """)

# 디버깅 정보
if st.checkbox("🔍 디버그 정보 표시"):
    debug_info = {
        "api_key_set": bool(st.session_state.api_key),
        "assistant_id": st.session_state.assistant_id,
        "thread_id": st.session_state.thread_id,
        "vector_store_id": st.session_state.vector_store_id,
        "file_ids": st.session_state.file_ids,
        "file_count": len(st.session_state.file_ids),
        "message_count": len(st.session_state.messages),
        "uploaded_files": [getattr(file, 'name', f'파일_{i+1}') for i, file in enumerate(uploaded_files)] if uploaded_files else [],
        "model": model_choice,
        "assistant_name": assistant_name
    }
    st.json(debug_info)
