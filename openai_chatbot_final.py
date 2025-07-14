import streamlit as st
import openai
import time
import io
from typing import List, Dict, Any

# 페이지 설정
st.set_page_config(
    page_title="문서 기반 챗봇",
    page_icon="🤖",
    layout="wide"
)

# 사이드바에서 API 키 입력
st.sidebar.header("🔑 API 설정")
api_key = st.sidebar.text_input(
    "OpenAI API Key를 입력하세요:",
    type="password",
    help="OpenAI API 키를 입력하세요. https://platform.openai.com/api-keys 에서 발급받을 수 있습니다."
)

# 모델 선택
model_choice = st.sidebar.selectbox(
    "모델 선택:",
    ["gpt-4o", "gpt-4-turbo", "gpt-4", "gpt-3.5-turbo"],
    index=0,
    help="Assistant API에서 사용할 모델을 선택하세요. gpt-4o가 권장됩니다."
)

# 메인 타이틀
st.title("📚 문서 기반 AI 챗봇")
st.markdown("---")

# API 키 확인
if not api_key:
    st.warning("⚠️ 사이드바에서 OpenAI API Key를 입력해주세요.")
    st.stop()

# OpenAI 클라이언트 초기화
try:
    client = openai.OpenAI(api_key=api_key)
except Exception as e:
    st.error(f"OpenAI 클라이언트 초기화 실패: {str(e)}")
    st.stop()

# 세션 상태 초기화
if "assistant_id" not in st.session_state:
    st.session_state.assistant_id = None
if "thread_id" not in st.session_state:
    st.session_state.thread_id = None
if "messages" not in st.session_state:
    st.session_state.messages = []
if "uploaded_files" not in st.session_state:
    st.session_state.uploaded_files = []

def create_assistant(files: List[str] = None) -> str:
    """OpenAI Assistant 생성"""
    try:
        assistant = client.beta.assistants.create(
            name="문서 기반 챗봇",
            instructions="""당신은 업로드된 문서들을 기반으로 답변하는 전문 AI 어시스턴트입니다.
            
            다음 규칙을 따라주세요:
            1. 업로드된 문서의 내용을 우선적으로 참고하여 답변하세요.
            2. 문서에서 찾은 정보를 인용할 때는 출처를 명시하세요.
            3. 문서에 없는 내용에 대해서는 일반적인 지식으로 답변하되, 문서 기반이 아님을 명시하세요.
            4. 한국어로 친절하고 자세하게 답변하세요.
            5. 필요시 문서의 특정 부분을 요약하거나 해석해주세요.""",
            model=model_choice,
            tools=[{"type": "file_search"}],
            tool_resources={"file_search": {"vector_store_ids": []}} if files else None
        )
        return assistant.id
    except Exception as e:
        st.error(f"Assistant 생성 실패: {str(e)}")
        return None

def upload_file_to_openai(file) -> str:
    """파일을 OpenAI에 업로드"""
    try:
        file_obj = client.files.create(
            file=file,
            purpose="assistants"
        )
        return file_obj.id
    except Exception as e:
        st.error(f"파일 업로드 실패: {str(e)}")
        return None

def create_vector_store_with_files(file_ids: List[str]) -> str:
    """Vector Store 생성 및 파일 추가"""
    try:
        vector_store = client.beta.vector_stores.create(
            name="문서 벡터 저장소"
        )
        
        # 파일들을 벡터 저장소에 추가
        client.beta.vector_stores.file_batches.create(
            vector_store_id=vector_store.id,
            file_ids=file_ids
        )
        
        return vector_store.id
    except Exception as e:
        st.error(f"Vector Store 생성 실패: {str(e)}")
        return None

def update_assistant_with_vector_store(assistant_id: str, vector_store_id: str):
    """Assistant에 Vector Store 연결"""
    try:
        client.beta.assistants.update(
            assistant_id=assistant_id,
            tool_resources={"file_search": {"vector_store_ids": [vector_store_id]}}
        )
    except Exception as e:
        st.error(f"Assistant 업데이트 실패: {str(e)}")

def create_thread() -> str:
    """대화 스레드 생성"""
    try:
        thread = client.beta.threads.create()
        return thread.id
    except Exception as e:
        st.error(f"Thread 생성 실패: {str(e)}")
        return None

def send_message(thread_id: str, message: str) -> str:
    """메시지 전송 및 응답 받기"""
    try:
        # 메시지 추가
        client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=message
        )
        
        # 실행 시작
        run = client.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=st.session_state.assistant_id
        )
        
        # 실행 완료 대기
        with st.spinner("답변을 생성하고 있습니다..."):
            while True:
                run_status = client.beta.threads.runs.retrieve(
                    thread_id=thread_id,
                    run_id=run.id
                )
                
                if run_status.status == "completed":
                    break
                elif run_status.status == "failed":
                    st.error("답변 생성에 실패했습니다.")
                    return None
                
                time.sleep(1)
        
        # 메시지 가져오기
        messages = client.beta.threads.messages.list(thread_id=thread_id)
        return messages.data[0].content[0].text.value
        
    except Exception as e:
        st.error(f"메시지 전송 실패: {str(e)}")
        return None

# 파일 업로드 섹션
st.header("📄 문서 업로드")
uploaded_files = st.file_uploader(
    "문서를 업로드하세요 (PDF, TXT, DOCX 등):",
    accept_multiple_files=True,
    type=['pdf', 'txt', 'docx', 'doc', 'csv', 'xlsx', 'md']
)

if uploaded_files:
    if st.button("📚 문서 처리 및 챗봇 초기화"):
        with st.spinner("문서를 처리하고 있습니다..."):
            # 파일 업로드
            file_ids = []
            for uploaded_file in uploaded_files:
                file_id = upload_file_to_openai(uploaded_file)
                if file_id:
                    file_ids.append(file_id)
            
            if file_ids:
                # Vector Store 생성
                vector_store_id = create_vector_store_with_files(file_ids)
                
                if vector_store_id:
                    # Assistant 생성
                    assistant_id = create_assistant()
                    
                    if assistant_id:
                        # Assistant에 Vector Store 연결
                        update_assistant_with_vector_store(assistant_id, vector_store_id)
                        
                        # Thread 생성
                        thread_id = create_thread()
                        
                        if thread_id:
                            st.session_state.assistant_id = assistant_id
                            st.session_state.thread_id = thread_id
                            st.session_state.uploaded_files = [f.name for f in uploaded_files]
                            st.session_state.messages = []
                            st.success("✅ 문서 처리가 완료되었습니다! 이제 질문을 입력하세요.")
                        else:
                            st.error("Thread 생성에 실패했습니다.")
                    else:
                        st.error("Assistant 생성에 실패했습니다.")
                else:
                    st.error("Vector Store 생성에 실패했습니다.")
            else:
                st.error("파일 업로드에 실패했습니다.")

# 업로드된 파일 목록 표시
if st.session_state.uploaded_files:
    st.success(f"📁 업로드된 문서: {', '.join(st.session_state.uploaded_files)}")

# 챗봇 섹션
st.header("💬 AI 챗봇")

# 대화 기록 표시
if st.session_state.messages:
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

# 메시지 입력
if st.session_state.assistant_id and st.session_state.thread_id:
    if prompt := st.chat_input("메시지를 입력하세요..."):
        # 사용자 메시지 표시
        with st.chat_message("user"):
            st.markdown(prompt)
        
        # 메시지 기록에 추가
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        # AI 응답 생성
        response = send_message(st.session_state.thread_id, prompt)
        
        if response:
            # AI 응답 표시
            with st.chat_message("assistant"):
                st.markdown(response)
            
            # 응답 기록에 추가
            st.session_state.messages.append({"role": "assistant", "content": response})
else:
    st.info("💡 문서를 업로드하고 '문서 처리 및 챗봇 초기화' 버튼을 클릭하여 챗봇을 시작하세요.")

# 사이드바 정보
st.sidebar.markdown("---")
st.sidebar.header("ℹ️ 사용 방법")
st.sidebar.markdown("""
1. **API Key 입력**: OpenAI API 키를 입력하세요
2. **모델 선택**: 사용할 모델을 선택하세요 (gpt-4o 권장)
3. **문서 업로드**: 분석할 문서들을 업로드하세요
4. **초기화**: '문서 처리 및 챗봇 초기화' 버튼을 클릭하세요
5. **대화 시작**: 업로드된 문서에 대해 질문하세요
""")

st.sidebar.markdown("---")
st.sidebar.header("🎯 기능")
st.sidebar.markdown("""
- 📚 **다중 문서 지원**: 여러 문서를 동시에 업로드
- 🔍 **스마트 검색**: 문서 내용을 빠르게 검색
- 💬 **대화형 인터페이스**: 자연스러운 대화로 정보 획득
- 📝 **출처 표시**: 답변의 근거가 되는 문서 표시
- 🌐 **다양한 파일 형식**: PDF, TXT, DOCX, CSV 등 지원
""")

# 초기화 버튼
if st.sidebar.button("🔄 대화 초기화"):
    st.session_state.messages = []
    st.session_state.assistant_id = None
    st.session_state.thread_id = None
    st.session_state.uploaded_files = []
    st.success("대화가 초기화되었습니다.")
    st.rerun()
