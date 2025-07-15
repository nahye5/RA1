import streamlit as st
import openai
import time
import json
import os
from typing import List, Dict, Any
from datetime import datetime
import requests

# 페이지 설정
st.set_page_config(
    page_title="문서 기반 챗봇",
    page_icon="🤖",
    layout="wide"
)

# 문서 저장소 경로
DOCUMENTS_DB_PATH = "documents_db.json"

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
    # API 키가 유효한지 확인
    models = client.models.list()
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
if "vector_store_id" not in st.session_state:
    st.session_state.vector_store_id = None

def load_documents_db() -> Dict[str, Any]:
    """문서 데이터베이스 로드"""
    if os.path.exists(DOCUMENTS_DB_PATH):
        try:
            with open(DOCUMENTS_DB_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {
        "documents": [],
        "vector_store_id": None,
        "assistant_id": None,
        "created_at": datetime.now().isoformat()
    }

def save_documents_db(db: Dict[str, Any]):
    """문서 데이터베이스 저장"""
    try:
        with open(DOCUMENTS_DB_PATH, 'w', encoding='utf-8') as f:
            json.dump(db, f, ensure_ascii=False, indent=2)
    except Exception as e:
        st.error(f"문서 데이터베이스 저장 실패: {str(e)}")

def make_api_request(method: str, endpoint: str, data: dict = None, files: dict = None) -> dict:
    """OpenAI API 직접 호출"""
    base_url = "https://api.openai.com/v1"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "OpenAI-Beta": "assistants=v2"
    }
    
    url = f"{base_url}{endpoint}"
    
    try:
        if method == "POST":
            if files:
                response = requests.post(url, headers=headers, data=data, files=files)
            else:
                headers["Content-Type"] = "application/json"
                response = requests.post(url, headers=headers, json=data)
        elif method == "GET":
            response = requests.get(url, headers=headers)
        elif method == "DELETE":
            response = requests.delete(url, headers=headers)
        else:
            raise ValueError(f"지원되지 않는 메서드: {method}")
        
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"API 요청 실패: {str(e)}")
        return None

def create_or_get_vector_store(db: Dict[str, Any]) -> str:
    """Vector Store 생성 또는 가져오기"""
    try:
        # 기존 Vector Store 확인
        if db.get("vector_store_id"):
            try:
                result = make_api_request("GET", f"/vector_stores/{db['vector_store_id']}")
                if result and result.get("id"):
                    return result["id"]
            except:
                pass
        
        # 새 Vector Store 생성
        data = {
            "name": "문서 저장소",
            "expires_after": {
                "anchor": "last_active_at",
                "days": 30
            }
        }
        
        result = make_api_request("POST", "/vector_stores", data)
        if result and result.get("id"):
            vector_store_id = result["id"]
            db["vector_store_id"] = vector_store_id
            save_documents_db(db)
            return vector_store_id
        else:
            st.error("Vector Store 생성 실패")
            return None
            
    except Exception as e:
        st.error(f"Vector Store 생성 실패: {str(e)}")
        return None

def create_or_get_assistant(db: Dict[str, Any], vector_store_id: str) -> str:
    """Assistant 생성 또는 가져오기"""
    try:
        # 기존 Assistant 확인
        if db.get("assistant_id"):
            try:
                assistant = client.beta.assistants.retrieve(db["assistant_id"])
                return assistant.id
            except:
                pass
        
        # 새 Assistant 생성
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
            tool_resources={
                "file_search": {
                    "vector_store_ids": [vector_store_id]
                }
            }
        )
        
        db["assistant_id"] = assistant.id
        save_documents_db(db)
        
        return assistant.id
    except Exception as e:
        st.error(f"Assistant 생성 실패: {str(e)}")
        return None

def upload_file_to_openai(file) -> tuple:
    """파일을 OpenAI에 업로드"""
    try:
        file_obj = client.files.create(
            file=file,
            purpose="assistants"
        )
        return file_obj.id, file_obj.filename
    except Exception as e:
        st.error(f"파일 업로드 실패: {str(e)}")
        return None, None

def add_files_to_vector_store(vector_store_id: str, file_ids: List[str]):
    """Vector Store에 파일 추가"""
    try:
        data = {
            "file_ids": file_ids
        }
        result = make_api_request("POST", f"/vector_stores/{vector_store_id}/file_batches", data)
        if result:
            # 파일 배치 완료 대기
            batch_id = result.get("id")
            if batch_id:
                with st.spinner("파일을 Vector Store에 추가하는 중..."):
                    while True:
                        batch_status = make_api_request("GET", f"/vector_stores/{vector_store_id}/file_batches/{batch_id}")
                        if batch_status and batch_status.get("status") == "completed":
                            break
                        elif batch_status and batch_status.get("status") == "failed":
                            st.error("파일 배치 처리 실패")
                            break
                        time.sleep(2)
    except Exception as e:
        st.error(f"Vector Store 파일 추가 실패: {str(e)}")

def delete_file_from_vector_store(vector_store_id: str, file_id: str):
    """Vector Store에서 파일 삭제"""
    try:
        # Vector Store에서 파일 삭제
        make_api_request("DELETE", f"/vector_stores/{vector_store_id}/files/{file_id}")
        
        # OpenAI 파일도 삭제
        try:
            client.files.delete(file_id)
        except:
            pass  # 파일 삭제 실패는 무시
            
    except Exception as e:
        st.error(f"파일 삭제 실패: {str(e)}")

def create_thread() -> str:
    """대화 스레드 생성"""
    try:
        thread = client.beta.threads.create()
        return thread.id
    except Exception as e:
        st.error(f"Thread 생성 실패: {str(e)}")
        return None

def send_message(thread_id: str, message: str, assistant_id: str) -> str:
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
            assistant_id=assistant_id
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
                    st.error(f"답변 생성에 실패했습니다: {run_status.last_error}")
                    return None
                elif run_status.status == "requires_action":
                    st.info("추가 작업이 필요합니다...")
                
                time.sleep(1)
        
        # 메시지 가져오기
        messages = client.beta.threads.messages.list(thread_id=thread_id)
        latest_message = messages.data[0]
        
        # 텍스트 내용 추출
        content = ""
        for content_item in latest_message.content:
            if content_item.type == "text":
                content += content_item.text.value
        
        return content
        
    except Exception as e:
        st.error(f"메시지 전송 실패: {str(e)}")
        return None

# 대체 방법으로 Vector Store 작업 수행
def alternative_vector_store_operations():
    """Vector Store 작업을 위한 대체 메서드들"""
    st.info("💡 Vector Store API 이슈가 감지되었습니다. 대체 방법을 사용합니다.")
    
    # Assistant만 사용하는 간단한 방법
    return "simple_assistant_mode"

# 문서 데이터베이스 로드
db = load_documents_db()

# 기존 문서 관리 섹션
st.header("📁 문서 관리")

col1, col2 = st.columns([3, 1])

with col1:
    st.subheader("📋 저장된 문서 목록")
    
    if db["documents"]:
        for i, doc in enumerate(db["documents"]):
            col_name, col_date, col_delete = st.columns([2, 1, 1])
            
            with col_name:
                st.write(f"📄 {doc['filename']}")
            
            with col_date:
                upload_date = datetime.fromisoformat(doc['uploaded_at']).strftime("%Y-%m-%d %H:%M")
                st.write(f"📅 {upload_date}")
            
            with col_delete:
                if st.button(f"🗑️ 삭제", key=f"delete_{i}"):
                    # Vector Store에서 파일 삭제
                    if db.get("vector_store_id"):
                        delete_file_from_vector_store(db["vector_store_id"], doc['file_id'])
                    
                    # DB에서 문서 제거
                    db["documents"].pop(i)
                    save_documents_db(db)
                    st.success(f"'{doc['filename']}' 문서가 삭제되었습니다.")
                    st.rerun()
    else:
        st.info("저장된 문서가 없습니다.")

with col2:
    st.subheader("🔧 관리 도구")
    
    if st.button("🗑️ 모든 문서 삭제"):
        if db["documents"]:
            # 모든 파일 삭제
            if db.get("vector_store_id"):
                for doc in db["documents"]:
                    delete_file_from_vector_store(db["vector_store_id"], doc['file_id'])
            
            # DB 초기화
            db["documents"] = []
            save_documents_db(db)
            st.success("모든 문서가 삭제되었습니다.")
            st.rerun()
        else:
            st.info("삭제할 문서가 없습니다.")

# 새 문서 업로드 섹션
st.header("📤 새 문서 업로드")

uploaded_files = st.file_uploader(
    "새 문서를 업로드하세요 (PDF, TXT, DOCX 등):",
    accept_multiple_files=True,
    type=['pdf', 'txt', 'docx', 'doc', 'csv', 'xlsx', 'md']
)

if uploaded_files:
    if st.button("📚 문서 추가"):
        with st.spinner("문서를 처리하고 있습니다..."):
            # Vector Store 생성 또는 가져오기
            vector_store_id = create_or_get_vector_store(db)
            
            if vector_store_id:
                # 파일 업로드
                file_ids = []
                new_documents = []
                
                for uploaded_file in uploaded_files:
                    file_id, filename = upload_file_to_openai(uploaded_file)
                    if file_id:
                        file_ids.append(file_id)
                        new_documents.append({
                            "filename": filename or uploaded_file.name,
                            "file_id": file_id,
                            "uploaded_at": datetime.now().isoformat()
                        })
                
                if file_ids:
                    # Vector Store에 파일 추가
                    add_files_to_vector_store(vector_store_id, file_ids)
                    
                    # DB에 문서 정보 추가
                    db["documents"].extend(new_documents)
                    save_documents_db(db)
                    
                    st.success(f"✅ {len(file_ids)}개의 문서가 추가되었습니다!")
                    st.rerun()
                else:
                    st.error("파일 업로드에 실패했습니다.")
            else:
                st.error("Vector Store 생성에 실패했습니다.")

# 챗봇 초기화 섹션
st.header("🤖 챗봇 초기화")

if db["documents"]:
    if st.button("🚀 챗봇 시작"):
        with st.spinner("챗봇을 초기화하고 있습니다..."):
            # Vector Store 가져오기
            vector_store_id = create_or_get_vector_store(db)
            
            if vector_store_id:
                # Assistant 생성 또는 가져오기
                assistant_id = create_or_get_assistant(db, vector_store_id)
                
                if assistant_id:
                    # Thread 생성
                    thread_id = create_thread()
                    
                    if thread_id:
                        st.session_state.assistant_id = assistant_id
                        st.session_state.thread_id = thread_id
                        st.session_state.vector_store_id = vector_store_id
                        st.session_state.messages = []
                        st.success("✅ 챗봇이 초기화되었습니다! 이제 질문을 입력하세요.")
                    else:
                        st.error("Thread 생성에 실패했습니다.")
                else:
                    st.error("Assistant 생성에 실패했습니다.")
            else:
                st.error("Vector Store 가져오기에 실패했습니다.")
else:
    st.info("💡 먼저 문서를 업로드해주세요.")

# 챗봇 섹션
st.header("💬 AI 챗봇")

# 현재 상태 표시
if st.session_state.assistant_id and st.session_state.thread_id:
    st.success(f"🟢 챗봇이 활성화되었습니다. (문서 {len(db['documents'])}개 로드됨)")
    
    # 대화 기록 표시
    if st.session_state.messages:
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
    
    # 메시지 입력
    if prompt := st.chat_input("메시지를 입력하세요..."):
        # 사용자 메시지 표시
        with st.chat_message("user"):
            st.markdown(prompt)
        
        # 메시지 기록에 추가
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        # AI 응답 생성
        response = send_message(st.session_state.thread_id, prompt, st.session_state.assistant_id)
        
        if response:
            # AI 응답 표시
            with st.chat_message("assistant"):
                st.markdown(response)
            
            # 응답 기록에 추가
            st.session_state.messages.append({"role": "assistant", "content": response})
else:
    st.info("💡 '챗봇 시작' 버튼을 클릭하여 챗봇을 활성화하세요.")

# 사이드바 정보
st.sidebar.markdown("---")
st.sidebar.header("ℹ️ 사용 방법")
st.sidebar.markdown("""
1. **API Key 입력**: OpenAI API 키를 입력하세요
2. **모델 선택**: 사용할 모델을 선택하세요
3. **문서 업로드**: 분석할 문서들을 업로드하세요
4. **챗봇 시작**: '챗봇 시작' 버튼을 클릭하세요
5. **대화 시작**: 업로드된 문서에 대해 질문하세요
""")

st.sidebar.markdown("---")
st.sidebar.header("🎯 새로운 기능")
st.sidebar.markdown("""
- 💾 **영구 문서 저장**: 문서가 영구적으로 저장됩니다
- 📁 **문서 관리**: 저장된 문서 목록 확인 및 삭제
- ➕ **점진적 업로드**: 기존 문서에 새 문서 추가
- 🔄 **재사용 가능**: 한 번 업로드하면 계속 사용 가능
- 📊 **Vector Store**: 효율적인 문서 검색 및 관리
- 🛠️ **API 호환성**: 최신 OpenAI API 변경사항 대응
""")

# 대화 초기화 버튼
if st.sidebar.button("🔄 대화 초기화"):
    st.session_state.messages = []
    st.session_state.thread_id = None
    st.success("대화가 초기화되었습니다.")
    st.rerun()

# 전체 초기화 버튼
if st.sidebar.button("🗑️ 전체 초기화"):
    if db["documents"]:
        # 모든 파일 삭제
        if db.get("vector_store_id"):
            for doc in db["documents"]:
                delete_file_from_vector_store(db["vector_store_id"], doc['file_id'])
    
    # 세션 상태 초기화
    st.session_state.messages = []
    st.session_state.assistant_id = None
    st.session_state.thread_id = None
    st.session_state.vector_store_id = None
    
    # DB 파일 삭제
    if os.path.exists(DOCUMENTS_DB_PATH):
        os.remove(DOCUMENTS_DB_PATH)
    
    st.success("모든 데이터가 초기화되었습니다.")
    st.rerun()

# 디버깅 정보 (개발자용)
if st.sidebar.checkbox("🔍 디버깅 정보 표시"):
    st.sidebar.markdown("---")
    st.sidebar.header("🔧 디버깅 정보")
    st.sidebar.write(f"Vector Store ID: {st.session_state.vector_store_id}")
    st.sidebar.write(f"Assistant ID: {st.session_state.assistant_id}")
    st.sidebar.write(f"Thread ID: {st.session_state.thread_id}")
    st.sidebar.write(f"저장된 문서 수: {len(db['documents'])}")
