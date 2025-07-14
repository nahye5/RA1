
import streamlit as st
import openai
from packaging import version
from datetime import datetime
import time

###############################################################################
# 🌟 Streamlit – OpenAI Assistants (Vector Store 기반)                        #
#   - SDK v1.2 이상 : Vector Store + file_search                               #
#   - SDK v1.1 이하 : retrieval + file_ids (구버전 호환)                       #
###############################################################################

st.set_page_config(page_title="OpenAI 문서 챗봇", page_icon="🤖")

###############################################################################
# 1. API 키 입력 & 클라이언트 초기화
###############################################################################
if "api_key" not in st.session_state:
    st.session_state.api_key = ""

st.sidebar.header("🔑 OpenAI API Key")
api_key_input = st.sidebar.text_input(
    "sk-로 시작하는 키를 입력하세요",
    type="password",
    value=st.session_state.api_key,
    placeholder="sk-...",
)

if st.sidebar.button("API 키 설정"):
    if api_key_input.startswith("sk-"):
        st.session_state.api_key = api_key_input
        st.sidebar.success("API 키가 저장되었습니다!")
    else:
        st.sidebar.error("유효한 API 키를 입력해 주세요 (sk- 로 시작)")

if not st.session_state.api_key:
    st.stop()

client = openai.OpenAI(api_key=st.session_state.api_key)

###############################################################################
# 2. 파일 업로드
###############################################################################
st.header("📄 문서 업로드")
uploaded_files = st.file_uploader(
    "PDF, DOCX, TXT 등을 선택하세요 (여러 개 가능)",
    type=None,
    accept_multiple_files=True,
)

###############################################################################
# 3. 챗봇 옵션
###############################################################################
st.header("⚙️ 설정")
assistant_name = st.text_input("Assistant 이름", value="문서 챗봇")
model_choice = st.selectbox(
    "모델 선택",
    ["gpt-4o-2024-05-13", "gpt-4o-mini", "gpt-3.5-turbo"],
    index=0,
)
system_instructions = st.text_area(
    "시스템 지침",
    "You are an expert assistant that answers questions based on the uploaded documents.",
    height=120,
)

if st.button("Assistant 생성/재설정"):
    if not uploaded_files:
        st.warning("먼저 문서를 업로드해 주세요.")
        st.stop()

    # 3‑1. 파일 업로드 (purpose='assistants')
    st.write("🔄 파일 업로드 중...")
    file_ids = []
    for f in uploaded_files:
        uploaded = client.files.create(
            file=(f.name, f.read()),
            purpose="assistants"
        )
        file_ids.append(uploaded.id)

    # 3‑2. SDK 버전에 따라 Assistant 생성 로직 분기
    if version.parse(openai.__version__) >= version.parse("1.2.0"):
        # ───────────────────────────────────────────────────────────────
        # 최신 버전: Vector Store + file_search
        # ───────────────────────────────────────────────────────────────
        st.write("🛠️ Vector Store 생성 중...")
        vector_store = client.beta.vector_stores.create_and_poll(
            name=f"문서 저장소 - {datetime.now().strftime('%Y%m%d_%H%M%S')}",
            file_ids=file_ids,
        )

        st.write("🤖 Assistant 생성 중...")
        assistant = client.beta.assistants.create(
            name=assistant_name,
            instructions=system_instructions,
            model=model_choice,
            tools=[{"type": "file_search"}],
            tool_resources={
                "file_search": {"vector_store_ids": [vector_store.id]}
            },
        )
    else:
        # ───────────────────────────────────────────────────────────────
        # 구버전 호환: retrieval + file_ids
        # ───────────────────────────────────────────────────────────────
        st.write("🤖 Assistant 생성 중... (구버전 모드)")
        assistant = client.beta.assistants.create(
            name=assistant_name,
            instructions=system_instructions,
            model=model_choice,
            tools=[{"type": "retrieval"}],
            file_ids=file_ids,
        )

    # 3‑3. 새 Thread 생성
    thread = client.beta.threads.create()
    st.session_state.assistant_id = assistant.id
    st.session_state.thread_id = thread.id

    st.success(f"Assistant 준비 완료! (ID: {assistant.id})")

###############################################################################
# 4. 채팅 인터페이스
###############################################################################
if "assistant_id" not in st.session_state:
    st.info("왼쪽에서 API 키를 설정하고, 문서를 업로드한 후 Assistant를 생성하세요.")
    st.stop()

st.header("💬 문서 Q&A")
user_input = st.text_input("질문을 입력하세요", placeholder="문서 내용에 대해 질문해 보세요!")

if st.button("전송") and user_input.strip():
    # 4‑1. 사용자 메시지를 Thread에 추가
    client.beta.threads.messages.create(
        thread_id=st.session_state.thread_id,
        role="user",
        content=user_input,
    )

    # 4‑2. Run 실행
    run = client.beta.threads.runs.create(
        thread_id=st.session_state.thread_id,
        assistant_id=st.session_state.assistant_id,
    )

    # 4‑3. Run 완료까지 폴링
    with st.spinner("Assistant가 생각 중..."):
        while run.status not in {"completed", "failed", "cancelled"}:
            time.sleep(1)
            run = client.beta.threads.runs.retrieve(
                thread_id=st.session_state.thread_id,
                run_id=run.id,
            )

    # 4‑4. 답변 출력
    if run.status == "completed":
        messages = client.beta.threads.messages.list(
            thread_id=st.session_state.thread_id
        ).data

        # 마지막 Assistant 메시지 검색
        for m in reversed(messages):
            if m.role == "assistant":
                st.success(m.content[0].text.value)
                break
    else:
        st.error(f"Run이 실패했습니다: {run.status}")
